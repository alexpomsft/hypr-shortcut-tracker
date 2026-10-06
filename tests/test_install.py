import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).parents[1]
BOOTSTRAP = (
    'dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") '
    '.. "/default/hypr/bootstrap.lua")'
)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary_directory.name)
        self.config = self.home / ".config/hypr/hyprland.lua"
        self.config.parent.mkdir(parents=True)
        self.original = BOOTSTRAP + '\nrequire("default.hypr.omarchy")\n'
        self.config.write_text(self.original)
        self.binary = self.home / ".local/bin/hypr-shortcuts"
        self.module = self.home / ".config/hypr/shortcut_tracker.lua"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_action(self, action):
        return subprocess.run(
            [str(REPO / action)],
            env=dict(os.environ, HOME=str(self.home)),
            capture_output=True,
            text=True,
            timeout=20,
        )

    def install(self):
        result = self.run_action("install")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue(self.binary.is_symlink())
        self.assertTrue(self.module.is_symlink())

    def test_install_is_idempotent(self):
        self.install()
        text = self.config.read_text()
        backups = list(self.config.parent.glob("*.backup-shortcut-tracker-*"))
        self.install()
        self.assertEqual(text, self.config.read_text())
        self.assertEqual(backups, list(self.config.parent.glob("*.backup-shortcut-tracker-*")))

    def test_uninstall_accepts_reformatted_integration_and_keeps_history(self):
        self.install()
        history = self.home / ".local/state/hypr-shortcut-tracker/usage.sqlite3"
        history.parent.mkdir(parents=True)
        history.write_bytes(b"private history sentinel")
        text = self.config.read_text()
        text = text.replace(
            'local shortcut_tracker = require("hypr.shortcut_tracker")',
            "  local shortcut_tracker=require ( 'hypr.shortcut_tracker' ) -- tracker",
        ).replace("shortcut_tracker.start()", "  shortcut_tracker . start ( )")
        self.config.write_text(text)
        result = self.run_action("uninstall")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("shortcut_tracker", self.config.read_text())
        self.assertIn('require("default.hypr.omarchy")', self.config.read_text())
        self.assertEqual(b"private history sentinel", history.read_bytes())
        self.assertFalse(self.binary.is_symlink())
        self.assertFalse(self.module.is_symlink())
        self.assertIn("hyprctl reload", result.stdout)

    def test_uninstall_refuses_unknown_references_before_removing_links(self):
        self.install()
        text = self.config.read_text() + "\nshortcut_tracker.custom_action()\n"
        self.config.write_text(text)
        result = self.run_action("uninstall")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Unrecognized tracker integration", result.stderr)
        self.assertEqual(text, self.config.read_text())
        self.assertTrue(self.binary.is_symlink())
        self.assertTrue(self.module.is_symlink())

    def test_uninstall_refuses_partial_integration(self):
        self.install()
        text = self.config.read_text().replace("shortcut_tracker.finish()", "")
        self.config.write_text(text)
        result = self.run_action("uninstall")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(text, self.config.read_text())
        self.assertTrue(self.module.is_symlink())

    def test_install_refuses_unrelated_files_without_config_changes(self):
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text("unrelated command")
        result = self.run_action("install")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("unrelated command", self.binary.read_text())
        self.assertEqual(self.original, self.config.read_text())
        self.assertFalse(self.module.is_symlink())

    def test_install_checks_bootstrap_before_creating_links(self):
        self.config.write_text("-- unrelated config\n")
        result = self.run_action("install")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(self.binary.is_symlink())
        self.assertFalse(self.module.is_symlink())

    def test_uninstall_refuses_unrelated_symlinks(self):
        self.install()
        self.binary.unlink()
        self.binary.symlink_to(self.home / "unrelated")
        text = self.config.read_text()
        result = self.run_action("uninstall")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(text, self.config.read_text())
        self.assertTrue(self.module.is_symlink())
