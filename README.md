# Hypr Shortcut Tracker

Local shortcut analytics for Omarchy's Lua-based Hyprland configuration.

It records only the configured shortcut and invocation time. It does not log
ordinary keystrokes, typed text, active windows, or command arguments.

## What it shows

- Invocation count and percentage of all shortcut usage
- Relative and absolute last-used time
- Current bindings that have never been used
- Review hints for shortcuts that are unused or stale

Data stays in `~/.local/state/hypr-shortcut-tracker/usage.sqlite3`.

## Install

```bash
./install
hyprctl reload
hyprctl configerrors
```

The installer creates:

- `~/.local/bin/hypr-shortcuts`
- `~/.config/hypr/shortcut_tracker.lua`
- A small integration block in `~/.config/hypr/hyprland.lua`

The files in `~/.local/bin` and `~/.config/hypr` are symlinks to this checkout,
so repository updates apply immediately.

## Reports

```bash
# Highest-frequency shortcuts first
hypr-shortcuts report

# Most recently used first
hypr-shortcuts report --sort recent

# Never-used and stale shortcuts first
hypr-shortcuts report --sort review --stale-days 30

# Machine-readable output
hypr-shortcuts report --format json
hypr-shortcuts report --format csv
```

`NEVER` means the shortcut has not been used since the tracker was installed,
not that it was never used before installation.

## Maintenance

```bash
hypr-shortcuts status
hypr-shortcuts reset
./uninstall
```

`reset` asks for confirmation unless `--yes` is supplied. Uninstalling keeps
the SQLite history by default.

## How it works

The Lua adapter wraps Omarchy's public `o.bind` helper during configuration
loading. Each shortcut gets a second Hyprland action that records the
invocation asynchronously, while the original action remains unchanged.
Bindings with multiple actions are counted once per trigger.

The adapter also writes the current binding catalog on each successful config
load. Reports join that catalog with SQLite usage totals, which makes unused
shortcuts visible.

