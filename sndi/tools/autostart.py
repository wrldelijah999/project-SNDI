from __future__ import annotations

from pathlib import Path
import os
import sys


AUTOSTART_FILENAME = "SNDI.cmd"


def get_project_root() -> Path:
    """
    Resolve project root from this file:
    sndi/tools/autostart.py -> project root is parents[2].
    """
    return Path(__file__).resolve().parents[2]


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


def _resolve_python_executable() -> Path:
    """
    Prefer pythonw.exe to avoid opening a console window on Windows.
    Fallback to current python executable.
    """
    current = Path(sys.executable).resolve()
    pythonw = current.with_name("pythonw.exe")

    if pythonw.exists():
        return pythonw

    return current


def _build_cmd_content(project_root: Path) -> str:
    python_exe = _resolve_python_executable()
    run_py = project_root / "run.py"

    return (
        "@echo off\n"
        f'cd /d "{project_root}"\n'
        f'start "" "{python_exe}" "{run_py}"\n'
    )


def enable_autostart(project_root: str | Path | None = None) -> str:
    """
    Enable SNDI autostart by creating SNDI.cmd in user's Startup folder.
    """
    root = Path(project_root).resolve() if project_root else get_project_root()
    run_py = root / "run.py"

    if not run_py.exists():
        return f"не змогла увімкнути автозапуск: не знайдено run.py у {root}"

    startup_folder = get_startup_folder()
    startup_folder.mkdir(parents=True, exist_ok=True)

    autostart_file = get_autostart_file_path()
    autostart_file.write_text(
        _build_cmd_content(root),
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

    if autostart_file.exists():
        return f"автозапуск активний: {autostart_file}"

    return "автозапуск вимкнено."