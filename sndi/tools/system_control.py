# sndi/tools/system_control.py
"""
SNDI V1.7 — System Control tools.

Controlled local system actions.

Current actions:
  - open URL
  - open Steam game by app id
  - open known app by path
  - open known folder
  - open browser search
  - find files in safe roots
  - discover installed shortcuts in Start Menu/Desktop

No destructive actions in this version.
No file deletion.
No file overwrite.
No shell=True.
"""

from __future__ import annotations

import os
import re
from sndi.tools.process_control import close_process_by_name_or_pid
import webbrowser
from pathlib import Path
from sndi.tools.system_index import (
    find_target_by_path_or_name,
    build_system_index,
    save_system_index,
)
from sndi.tools.app_registry import find_registry_match, normalize_text



SAFE_SEARCH_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Music",
    Path.home() / "Pictures",
    Path.home() / "Videos",
    Path(r"C:\SNDI project"),
]


def _start_menu_roots() -> list[Path]:
    roots: list[Path] = []

    program_data = os.getenv("PROGRAMDATA")
    appdata = os.getenv("APPDATA")

    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    roots.append(Path.home() / "Desktop")
    roots.append(Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    return [root for root in roots if root.exists()]


def _clean_action_words(text: str) -> str:
    text = normalize_text(text)

    remove_phrases = [
        "відкрий",
        "відкривай",
        "запусти",
        "запускай",
        "включи",
        "врубай",
        "увімкни",
        "зайди на",
        "перейди на",
        "погнали в",
        "го в",
        "го",
        "давай",
        "папку",
        "програму",
        "гру",
        "сайт",
        "мені",
        "будь ласка",
    ]

    for phrase in remove_phrases:
        text = text.replace(phrase, " ")

    text = re.sub(r"\s+", " ", text).strip()
    return text


def _open_path(path: str) -> str:
    try:
        if not path:
            return "не бачу шлях для відкриття."

        if not os.path.exists(path):
            return f"шлях не знайдено: {path}"

        os.startfile(path)
        return f"відкриваю: {path}"

    except Exception as error:
        return f"⚡ не змогла відкрити шлях: {error}"


def open_url(url: str) -> str:
    try:
        if not url:
            return "не бачу URL."

        if not url.startswith(("http://", "https://", "steam://")):
            url = "https://" + url

        webbrowser.open(url)
        return f"відкриваю: {url}"

    except Exception as error:
        return f"⚡ не змогла відкрити URL: {error}"


def open_steam_game(steam_id: str, display_name: str = "Steam game") -> str:
    try:
        url = f"steam://rungameid/{steam_id}"
        os.startfile(url)
        return f"запускаю {display_name} через Steam."

    except Exception as error:
        return f"⚡ не змогла запустити Steam-гру: {error}"


def open_app_from_paths(possible_paths: list[str], display_name: str = "app") -> str:
    for path in possible_paths:
        if path and os.path.exists(path):
            try:
                os.startfile(path)
                return f"відкриваю {display_name}: {path}"
            except Exception as error:
                return f"⚡ знайшла {display_name}, але не змогла запустити: {error}"

    return f"не знайшла локальний шлях для {display_name}."


def open_folder(path: str, display_name: str = "folder") -> str:
    if not path:
        return f"не бачу шлях до {display_name}."

    return _open_path(path)


def open_web_search(query: str) -> str:
    try:
        clean = query.strip()

        if not clean:
            return "дай мені, що саме шукати."

        url = "https://www.google.com/search?q=" + clean.replace(" ", "+")
        webbrowser.open(url)
        return f"відкриваю пошук: {clean}"

    except Exception as error:
        return f"⚡ не змогла відкрити пошук: {error}"


def find_files(query: str, max_results: int = 10) -> str:
    clean = _clean_action_words(query).lower()

    if not clean:
        return "дай назву файлу або частину назви."

    results: list[str] = []

    for root in SAFE_SEARCH_ROOTS:
        if not root.exists():
            continue

        try:
            for path in root.rglob("*"):
                if len(results) >= max_results:
                    break

                try:
                    if path.is_file() and clean in path.name.lower():
                        results.append(str(path))
                except Exception:
                    continue

        except Exception:
            continue

        if len(results) >= max_results:
            break

    if not results:
        return f"не знайшла файлів за запитом: {query}"

    lines = ["знайшла файли:"]
    lines.extend(f"- {item}" for item in results)
    return "\n".join(lines)


def find_shortcut_or_app(query: str) -> str | None:
    """
    Try to find a Start Menu/Desktop shortcut by fuzzy name.
    Returns path to .lnk/.exe/.url or None.
    """
    clean = _clean_action_words(query)

    if not clean:
        return None

    clean_words = set(clean.split())

    candidates: list[tuple[int, Path]] = []

    for root in _start_menu_roots():
        try:
            for path in root.rglob("*"):
                if not path.is_file():
                    continue

                if path.suffix.lower() not in (".lnk", ".exe", ".url"):
                    continue

                name = normalize_text(path.stem)
                name_words = set(name.split())

                score = 0

                if clean == name:
                    score = 1000
                elif clean in name:
                    score = 700 + len(clean)
                elif name in clean:
                    score = 600 + len(name)
                elif clean_words and clean_words.issubset(name_words):
                    score = 400 + len(clean_words) * 20
                else:
                    overlap = clean_words.intersection(name_words)
                    if overlap:
                        score = 100 + len(overlap) * 30

                if score > 0:
                    candidates.append((score, path))

        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], str(item[1]).lower()))
    return str(candidates[0][1])


def execute_registry_target(match: dict) -> str:
    target_type = match.get("type")
    display_name = match.get("display_name", match.get("key", "target"))

    if target_type == "steam":
        steam_id = match.get("steam_id")
        if not steam_id:
            return f"для {display_name} не вказаний steam_id."
        return open_steam_game(steam_id, display_name)

    if target_type == "url":
        url = match.get("url")
        if not url:
            return f"для {display_name} не вказаний URL."
        return open_url(url)

    if target_type == "folder":
        path_func = match.get("path_func")
        path = ""

        if callable(path_func):
            path = path_func()
        else:
            path = match.get("path", "")

        return open_folder(path, display_name)

    if target_type == "app":
        possible_paths = match.get("possible_paths", [])
        return open_app_from_paths(possible_paths, display_name)

    return f"не знаю, як виконати target type: {target_type}"


def _build_search_text(original_text: str, action: dict) -> str:
    parts = [
        original_text,
        str(action.get("target", "") or ""),
        str(action.get("query", "") or ""),
        str(action.get("url", "") or ""),
    ]

    return " ".join(part for part in parts if part.strip())


def execute_simple_system_action(action: dict, original_text: str) -> str:
    """
    Execute structured action.

    Expected action:
    {
      "intent": "open_known_target | open_app | open_site | open_url | open_folder | close_target | web_search_browser | find_file | refresh_system_index",
      "target": "...",
      "url": "...",
      "query": "..."
    }
    """
    intent = action.get("intent", "unknown")
    target = str(action.get("target", "") or "").strip()
    url = str(action.get("url", "") or "").strip()
    query = str(action.get("query", "") or "").strip()

    if intent == "refresh_system_index":
        return refresh_system_index()

    if intent == "close_target":
        return close_process_by_name_or_pid(target or query or original_text)

    search_text = _build_search_text(original_text, action)

    # 0. Exact target selected from system index by model.
    selected_target = target or query
    indexed_target = find_target_by_path_or_name(selected_target)

    if indexed_target:
        kind = indexed_target.get("kind", "")
        path = indexed_target.get("path", "")
        name = indexed_target.get("name", "target")

        if kind in ("folder", "shortcut", "url_shortcut", "app", "file") and path:
            return _open_path(path)

    # 1. Registry aliases.
    match = find_registry_match(search_text)
    if match:
        return execute_registry_target(match)

    # 2. Direct URL.
    if intent in ("open_url", "open_site") and url:
        return open_url(url)

    # 3. Browser search.
    if intent == "web_search_browser":
        return open_web_search(query or target or original_text)

    # 4. Find files.
    if intent == "find_file":
        return find_files(query or target or original_text)

    # 5. Try Start Menu/Desktop shortcut discovery for apps.
    if intent in ("open_known_target", "open_app", "open_site", "open_folder", "unknown"):
        shortcut = find_shortcut_or_app(target or query or original_text)

        if shortcut:
            return _open_path(shortcut)

    # 6. If user typed an existing path, open it.
    maybe_path = target or query
    if maybe_path and os.path.exists(maybe_path):
        return _open_path(maybe_path)

    # 7. Do NOT os.startfile raw text.
    return (
        "я зрозуміла, що це системна дія, але не знайшла точний target у карті ПК. "
        "не запускаю сирий текст як команду."
    )

def run_system_control_from_text(user_text: str, action: dict | None = None) -> str:
    """
    Main entrypoint for GUI thread.
    """
    if action is None:
        action = {"intent": "unknown"}

    return execute_simple_system_action(action, user_text)


def refresh_system_index() -> str:
    try:
        index = build_system_index()
        path = save_system_index(index)
        return f"оновила карту ПК: {len(index)} targets.\n{path}"
    except Exception as error:
        return f"⚡ не змогла оновити карту ПК: {error}"