from __future__ import annotations

from pathlib import Path
import os

from sndi.core.app_paths import is_frozen
from sndi.tools.windows_shortcuts import get_shortcut_launch_parts


AUTOSTART_FILENAME = "SNDI.cmd"


def get_startup_folder() -> Path:
    """
    User-level Windows Startup folder.
    Does not require admin rights.
    """
    appdata = os.environ.get("APPDATA")

    if not appdata:
        raise RuntimeError("APPDATA environment variable is not available")

    return (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def get_autostart_file_path() -> Path:
    return get_startup_folder() / AUTOSTART_FILENAME


def _build_cmd_content() -> str:
    """
    Build Startup .cmd content.

    v1.11 behavior:
    - if running frozen exe: launch current SNDI.exe;
    - if dist/SNDI/SNDI.exe exists in dev project: launch built exe;
    - fallback: launch pythonw/python run.py.
    """
    target, arguments, working_dir = get_shortcut_launch_parts()

    if arguments:
        launch_line = f'start "" "{target}" {arguments}'
    else:
        launch_line = f'start "" "{target}"'

    return (
        "@echo off\n"
        f'cd /d "{working_dir}"\n'
        f"{launch_line}\n"
    )


def enable_autostart(project_root: str | Path | None = None) -> str:
    """
    Enable SNDI autostart by creating SNDI.cmd in user's Startup folder.

    project_root is kept for backward compatibility with v1.10 calls,
    but v1.11 resolves launch target automatically.
    """
    startup_folder = get_startup_folder()
    startup_folder.mkdir(parents=True, exist_ok=True)

    autostart_file = get_autostart_file_path()
    autostart_file.write_text(
        _build_cmd_content(),
        encoding="utf-8",
    )

    return f"автозапуск увімкнено: {autostart_file}"


def disable_autostart() -> str:
    """
    Disable SNDI autostart by deleting SNDI.cmd from Startup folder.
    """
    autostart_file = get_autostart_file_path()

    if not autostart_file.exists():
        return "автозапуск уже вимкнено."

    autostart_file.unlink()
    return "автозапуск вимкнено."


def is_autostart_enabled() -> bool:
    return get_autostart_file_path().exists()


def get_autostart_status() -> str:
    autostart_file = get_autostart_file_path()
    target, arguments, working_dir = get_shortcut_launch_parts()

    mode = "frozen_exe" if is_frozen() else "dev"

    if autostart_file.exists():
        return (
            "автозапуск активний:\n"
            f"- file: {autostart_file}\n"
            f"- mode: {mode}\n"
            f"- target: {target}\n"
            f"- arguments: {arguments or '(none)'}\n"
            f"- working dir: {working_dir}"
        )

    return (
        "автозапуск вимкнено.\n"
        f"- mode: {mode}\n"
        f"- next target: {target}\n"
        f"- arguments: {arguments or '(none)'}\n"
        f"- working dir: {working_dir}"
    )


def read_autostart_file() -> str:
    """
    Debug helper for tests.
    """
    autostart_file = get_autostart_file_path()

    if not autostart_file.exists():
        return ""

    return autostart_file.read_text(encoding="utf-8", errors="replace")