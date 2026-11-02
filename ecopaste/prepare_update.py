#!/usr/bin/env python3
"""Prepare a stable upstream snapshot while retaining the fork's tested overlay."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "n0-computer/iroh"


def git(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *args], check=check,
                          text=True, capture_output=True)


def version(tag):
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
    if not match:
        raise ValueError(f"Not a stable version tag: {tag}")
    return tuple(map(int, match.groups()))


def apply_gso_patch(root):
    """Accept the carry patch or its exact upstream integration; reject conflicts."""
    patch = root / "ecopaste/patches/gso-live-limit.patch"
    if git(root, "apply", "--check", str(patch), check=False).returncode == 0:
        git(root, "apply", str(patch))
        return "backported"
    if git(root, "apply", "--reverse", "--check", str(patch), check=False).returncode == 0:
        return "upstream"
    raise RuntimeError("GSO patch conflicts with this release; current fork stays unchanged")


def install_overlay(root):
    """Keep only fork workflows and run the real socket regression on Android too."""
    workflows = root / ".github/workflows"
    if workflows.exists():
        shutil.rmtree(workflows)
    shutil.copytree(root / "ecopaste/workflows", workflows)
    shutil.copyfile(root / "ecopaste/rust-toolchain.toml", root / "rust-toolchain.toml")
    ignore = root / ".gitignore"
    ignored = ignore.read_text() if ignore.exists() else ""
    if "__pycache__/" not in ignored:
        ignore.write_text(ignored + "\n# Local Python update-tool bytecode.\n__pycache__/\n")
    source = root / "iroh/src/socket/transports.rs"
    text = source.read_text()
    old = ('#[cfg(target_os = "linux")]\n    #[tokio::test]\n'
           '    async fn open_senders_stop_batching_after_a_refused_segmented_send()')
    new = old.replace('target_os = "linux"', 'any(target_os = "linux", target_os = "android")')
    if old not in text and new not in text:
        raise RuntimeError("Required GSO regression test is missing")
    source.write_text(text.replace(old, new))
    # The fork's Android-only test exercises the actual VPN EIO when explicitly requested.
    marker = '\n#[cfg(all(test, target_os = "android"))]\n#[path = "transports/ecopaste_android_gso.rs"]\nmod ecopaste_android_gso;\n'
    text = source.read_text()
    if marker not in text:
        source.write_text(text + marker)
    shutil.copyfile(root / "ecopaste/tests/android_gso.rs",
                    root / "iroh/src/socket/transports/ecopaste_android_gso.rs")


def output(**values):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
    print(json.dumps(values))


def prepare(tag=None):
    if git(ROOT, "status", "--porcelain").stdout.strip():
        raise RuntimeError("Refusing to replace a worktree with uncommitted changes")
    state = json.loads((ROOT / "ecopaste/upstream.json").read_text())
    endpoint = f"repos/{UPSTREAM}/releases/" + (f"tags/{tag}" if tag else "latest")
    if tag:
        version(tag)
    release = json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))
    target = release["tag_name"]
    target_version = version(target)
    if release["draft"] or release["prerelease"]:
        raise RuntimeError("Only published stable releases are eligible")
    if target_version[0] != state["major"]:
        raise RuntimeError("A new upstream major version requires compatibility review")
    if target_version <= version(state["tag"]):
        output(changed="false", tag=state["tag"])
        return
    git(ROOT, "fetch", "--no-tags", f"https://github.com/{UPSTREAM}.git", f"refs/tags/{target}")
    revision = git(ROOT, "rev-parse", "FETCH_HEAD^{commit}").stdout.strip()
    original = git(ROOT, "rev-parse", "HEAD").stdout.strip()
    with tempfile.TemporaryDirectory(prefix="iroh-fork-overlay-") as temporary:
        overlay = Path(temporary) / "ecopaste"
        shutil.copytree(ROOT / "ecopaste", overlay)
        try:
            git(ROOT, "read-tree", "--reset", "-u", revision)
            shutil.copytree(overlay, ROOT / "ecopaste", dirs_exist_ok=True)
            mode = apply_gso_patch(ROOT)
            install_overlay(ROOT)
            state.update(tag=target, revision=revision, gso_patch=mode)
            (ROOT / "ecopaste/upstream.json").write_text(json.dumps(state, indent=2) + "\n")
        except Exception:
            git(ROOT, "read-tree", "--reset", "-u", original)
            raise
    output(changed="true", tag=target, upstream_sha=revision)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    prepare(args.tag)
