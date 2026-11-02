"""Exercise patch carry-forward and conflict handling against real upstream files."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

FORK = Path(__file__).resolve().parents[2]
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
        upstream = json.loads((FORK / "ecopaste/upstream.json").read_text())["revision"]
        for relative in ["iroh/src/socket/transports.rs", "iroh/src/socket/transports/ip.rs"]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(["git", "-C", str(FORK), "show", f"{upstream}:{relative}"]))

    def test_backport_then_upstream_integration_is_not_applied_twice(self):
        self.assertEqual(update.apply_gso_patch(self.root), "backported")
        source = self.root / "iroh/src/socket/transports.rs"
        once = source.read_bytes()
        self.assertEqual(update.apply_gso_patch(self.root), "upstream")
        self.assertEqual(source.read_bytes(), once)

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
