# sndi/tools/app_registry.py
"""
SNDI V1.7 — App Registry.

Soft aliases for apps, games, sites and common folders.

This is not the brain.
This is the local target map that helps system_control understand user slang.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _home() -> str:
    return str(Path.home())


def _downloads() -> str:
    return str(Path.home() / "Downloads")


def _desktop() -> str:
    return str(Path.home() / "Desktop")


def _documents() -> str:
    return str(Path.home() / "Documents")


def _music() -> str:
    return str(Path.home() / "Music")


def _pictures() -> str:
    return str(Path.home() / "Pictures")


def _videos() -> str:
    return str(Path.home() / "Videos")


def _appdata_sndi() -> str:
    appdata = os.getenv("APPDATA") or _home()
    return str(Path(appdata) / "SNDI")


def _sndi_project() -> str:
    return r"C:\SNDI project"


APP_ALIASES: dict[str, dict] = {
    # ---------- games ----------
    "counter_strike_2": {
        "type": "steam",
        "steam_id": "730",
        "display_name": "Counter-Strike 2",
        "aliases": [
            "counter strike",
            "counter-strike",
            "counter strike 2",
            "counter-strike 2",
            "cs",
            "cs2",
            "csgo",
            "кс",
            "кс2",
            "ксочка",
            "кс-ка",
            "csку",
            "cs ку",
            "контра",
            "контру",
            "каес",
            "каеска",
            "в контру",
            "в кс",
            "погнали в кс",
            "го в кс",
            "го кс",
        ],
    },

    "steam": {
        "type": "app",
        "display_name": "Steam",
        "aliases": [
            "steam",
            "стім",
            "стим",
        ],
        "possible_paths": [
            r"C:\Program Files (x86)\Steam\steam.exe",
            r"C:\Program Files\Steam\steam.exe",
        ],
    },

    # ---------- sites ----------
    "twitch": {
        "type": "url",
        "display_name": "Twitch",
        "url": "https://www.twitch.tv",
        "aliases": [
            "twitch",
            "твіч",
            "твич",
            "стріми",
            "стрими",
            "зайди на твіч",
            "відкрий твіч",
        ],
    },

    "youtube": {
        "type": "url",
        "display_name": "YouTube",
        "url": "https://www.youtube.com",
        "aliases": [
            "youtube",
            "ютуб",
            "ютюб",
            "you tube",
            "зайди на ютуб",
            "відкрий ютуб",
        ],
    },

    "google": {
        "type": "url",
        "display_name": "Google",
        "url": "https://www.google.com",
        "aliases": [
            "google",
            "гугл",
        ],
    },

    "github": {
        "type": "url",
        "display_name": "GitHub",
        "url": "https://github.com",
        "aliases": [
            "github",
            "гітхаб",
            "гитхаб",
        ],
    },

    "chatgpt": {
        "type": "url",
        "display_name": "ChatGPT",
        "url": "https://chatgpt.com",
        "aliases": [
            "chatgpt",
            "чатгпт",
            "чат gpt",
            "чгпт",
        ],
    },

    # ---------- folders ----------
    "downloads": {
        "type": "folder",
        "display_name": "Downloads",
        "path_func": _downloads,
        "aliases": [
            "downloads",
            "download",
            "завантаження",
            "загрузки",
            "папку завантажень",
            "папку загрузок",
            "відкрий завантаження",
            "відкрий загрузки",
        ],
    },

    "desktop": {
        "type": "folder",
        "display_name": "Desktop",
        "path_func": _desktop,
        "aliases": [
            "desktop",
            "робочий стіл",
            "рабочий стол",
            "десктоп",
            "відкрий робочий стіл",
        ],
    },

    "documents": {
        "type": "folder",
        "display_name": "Documents",
        "path_func": _documents,
        "aliases": [
            "documents",
            "документи",
            "доки",
            "папку документів",
            "відкрий документи",
        ],
    },

    "music": {
        "type": "folder",
        "display_name": "Music",
        "path_func": _music,
        "aliases": [
            "music",
            "музика",
            "папку музики",
        ],
    },

    "pictures": {
        "type": "folder",
        "display_name": "Pictures",
        "path_func": _pictures,
        "aliases": [
            "pictures",
            "images",
            "фото",
            "картинки",
            "зображення",
        ],
    },

    "videos": {
        "type": "folder",
        "display_name": "Videos",
        "path_func": _videos,
        "aliases": [
            "videos",
            "відео",
            "видео",
        ],
    },

    "sndi_project": {
        "type": "folder",
        "display_name": "SNDI project",
        "path_func": _sndi_project,
        "aliases": [
            "sndi",
            "сенді",
            "sandy",
            "sndi project",
            "проект sndi",
            "проєкт sndi",
            "папку sndi",
            "папку сенді",
            "папку проекту",
            "папку проєкту",
            "свій проект",
            "свій проєкт",
            "директорію проекту",
            "директорію sndi",
            "відкрий папку sndi",
            "відкрий папку сенді",
            "відкрий проект sndi",
        ],
    },

    "sndi_appdata": {
        "type": "folder",
        "display_name": "SNDI AppData",
        "path_func": _appdata_sndi,
        "aliases": [
            "appdata sndi",
            "аппдата sndi",
            "память sndi",
            "пам'ять sndi",
            "памʼять sndi",
            "живу пам'ять",
            "живу памʼять",
            "живу память",
            "user data sndi",
        ],
    },
}


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("’", "'").replace("ʼ", "'").replace("`", "'")
    text = text.replace("проєкт", "проект")
    text = text.replace("памʼять", "память")
    text = text.replace("пам'ять", "память")
    text = text.replace("інтернет", "интернет")
    text = re.sub(r"\s+", " ", text)
    return text


def _score_alias(text: str, alias: str) -> int:
    alias_norm = normalize_text(alias)

    if not alias_norm:
        return 0

    if alias_norm == text:
        return 1000

    if alias_norm in text:
        return 500 + len(alias_norm)

    # word-level soft match
    alias_words = set(alias_norm.split())
    text_words = set(text.split())

    if alias_words and alias_words.issubset(text_words):
        return 300 + len(alias_words) * 20

    return 0


def find_registry_match(user_text: str) -> dict | None:
    """
    Soft match user text to known app/site/folder aliases.
    """
    text = normalize_text(user_text)

    best_match: dict | None = None
    best_score = 0

    for key, item in APP_ALIASES.items():
        aliases = item.get("aliases", [])

        for alias in aliases:
            score = _score_alias(text, alias)

            if score > best_score:
                best_score = score
                best_match = {
                    "key": key,
                    **item,
                }

    return best_match