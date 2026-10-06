import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from contextlib import closing


REPO = Path(__file__).parents[1]


class LuaTests(unittest.TestCase):
    def test_adapter_with_stubbed_hyprland(self):
        with tempfile.TemporaryDirectory(prefix="shortcut-test-'") as home:
            binary = Path(home) / ".local/bin/hypr-shortcuts"
            binary.parent.mkdir(parents=True)
            binary.symlink_to(REPO / "bin/hypr-shortcuts")
            result = subprocess.run(
                ["lua", str(REPO / "tests/test_tracker.lua"), str(REPO), home],
                env=dict(os.environ, HOME=home, XDG_STATE_HOME=home + "/state"),
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            database = Path(home) / "state/hypr-shortcut-tracker/usage.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    [("XF86AudioRaiseVolume", 1)],
                    connection.execute("SELECT shortcut, invocation_count FROM usage").fetchall(),
                )
