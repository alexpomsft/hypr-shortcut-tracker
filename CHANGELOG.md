# Changelog

## 0.1.0 - 2026-10-06

First public release of the local-first Omarchy/Hyprland shortcut tracker.

### Features

- Count invocations of shortcuts registered through Omarchy's `o.bind`.
- Report share of total usage and relative or exact last-used time.
- Include current shortcuts with no recorded usage and stale-review hints.
- Export reports as JSON or CSV; retain history for removed key strings.
- Keep data in local SQLite with no tracker daemon or network requests.
- Install and uninstall using checked symlinks and backed-up config edits.

### Reliability

- Count held repeating keys once per press without changing native autorepeat.
- Deduplicate multi-action, press/release, and ordinary/long-press combinations.
- Merge action descriptions rather than overwrite duplicate catalog entries.
- Prefer ordinary presses regardless of registration order.
- Rebuild the catalog and avoid wrapper stacking on configuration reload.
- Preserve timestamp extrema across concurrent recording processes.
- Reset usage in a transaction without deleting an active database.
- Refuse unrelated file replacements and unknown/partial config integrations.

### Compatibility and data

Live-tested on Omarchy 4.0.4 and Hyprland 0.56.2. Requires Omarchy's Lua config
and Python 3.10+; legacy `.conf` configurations are unsupported.

Pre-release aggregate history is preserved. Counts recorded before the
autorepeat and press/release fixes may be inflated and cannot be reconstructed
reliably from aggregate rows.
