# Contributing

Small, understandable changes are welcome. This project is a CLI and an
Omarchy Lua hook, not a shell/QML plugin or a general-purpose keylogger.

## Development environment

Use Python 3.10+, Bash, and Lua 5.4 (`lua` and `luac` on `PATH`). The Python
code uses only the standard library; there is no dependency installation step.
A running Omarchy desktop is needed for live integration checks, not for tests.

```bash
python3 -m unittest discover -s tests -v
luac -p lua/shortcut_tracker.lua
luac -p tests/test_tracker.lua
bash -n install uninstall
git diff --check
```

CI runs the suite on Python 3.10, 3.12, and 3.14. The tests use temporary homes
and databases. The Lua test executes a generated recorder command against its
temporary home, including a path containing a quote; it never records into
your live database.

## Project layout

| Path | Responsibility |
| --- | --- |
| `bin/hypr-shortcuts` | SQLite recording, family rules/rollups, reports, status, reset, and CLI parsing |
| `lua/shortcut_tracker.lua` | `o.bind` adapter, logging bindings, catalog publication |
| `tools/configure.py` | Checked symlink/config installation and removal |
| `install`, `uninstall` | Bash entry points to the configuration helper |
| `tests/` | CLI, concurrent-writer, Lua, and temporary-home installation tests |

## Change guidelines

- Preserve original shortcut actions, flags, and native behavior.
- Count a shortcut once per interaction; do not reintroduce autorepeat or
  multi-action double-counting.
- Do not collect typed text, command arguments, windows, or clipboard data.
- Keep state local and preserve existing history unless the user explicitly
  requests a reset.
- Keep grouping in the reporting layer. Match known keys and descriptions
  conservatively; do not merge unrelated actions by label alone. Preserve the
  flat export schema behind `--group-by shortcut` and cover grouped exports,
  filtering, coverage, sorting, and global share calculations with tests.
- Refuse unfamiliar config edits instead of guessing. Back up and atomically
  replace config files when changes are required.
- Avoid runtime dependencies and privileged operations.
- Add regression coverage and update user-facing documentation.

If you change live integration, reload and check errors:

```bash
hyprctl reload
hyprctl configerrors
```

Verify original actions still work and invocation counts increase as intended.
Do not clear real usage history just to validate a change.

## Issues and pull requests

For bugs, include the tracker, Python, Omarchy, and Hyprland versions; expected
and observed behavior; and a minimal reproduction. Use synthetic shortcuts
and redact personal paths or descriptions.

Do not upload your usage database, full usage export, private bindings, or
credentials. Report suspected vulnerabilities privately as described in
[SECURITY.md](SECURITY.md).

For releases, keep the CLI `VERSION`, changelog entry, and Git tag consistent.
Tag the reviewed commit, then publish notes covering compatibility and any
changes to data or counting semantics.
