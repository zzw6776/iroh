"""Exercise patch carry-forward and conflict handling against real upstream files."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FORK = Path(__file__).resolve().parents[2]
# Freeze the pre-fix fixture; the tracked upstream revision may already contain the fix.
UNFIXED_UPSTREAM = "d6c6963b9602d1b8dd2ba53b6519e7eb19cc7940"
spec = importlib.util.spec_from_file_location("prepare_update", FORK / "ecopaste/prepare_update.py")
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class UpstreamOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        shutil.copytree(FORK / "ecopaste", self.root / "ecopaste")
        for relative in ["iroh/src/socket/transports.rs", "iroh/src/socket/transports/ip.rs"]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(["git", "-C", str(FORK), "show", f"{UNFIXED_UPSTREAM}:{relative}"]))

    def test_unfixed_upstream_receives_the_backport(self):
        self.assertEqual(update.apply_gso_patch(self.root), "backported")

    def test_upstream_with_the_fix_is_not_patched_again(self):
        patch = self.root / "ecopaste/patches/gso-live-limit.patch"
        subprocess.run(["git", "-C", str(self.root), "apply", str(patch)], check=True)
        source = self.root / "iroh/src/socket/transports.rs"
        fixed = source.read_bytes()
        self.assertEqual(update.apply_gso_patch(self.root), "upstream")
        self.assertEqual(source.read_bytes(), fixed)

    def test_conflicting_upstream_is_rejected_without_partial_patch(self):
        source = self.root / "iroh/src/socket/transports.rs"
        source.write_text(source.read_text().replace("self.sender.max_transmit_segments", "changed_upstream_limit"))
        before = source.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            update.apply_gso_patch(self.root)
        self.assertEqual(source.read_bytes(), before)

    def test_only_fork_workflows_survive_and_android_regression_is_present(self):
        update.apply_gso_patch(self.root)
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        (workflows / "upstream-release.yml").write_text("do not publish from a fork")
        update.install_overlay(self.root)
        self.assertEqual({p.name for p in workflows.iterdir()}, {"fork-check.yml", "upstream-sync.yml"})
        self.assertIn('any(target_os = "linux", target_os = "android")',
                      (self.root / "iroh/src/socket/transports.rs").read_text())
        self.assertTrue((self.root / "iroh/src/socket/transports/ecopaste_android_gso.rs").is_file())
        update.install_overlay(self.root)
        self.assertEqual((self.root / "iroh/src/socket/transports.rs").read_text().count("mod ecopaste_android_gso;"), 1)

    def test_dirty_worktree_is_rejected_before_network_or_replacement(self):
        original = update.ROOT
        update.ROOT = self.root
        try:
            with self.assertRaisesRegex(RuntimeError, "uncommitted"):
                update.prepare()
        finally:
            update.ROOT = original

    def test_tag_input_accepts_only_stable_numeric_versions(self):
        self.assertEqual(update.version("v1.4.1"), (1, 4, 1))
        for value in ["main", "v1.5.0-rc.1", "v1.4.1\nother", "--upload-pack=anything"]:
            with self.assertRaises(ValueError):
                update.version(value)


if __name__ == "__main__":
    unittest.main()
