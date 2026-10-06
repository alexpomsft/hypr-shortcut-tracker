import importlib.machinery
import importlib.util
import contextlib
import io
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


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
        cli.CATALOG_PATH.write_text("")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_record_increments_count(self):
        cli.record("SUPER + RETURN")
        cli.record("SUPER + RETURN")
        usage = cli.load_usage()
        self.assertEqual(2, usage["SUPER + RETURN"][0])

    def test_version_does_not_access_history(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as caught:
                cli.build_parser().parse_args(["--version"])
        self.assertEqual(0, caught.exception.code)
        self.assertIn("0.1.0", output.getvalue())
        self.assertFalse(cli.DB_PATH.exists())

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

    def test_duplicate_catalog_keys_merge_descriptions(self):
        cli.CATALOG_PATH.write_text(
            "F9\tStart dictation\nF9\tStop dictation\nF9\tStart dictation\n"
        )
        self.assertEqual({"F9": "Start dictation / Stop dictation"}, cli.load_catalog())

    def test_malformed_catalog_is_reported(self):
        cli.CATALOG_PATH.write_text("F9 without a tab\n")
        with self.assertRaisesRegex(ValueError, "Malformed catalog entry"):
            cli.load_catalog()

    def test_missing_catalog_warns(self):
        cli.CATALOG_PATH.unlink()
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertEqual({}, cli.load_catalog())
        self.assertIn("Binding catalog missing", output.getvalue())

    def test_out_of_order_writers_preserve_timestamp_extremes(self):
        with patch.object(cli.time, "time", return_value=200):
            cli.record("SUPER + RETURN")
        with patch.object(cli.time, "time", return_value=100):
            cli.record("SUPER + RETURN")
        self.assertEqual((2, 100, 200), cli.load_usage()["SUPER + RETURN"])

    def test_reset_preserves_database_for_open_connections(self):
        cli.record("F9")
        with contextlib.closing(cli.connect()) as observer:
            with contextlib.redirect_stdout(io.StringIO()):
                cli.reset(confirmed=True)
            self.assertTrue(cli.DB_PATH.exists())
            self.assertEqual(0, observer.execute("SELECT COUNT(*) FROM usage").fetchone()[0])
            cli.record("F9")
            self.assertEqual(
                1, observer.execute("SELECT invocation_count FROM usage").fetchone()[0]
            )

    def test_reset_requires_confirmation_in_noninteractive_shell(self):
        cli.record("F9")
        with patch.object(cli.sys.stdin, "isatty", return_value=False):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(2, cli.reset(confirmed=False))
        self.assertEqual(1, cli.load_usage()["F9"][0])

    def test_report_rejects_nonpositive_thresholds(self):
        for option, value in (("--limit", "0"), ("--limit", "-1"), ("--stale-days", "0")):
            with self.subTest(option=option, value=value):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as caught:
                        cli.build_parser().parse_args(["report", option, value])
                self.assertEqual(2, caught.exception.code)

    def test_concurrent_cli_writers_lose_no_invocations(self):
        environment = dict(os.environ, XDG_STATE_HOME=str(cli.STATE_DIR))
        processes = [
            subprocess.Popen(
                [os.sys.executable, str(SCRIPT), "record", "--key", "F9"],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(24)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(0, process.returncode, stdout + stderr)
        database = cli.STATE_DIR / cli.APP_NAME / "usage.sqlite3"
        with contextlib.closing(cli.sqlite3.connect(database)) as connection:
            self.assertEqual(
                24, connection.execute("SELECT invocation_count FROM usage").fetchone()[0]
            )


if __name__ == "__main__":
    unittest.main()
