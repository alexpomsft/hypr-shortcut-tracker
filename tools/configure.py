import datetime as dt
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


BOOTSTRAP = (
    'dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") '
    '.. "/default/hypr/bootstrap.lua")'
)
REQUIRE_PATTERN = re.compile(
    r"""^\s*local\s+shortcut_tracker\s*=\s*require\s*\(\s*["']hypr\.shortcut_tracker["']\s*\)\s*(?:--.*)?$"""
)
CALL_PATTERN = re.compile(
    r"^\s*shortcut_tracker\s*\.\s*(start|finish)\s*\(\s*\)\s*(?:--.*)?$"
)


def integration_lines(text: str) -> dict[str, int]:
    found = {}
    for index, line in enumerate(text.splitlines(keepends=True)):
        if line.lstrip().startswith("--"):
            continue
        if "shortcut_tracker" not in line:
            continue
        if REQUIRE_PATTERN.fullmatch(line.rstrip("\n")):
            kind = "require"
        else:
            match = CALL_PATTERN.fullmatch(line.rstrip("\n"))
            if not match:
                raise ValueError(
                    f"Unrecognized tracker integration at line {index + 1}; "
                    "leaving config and installed files untouched."
                )
            kind = match[1]
        if kind in found:
            raise ValueError(f"Duplicate tracker {kind} line; leaving installation untouched.")
        found[kind] = index
    if found and (
        set(found) != {"require", "start", "finish"}
        or not found["require"] < found["start"] < found["finish"]
    ):
        raise ValueError("Incomplete tracker integration; leaving installation untouched.")
    return found


def check_link(target: Path, source: Path) -> None:
    if target.is_symlink():
        if target.resolve() != source:
            raise ValueError(f"Refusing to replace or remove an unrelated symlink: {target}")
    elif target.exists():
        raise ValueError(f"Refusing to replace or remove an existing file: {target}")


def write_config(path: Path, text: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(path, path.with_name(f"{path.name}.backup-shortcut-tracker-{timestamp}"))
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
        temporary_path.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def configure(action: str, repo: Path) -> None:
    home = Path.home()
    config = (home / ".config/hypr/hyprland.lua").resolve(strict=True)
    text = config.read_text(encoding="utf-8")
    found = integration_lines(text)
    links = {
        home / ".local/bin/hypr-shortcuts": repo / "bin/hypr-shortcuts",
        home / ".config/hypr/shortcut_tracker.lua": repo / "lua/shortcut_tracker.lua",
    }
    for target, source in links.items():
        check_link(target, source)

    if action == "install":
        if not found:
            if text.count(BOOTSTRAP) != 1:
                raise ValueError("Could not find a unique Omarchy bootstrap line in hyprland.lua.")
            text = text.replace(
                BOOTSTRAP,
                BOOTSTRAP
                + '\n\nrequire("default.hypr.helpers")\n'
                + 'local shortcut_tracker = require("hypr.shortcut_tracker")\n'
                + "shortcut_tracker.start()",
                1,
            ).rstrip() + "\n\nshortcut_tracker.finish()\n"
        created = []
        try:
            for target, source in links.items():
                if not source.is_file():
                    raise ValueError(f"Missing tracker source file: {source}")
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.is_symlink():
                    target.symlink_to(source)
                    created.append(target)
            if not found:
                write_config(config, text)
        except (OSError, ValueError):
            for target in created:
                target.unlink()
            raise
        print("Installed Hypr Shortcut Tracker.")
    else:
        if found:
            lines = text.splitlines(keepends=True)
            text = "".join(line for index, line in enumerate(lines) if index not in found.values())
            write_config(config, text)
        for target in links:
            if target.is_symlink():
                target.unlink()
        print("Uninstalled Hypr Shortcut Tracker. Usage history was kept.")
    print("Run: hyprctl reload && hyprctl configerrors")


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in {"install", "uninstall"}:
            raise ValueError("Usage: configure.py {install|uninstall} REPOSITORY")
        configure(sys.argv[1], Path(sys.argv[2]).resolve(strict=True))
    except (OSError, ValueError) as error:
        print(f"shortcut tracker: {error}", file=sys.stderr)
        raise SystemExit(1)
