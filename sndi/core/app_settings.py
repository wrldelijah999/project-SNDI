from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from sndi.core.app_paths import (
    ensure_runtime_dirs,
    get_runtime_memory_dir,
    get_legacy_memory_dir,
)


APP_SETTINGS_FILENAME = "app_settings.json"
APP_SETTINGS_PATH = get_runtime_memory_dir() / APP_SETTINGS_FILENAME
LEGACY_APP_SETTINGS_PATH = get_legacy_memory_dir() / APP_SETTINGS_FILENAME


DEFAULT_APP_SETTINGS: dict[str, Any] = {
    "voice_enabled": False,
    "voice_wake_word": "сенді",
    "voice_reply_enabled": False,
    "tray_enabled": True,
    "minimize_to_tray": True,
    "autostart_enabled": False,
}


def _copy_defaults() -> dict[str, Any]:
    return dict(DEFAULT_APP_SETTINGS)


def _load_settings_from_path(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None

        raw = path.read_text(encoding="utf-8").strip()

        if not raw:
            return None

        loaded = json.loads(raw)

        if not isinstance(loaded, dict):
            return None

        settings = _copy_defaults()
        settings.update(loaded)

        return settings

    except Exception as error:
        print(f"[SNDI][APP SETTINGS LOAD ERROR] {path}: {error}")
        return None


def load_app_settings() -> dict[str, Any]:
    """
    Load local app settings.

    v1.11 behavior:
    - primary path: %APPDATA%/SNDI/memory/app_settings.json
    - legacy fallback: project_root/memory/app_settings.json
    - if legacy exists and runtime file does not, copy settings to AppData
    - broken JSON -> defaults
    """
    ensure_runtime_dirs()

    runtime_settings = _load_settings_from_path(APP_SETTINGS_PATH)

    if runtime_settings is not None:
        return runtime_settings

    legacy_settings = _load_settings_from_path(LEGACY_APP_SETTINGS_PATH)

    if legacy_settings is not None:
        try:
            save_app_settings(legacy_settings)
            print(
                "[SNDI][APP SETTINGS] migrated legacy settings to runtime AppData"
            )
        except Exception as error:
            print("[SNDI][APP SETTINGS MIGRATION ERROR]", error)

        return legacy_settings

    return _copy_defaults()


def save_app_settings(settings: dict[str, Any]) -> None:
    """
    Save local app settings as UTF-8 JSON.
    """
    ensure_runtime_dirs()

    normalized = _copy_defaults()
    normalized.update(settings or {})

    APP_SETTINGS_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_app_setting(key: str, default: Any = None) -> Any:
    settings = load_app_settings()
    return settings.get(key, default)


def set_app_setting(key: str, value: Any) -> dict[str, Any]:
    settings = load_app_settings()
    settings[key] = value
    save_app_settings(settings)
    return settings


def update_app_settings(**kwargs: Any) -> dict[str, Any]:
    settings = load_app_settings()
    settings.update(kwargs)
    save_app_settings(settings)
    return settings


def reset_app_settings() -> dict[str, Any]:
    settings = _copy_defaults()
    save_app_settings(settings)
    return settings


def get_app_settings_path() -> Path:
    return APP_SETTINGS_PATH