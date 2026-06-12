from __future__ import annotations

from pathlib import Path
from typing import Any
import json


MEMORY_DIR = Path("memory")
APP_SETTINGS_PATH = MEMORY_DIR / "app_settings.json"


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


def load_app_settings() -> dict[str, Any]:
    """
    Load local app settings.

    Safe behavior:
    - missing file -> defaults
    - empty file -> defaults
    - broken JSON -> defaults
    - unknown keys are preserved
    - missing default keys are added
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    if not APP_SETTINGS_PATH.exists():
        return _copy_defaults()

    try:
        raw = APP_SETTINGS_PATH.read_text(encoding="utf-8").strip()

        if not raw:
            return _copy_defaults()

        loaded = json.loads(raw)

        if not isinstance(loaded, dict):
            return _copy_defaults()

        settings = _copy_defaults()
        settings.update(loaded)

        return settings

    except Exception as error:
        print("[SNDI][APP SETTINGS LOAD ERROR]", error)
        return _copy_defaults()


def save_app_settings(settings: dict[str, Any]) -> None:
    """
    Save local app settings as UTF-8 JSON.
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

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