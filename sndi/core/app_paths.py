from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import sys


APP_NAME = "SNDI"


def is_frozen() -> bool:
    """
    True when app is running as a PyInstaller executable.
    False when running in dev mode via python run.py.
    """
    return bool(getattr(sys, "frozen", False))


def get_executable_path() -> Path:
    """
    Current executable:
    - dev mode: python.exe / pythonw.exe
    - frozen mode: SNDI.exe
    """
    return Path(sys.executable).resolve()


def get_project_root() -> Path:
    """
    Dev mode:
        C:\\SNDI project

    Frozen mode:
        folder that contains SNDI.exe, usually dist/SNDI
    """
    if is_frozen():
        return get_executable_path().parent

    return Path(__file__).resolve().parents[2]


def get_bundle_root() -> Path:
    """
    Resource root.

    In dev mode it is the project root.
    In PyInstaller mode it is sys._MEIPASS when available.
    """
    if is_frozen():
        mei_pass = getattr(sys, "_MEIPASS", None)

        if mei_pass:
            return Path(mei_pass).resolve()

        return get_project_root()

    return get_project_root()


def get_legacy_memory_dir() -> Path:
    """
    Old dev memory directory used before v1.11.
    Kept for compatibility and migration.
    """
    return get_project_root() / "memory"


def get_app_data_dir() -> Path:
    """
    User-level runtime app directory:
    %APPDATA%\\SNDI

    No admin rights required.
    """
    appdata = os.environ.get("APPDATA")

    if appdata:
        return Path(appdata).resolve() / APP_NAME

    # Fallback for unusual environments.
    return Path.home() / "AppData" / "Roaming" / APP_NAME


def get_runtime_memory_dir() -> Path:
    return get_app_data_dir() / "memory"


def get_runtime_logs_dir() -> Path:
    return get_app_data_dir() / "logs"


def get_runtime_safe_trash_dir() -> Path:
    return get_app_data_dir() / "safe_trash"


def get_runtime_file_backups_dir() -> Path:
    return get_app_data_dir() / "file_backups"


def resource_path(relative_path: str | Path) -> Path:
    """
    Resolve bundled resource path.

    Works both in dev mode and frozen PyInstaller mode.
    Example:
        resource_path("assets/images/avatar.png")
    """
    return get_bundle_root() / Path(relative_path)


def ensure_runtime_dirs() -> None:
    """
    Create runtime directories used by installed/app mode.
    """
    get_app_data_dir().mkdir(parents=True, exist_ok=True)
    get_runtime_memory_dir().mkdir(parents=True, exist_ok=True)
    get_runtime_logs_dir().mkdir(parents=True, exist_ok=True)
    get_runtime_safe_trash_dir().mkdir(parents=True, exist_ok=True)
    get_runtime_file_backups_dir().mkdir(parents=True, exist_ok=True)


def get_runtime_status() -> dict[str, Any]:
    """
    Human/debug friendly runtime status.
    Safe to print in CLI tests and show in future app status command.
    """
    ensure_runtime_dirs()

    return {
        "app_name": APP_NAME,
        "mode": "frozen_exe" if is_frozen() else "dev",
        "is_frozen": is_frozen(),
        "executable_path": str(get_executable_path()),
        "project_root": str(get_project_root()),
        "bundle_root": str(get_bundle_root()),
        "app_data_dir": str(get_app_data_dir()),
        "runtime_memory_dir": str(get_runtime_memory_dir()),
        "runtime_logs_dir": str(get_runtime_logs_dir()),
        "runtime_safe_trash_dir": str(get_runtime_safe_trash_dir()),
        "runtime_file_backups_dir": str(get_runtime_file_backups_dir()),
        "legacy_memory_dir": str(get_legacy_memory_dir()),
    }