import importlib.machinery
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "bin" / "hypr-shortcuts"
loader = importlib.machinery.SourceFileLoader("hypr_shortcuts", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        state_dir = Path(self.temporary_directory.name)
        cli.STATE_DIR = state_dir
        cli.DB_PATH = state_dir / "usage.sqlite3"
        cli.CATALOG_PATH = state_dir / "bindings.tsv"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_record_increments_count(self):
        cli.record("SUPER + RETURN")
        cli.record("SUPER + RETURN")
        usage = cli.load_usage()
        self.assertEqual(2, usage["SUPER + RETURN"][0])

    def test_report_includes_never_used_catalog_entries(self):
        cli.CATALOG_PATH.write_text(
            "SUPER + RETURN\tTerminal\nSUPER + K\tKeybindings\n"
        )
        cli.record("SUPER + RETURN")
        rows = {row["shortcut"]: row for row in cli.report_rows(stale_days=30)}
        self.assertEqual(1, rows["SUPER + RETURN"]["count"])
        self.assertEqual(0, rows["SUPER + K"]["count"])
        self.assertEqual("LEARN / REMOVE", rows["SUPER + K"]["review"])

    def test_stale_shortcut_is_marked_for_review(self):
        cli.CATALOG_PATH.write_text("SUPER + W\tClose window\n")
        old_timestamp = int(time.time()) - 31 * 86_400
        with cli.connect() as connection:
            connection.execute(
                "INSERT INTO usage VALUES (?, ?, ?, ?)",
                ("SUPER + W", 3, old_timestamp, old_timestamp),
            )
        row = cli.report_rows(stale_days=30)[0]
        self.assertEqual("REVIEW", row["review"])

    def test_removed_shortcut_remains_visible(self):
        cli.record("SUPER + OLD")
        row = cli.report_rows(stale_days=30)[0]
        self.assertEqual("(no longer configured)", row["description"])


if __name__ == "__main__":
    unittest.main()
