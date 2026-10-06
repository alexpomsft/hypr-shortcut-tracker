# Security policy

## Supported releases

Report issues against the latest published release or current `main`. This is
an independent community project; older revisions may not receive backports.

## Report a vulnerability

Use GitHub's
[private vulnerability reporting](https://github.com/alexpomsft/hypr-shortcut-tracker/security/advisories/new)
instead of a public issue for suspected vulnerabilities.

Include affected versions, a minimal reproduction using synthetic bindings,
the impact, and any suggested fix. Do not include secrets, personal usage
databases, clipboard data, or private command arguments.

## Trust and privacy boundaries

Installation modifies your user-owned Hyprland config and registers additional
logging actions. The Lua adapter executes inside Hyprland, and the CLI runs
with your user account's permissions. Read the source before installing.

The tracker requires no root access, opens no network connections, and does
not log ordinary keys or typed text. It stores configured shortcut strings,
descriptions, counts, and first/last timestamps in local state files.
Those files and exported reports can still reveal personal usage habits.

The installer refuses unrelated files and unrecognized integrations, creates
timestamped backups for config edits, and does not edit packaged Omarchy
files. These checks are safeguards, not a sandbox or security guarantee.
