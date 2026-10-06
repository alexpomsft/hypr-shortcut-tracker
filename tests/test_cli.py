import importlib.machinery
import importlib.util
import contextlib
import io
import csv
import json
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
        self.assertIn("0.2.0", output.getvalue())
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

    def write_bindings(self, bindings):
        cli.CATALOG_PATH.write_text(
            "".join(f"{shortcut}\t{description}\n" for shortcut, description in bindings)
        )

    def seed_usage(self, shortcut, count, first_used, last_used):
        with contextlib.closing(cli.connect()) as connection, connection:
            connection.execute(
                "INSERT INTO usage VALUES (?, ?, ?, ?)",
                (shortcut, count, first_used, last_used),
            )

    def run_report(self, *flags):
        args = cli.build_parser().parse_args(["report", *flags])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(0, cli.report(args))
        return output.getvalue()

    def test_family_rules_cover_exactly_ten_nonoverlapping_families(self):
        expected = {
            "workspace-switch": 10,
            "workspace-move-window": 10,
            "workspace-move-window-silent": 10,
            "group-window-select": 5,
            "bar-panel-open": 9,
            "window-focus-direction": 4,
            "window-swap-direction": 4,
            "workspace-move-monitor": 4,
            "window-move-group": 4,
            "window-resize-keyboard": 12,
        }
        actual = {}
        for family in cli.FAMILY_BINDINGS.values():
            actual[family] = actual.get(family, 0) + 1
        self.assertEqual(expected, actual)
        self.assertEqual(72, len(cli.FAMILY_BINDINGS))

    def test_family_rules_require_matching_keys_and_descriptions(self):
        examples = (
            ("SUPER + code:10", "Custom action"),
            ("SUPER + Q", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 1"),
            ("SUPER + CTRL + ALT + D", "Calendar"),
            ("SUPER + SHIFT + C", "Calendar"),
            ("SUPER + code:10", "Switch to workspace 1 / Custom action"),
        )
        for shortcut, description in examples:
            with self.subTest(shortcut=shortcut, description=description):
                self.assertIsNone(cli.family_for(shortcut, description))
        self.assertEqual(
            "workspace-move-window-silent",
            cli.family_for("SHIFT+super+ALT+code:10", "Move window silently to workspace 1"),
        )
        self.assertEqual(
            "window-resize-keyboard",
            cli.family_for("SUPER + CTRL + SHIFT + code:20", "Shrink window up a lot"),
        )

    def test_grouping_collapses_members_without_losing_total_counts(self):
        self.write_bindings([
            *cli.FAMILY_BINDINGS.keys(),
            ("SUPER + RETURN", "Terminal"),
        ])
        for shortcut, _ in cli.FAMILY_BINDINGS:
            self.seed_usage(shortcut, 1, 100, 200)
        rows = json.loads(self.run_report("--format", "json"))
        self.assertEqual(11, len(rows))
        self.assertEqual(72, sum(row["count"] for row in rows))
        self.assertEqual(73, sum(row["binding_count"] for row in rows))
        self.assertEqual(10, len({row["family_id"] for row in rows if row["family_id"]}))

    def test_family_rollup_uses_sum_extrema_and_member_coverage(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
            ("SUPER + code:12", "Switch to workspace 3"),
            ("SUPER + RETURN", "Terminal"),
        ])
        now = int(time.time())
        self.seed_usage("SUPER + code:10", 7, now - 1000, now - 300)
        self.seed_usage("SUPER + code:11", 3, now - 500, now - 10)
        self.seed_usage("SUPER + RETURN", 10, now - 100, now - 20)
        family = next(
            row for row in json.loads(self.run_report("--format", "json"))
            if row["family_id"] == "workspace-switch"
        )
        self.assertEqual(10, family["count"])
        self.assertEqual(50.0, family["share_percent"])
        self.assertEqual(cli.iso_time(now - 1000), family["first_used"])
        self.assertEqual(cli.iso_time(now - 10), family["last_used"])
        self.assertEqual("just now", family["last_used_relative"])
        self.assertEqual((2, 3), (family["used_bindings"], family["binding_count"]))
        self.assertEqual("", family["review"])
        self.assertEqual("", family["shortcut"])

    def test_family_share_is_recomputed_not_sum_of_rounded_members(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
            ("SUPER + RETURN", "Terminal"),
        ])
        for shortcut in ("SUPER + code:10", "SUPER + code:11", "SUPER + RETURN"):
            self.seed_usage(shortcut, 1, 100, 200)
        family = next(
            row for row in json.loads(self.run_report("--format", "json"))
            if row["family_id"]
        )
        self.assertEqual(66.7, family["share_percent"])

    def test_never_used_family_and_singleton_remain_visible(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
            ("SUPER + RETURN", "Terminal"),
        ])
        rows = json.loads(self.run_report("--format", "json"))
        self.assertEqual(2, len(rows))
        family = next(row for row in rows if row["family_id"])
        self.assertEqual("NEVER", family["last_used_relative"])
        self.assertEqual("", family["first_used"])
        self.assertEqual("", family["last_used"])
        self.assertEqual("LEARN / REMOVE", family["review"])
        self.assertEqual((0, 2), (family["used_bindings"], family["binding_count"]))
        singleton = next(row for row in rows if not row["family_id"])
        self.assertEqual("SUPER + RETURN", singleton["shortcut"])
        self.assertEqual(1, singleton["binding_count"])

    def test_family_review_uses_most_recent_used_member(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
        ])
        now = int(time.time())
        self.seed_usage("SUPER + code:10", 1, now - 40 * 86400, now - 31 * 86400)
        self.seed_usage("SUPER + code:11", 1, now - 40 * 86400, now - 29 * 86400)
        row = json.loads(self.run_report("--format", "json", "--stale-days", "30"))[0]
        self.assertEqual("", row["review"])
        row = json.loads(self.run_report("--format", "json", "--stale-days", "28"))[0]
        self.assertEqual("REVIEW", row["review"])

    def test_removed_bindings_do_not_inflate_family_coverage(self):
        self.write_bindings([("SUPER + code:10", "Switch to workspace 1")])
        self.seed_usage("SUPER + code:11", 5, 100, 200)
        rows = json.loads(self.run_report("--format", "json"))
        family = next(row for row in rows if row["family_id"])
        removed = next(row for row in rows if not row["family_id"])
        self.assertEqual((0, 1), (family["used_bindings"], family["binding_count"]))
        self.assertEqual("(no longer configured)", removed["description"])
        self.assertEqual(5, removed["count"])

    def test_flat_json_and_csv_keep_previous_export_schema(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
        ])
        fields = [
            "shortcut", "description", "count", "share_percent", "first_used",
            "last_used", "last_used_relative", "review",
        ]
        rows = json.loads(self.run_report("--group-by", "shortcut", "--format", "json"))
        self.assertEqual(2, len(rows))
        self.assertEqual(set(fields), set(rows[0]))
        reader = csv.DictReader(io.StringIO(
            self.run_report("--group-by", "shortcut", "--format", "csv")
        ))
        self.assertEqual(fields, reader.fieldnames)
        self.assertEqual(2, len(list(reader)))

    def test_grouped_csv_and_json_share_schema_even_when_empty(self):
        fields = [
            "shortcut", "description", "count", "share_percent", "first_used",
            "last_used", "last_used_relative", "review",
            "family_id", "used_bindings", "binding_count",
        ]
        self.write_bindings([("SUPER + code:10", "Switch to workspace 1")])
        row = json.loads(self.run_report("--format", "json"))[0]
        self.assertEqual(set(fields), set(row))
        reader = csv.DictReader(io.StringIO(self.run_report("--format", "csv")))
        self.assertEqual(fields, reader.fieldnames)
        self.assertEqual("workspace-switch", list(reader)[0]["family_id"])
        self.write_bindings([])
        reader = csv.DictReader(io.StringIO(self.run_report("--format", "csv")))
        self.assertEqual(fields, reader.fieldnames)
        self.assertEqual([], list(reader))

    def test_family_filter_drills_down_and_keeps_global_shares(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
            ("SUPER + RETURN", "Terminal"),
        ])
        self.seed_usage("SUPER + code:10", 2, 100, 200)
        self.seed_usage("SUPER + RETURN", 2, 100, 200)
        rows = json.loads(self.run_report("--family", "workspace-switch", "--format", "json"))
        self.assertEqual(2, len(rows))
        self.assertNotIn("family_id", rows[0])
        self.assertEqual(50.0, rows[0]["share_percent"])
        rows = json.loads(self.run_report(
            "--family", "workspace-switch", "--group-by", "family", "--format", "json"
        ))
        self.assertEqual(1, len(rows))
        self.assertEqual(50.0, rows[0]["share_percent"])

    def test_grouping_happens_before_sorting_and_limiting(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
            ("SUPER + RETURN", "Terminal"),
        ])
        self.seed_usage("SUPER + code:10", 6, 100, 200)
        self.seed_usage("SUPER + code:11", 6, 100, 300)
        self.seed_usage("SUPER + RETURN", 10, 100, 250)
        for order in ("frequency", "recent"):
            with self.subTest(order=order):
                rows = json.loads(self.run_report(
                    "--format", "json", "--sort", order, "--limit", "1"
                ))
                self.assertEqual("workspace-switch", rows[0]["family_id"])
        rows = json.loads(self.run_report("--format", "json", "--sort", "review"))
        self.assertEqual("", rows[0]["family_id"])

    def test_family_table_shows_coverage_and_flat_table_does_not(self):
        self.write_bindings([
            ("SUPER + code:10", "Switch to workspace 1"),
            ("SUPER + code:11", "Switch to workspace 2"),
        ])
        output = self.run_report()
        self.assertIn("COVERAGE", output)
        self.assertIn("0/2 used", output)
        self.assertIn("workspace-switch", output)
        self.assertNotIn("COVERAGE", self.run_report("--group-by", "shortcut"))

    def test_unknown_family_is_an_error_and_absent_family_is_explicit(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.build_parser().parse_args(["report", "--family", "typo"])
        self.assertEqual(2, caught.exception.code)
        self.assertIn("No configured bindings match", self.run_report("--family", "workspace-switch"))
        self.assertEqual(
            [], json.loads(self.run_report("--family", "workspace-switch", "--format", "json"))
        )

    def test_grouping_does_not_change_storage_and_reset_keeps_catalog(self):
        self.write_bindings([("SUPER + code:10", "Switch to workspace 1")])
        cli.record("SUPER + code:10")
        before = cli.load_usage()
        self.run_report("--format", "json")
        self.assertEqual(before, cli.load_usage())
        catalog = cli.CATALOG_PATH.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            cli.reset(confirmed=True)
        self.assertEqual(catalog, cli.CATALOG_PATH.read_bytes())
        row = json.loads(self.run_report("--format", "json"))[0]
        self.assertEqual(0, row["count"])
        self.assertEqual("workspace-switch", row["family_id"])


if __name__ == "__main__":
    unittest.main()
