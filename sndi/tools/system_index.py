# sndi/tools/system_index.py
"""
SNDI V1.7 — System Index.

Read-only scanner for local apps, shortcuts, folders and files.

Goal:
  - give SNDI a real map of this PC;
  - map casual phrases like "відкрий папку диплом" to real folders/files;
  - avoid raw os.startfile(user_text);
  - do not require manually writing every alias.

No destructive actions.
No file editing.
No shell commands.
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict

from sndi.storage import user_data_dir


INDEX_FILE_NAME = "system_index.json"
INDEX_MAX_AGE_SECONDS = 60 * 60  # 1 година

MAX_TARGETS_TOTAL = 900
MAX_SHORTCUT_TARGETS = 260
MAX_FOLDER_TARGETS = 420
MAX_FILE_TARGETS = 220

MAX_SCAN_DEPTH = 4

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".idea",
    ".vscode",
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
}

IMPORTANT_FILE_SUFFIXES = {
    ".py",
    ".txt",
    ".md",
    ".doc",
    ".docx",
    ".pdf",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".zip",
    ".rar",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".mp3",
    ".wav",
    ".mp4",
    ".mov",
}


@dataclass
class SystemTarget:
    name: str
    kind: str
    path: str
    source: str
    aliases: list[str]


def _normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def _normalize_name(name: str) -> str:
    text = name.strip()

    for suffix in [".lnk", ".url", ".exe"]:
        if text.lower().endswith(suffix):
            text = text[: -len(suffix)]

    return _normalize_spaces(text)


def _basic_aliases(name: str) -> list[str]:
    """
    Generate aliases automatically from the actual object name.

    This is NOT a manual command dictionary.
    It just creates searchable variants from real names found on disk.
    """
    clean = _normalize_name(name)
    lower = clean.lower()

    variants = {
        clean,
        lower,
        lower.replace("-", " "),
        lower.replace("_", " "),
        lower.replace(".", " "),
        lower.replace("  ", " "),
    }

    # simple latin/cyrillic comfort variants for common installed names
    # small helper layer, not the main logic
    helper_map = {
        "dayz": ["дейзі", "дейз", "day z", "дей з"],
        "counter-strike": ["кс", "контра", "контру", "cs"],
        "counter strike": ["кс", "контра", "контру", "cs"],
        "discord": ["діскорд", "дискорд"],
        "telegram": ["телега", "телеграм"],
        "spotify": ["спотіфай", "спотифай"],
        "visual studio code": ["vscode", "vs code", "код", "вс код"],
        "google chrome": ["хром", "гугл хром"],
        "chrome": ["хром", "гугл хром"],
        "steam": ["стім", "стим"],
    }

    for key, extra in helper_map.items():
        if key in lower:
            variants.update(extra)

    return sorted(v for v in variants if v)


def _start_menu_roots() -> list[Path]:
    roots: list[Path] = []

    program_data = os.getenv("PROGRAMDATA")
    appdata = os.getenv("APPDATA")

    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

    roots.append(Path.home() / "Desktop")

    return [root for root in roots if root.exists()]


def _user_scan_roots() -> list[Path]:
    """
    Places where user-created projects, folders and documents usually live.
    """
    roots = [
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "Music",
        Path.home() / "Pictures",
        Path.home() / "Videos",
        Path(r"C:\SNDI project"),
    ]

    # Add available non-system drive roots, but scan shallowly and safely.
    for letter in ["D", "E", "F"]:
        drive = Path(f"{letter}:\\")
        if drive.exists():
            roots.append(drive)

    # de-duplicate
    result: list[Path] = []
    seen: set[str] = set()

    for root in roots:
        try:
            key = str(root.resolve()).lower()
        except Exception:
            key = str(root).lower()

        if key not in seen and root.exists():
            seen.add(key)
            result.append(root)

    return result


def _common_folder_targets() -> list[SystemTarget]:
    appdata = os.getenv("APPDATA") or str(Path.home())

    folders = [
        ("Desktop", Path.home() / "Desktop", ["робочий стіл", "десктоп", "desktop"]),
        ("Downloads", Path.home() / "Downloads", ["завантаження", "загрузки", "downloads"]),
        ("Documents", Path.home() / "Documents", ["документи", "documents", "доки"]),
        ("Music", Path.home() / "Music", ["музика", "music"]),
        ("Pictures", Path.home() / "Pictures", ["фото", "картинки", "зображення", "pictures"]),
        ("Videos", Path.home() / "Videos", ["відео", "videos"]),
        ("SNDI project", Path(r"C:\SNDI project"), ["sndi", "папка sndi", "проект sndi", "проєкт sndi", "сенді"]),
        ("SNDI AppData", Path(appdata) / "SNDI", ["appdata sndi", "память sndi", "живу память", "user data"]),
    ]

    targets: list[SystemTarget] = []

    for name, path, aliases in folders:
        if path.exists():
            targets.append(
                SystemTarget(
                    name=name,
                    kind="folder",
                    path=str(path),
                    source="common_folder",
                    aliases=sorted(set([name.lower(), *aliases, *_basic_aliases(name)])),
                )
            )

    return targets


def _should_skip_dir(path: Path) -> bool:
    name = path.name.strip().lower()

    if not name:
        return True

    if name in SKIP_DIR_NAMES:
        return True

    if name.startswith(".") and name not in {".obsidian"}:
        return True

    return False


def _safe_relative_depth(path: Path, root: Path) -> int:
    try:
        rel = path.relative_to(root)
        return len(rel.parts)
    except Exception:
        return 999


def _scan_shortcuts() -> list[SystemTarget]:
    targets: list[SystemTarget] = []

    for root in _start_menu_roots():
        try:
            for path in root.rglob("*"):
                if len(targets) >= MAX_SHORTCUT_TARGETS:
                    return targets

                if not path.is_file():
                    continue

                suffix = path.suffix.lower()

                if suffix not in (".lnk", ".url", ".exe"):
                    continue

                name = _normalize_name(path.stem)

                if not name:
                    continue

                kind = "shortcut"

                if suffix == ".url":
                    kind = "url_shortcut"
                elif suffix == ".exe":
                    kind = "app"

                targets.append(
                    SystemTarget(
                        name=name,
                        kind=kind,
                        path=str(path),
                        source=str(root),
                        aliases=_basic_aliases(name),
                    )
                )

        except Exception:
            continue

    return targets


def _scan_real_folders() -> list[SystemTarget]:
    """
    Scan actual user folders, so SNDI can find:
      - ДИПЛОМ
      - Музика
      - Fiverr
      - SNDI backups
      - Дипломна робота
    without manual aliases.
    """
    targets: list[SystemTarget] = []

    for root in _user_scan_roots():
        try:
            for path in root.rglob("*"):
                if len(targets) >= MAX_FOLDER_TARGETS:
                    return targets

                if not path.is_dir():
                    continue

                if _should_skip_dir(path):
                    continue

                depth = _safe_relative_depth(path, root)
                if depth > MAX_SCAN_DEPTH:
                    continue

                name = _normalize_name(path.name)

                if not name:
                    continue

                targets.append(
                    SystemTarget(
                        name=name,
                        kind="folder",
                        path=str(path),
                        source=f"user_folder:{root}",
                        aliases=_basic_aliases(name),
                    )
                )

        except Exception:
            continue

    return targets


def _scan_important_files() -> list[SystemTarget]:
    """
    Scan visible important files by name.
    Limited so it doesn't become a huge slow filesystem crawler.
    """
    targets: list[SystemTarget] = []

    for root in _user_scan_roots():
        try:
            for path in root.rglob("*"):
                if len(targets) >= MAX_FILE_TARGETS:
                    return targets

                if not path.is_file():
                    continue

                if path.suffix.lower() not in IMPORTANT_FILE_SUFFIXES:
                    continue

                depth = _safe_relative_depth(path, root)
                if depth > MAX_SCAN_DEPTH:
                    continue

                # skip files inside skipped dirs
                parts_lower = {part.lower() for part in path.parts}
                if parts_lower.intersection(SKIP_DIR_NAMES):
                    continue

                name = _normalize_name(path.name)

                if not name:
                    continue

                targets.append(
                    SystemTarget(
                        name=name,
                        kind="file",
                        path=str(path),
                        source=f"user_file:{root}",
                        aliases=_basic_aliases(path.stem),
                    )
                )

        except Exception:
            continue

    return targets


def build_system_index() -> list[dict]:
    """
    Build fresh system target index.
    """
    started = time.time()

    targets: list[SystemTarget] = []

    targets.extend(_common_folder_targets())
    targets.extend(_scan_real_folders())
    targets.extend(_scan_important_files())
    targets.extend(_scan_shortcuts())

    seen_paths: set[str] = set()
    deduped: list[SystemTarget] = []

    for target in targets:
        key = target.path.lower()

        if key in seen_paths:
            continue

        seen_paths.add(key)
        deduped.append(target)

        if len(deduped) >= MAX_TARGETS_TOTAL:
            break

    result = [asdict(t) for t in deduped]

    # add metadata as a pseudo target? no. keep index list clean.
    elapsed = round(time.time() - started, 2)
    print(f"[SNDI][SYSTEM INDEX] built {len(result)} targets in {elapsed}s")

    return result


def save_system_index(index: list[dict]) -> str:
    """
    Save index to %APPDATA%\\SNDI\\system_index.json
    """
    path = Path(user_data_dir()) / INDEX_FILE_NAME

    with open(path, "w", encoding="utf-8") as file:
        json.dump(index, file, ensure_ascii=False, indent=2)

    return str(path)


def _is_index_stale(path: Path, max_age_seconds: int = INDEX_MAX_AGE_SECONDS) -> bool:
    if not path.exists():
        return True

    try:
        age = time.time() - path.stat().st_mtime
        return age > max_age_seconds
    except Exception:
        return True


def load_or_build_system_index(force_refresh: bool = False) -> list[dict]:
    """
    Load cached system index or rebuild it.

    Auto-refresh:
      - if force_refresh=True
      - if index file does not exist
      - if index is older than INDEX_MAX_AGE_SECONDS
    """
    path = Path(user_data_dir()) / INDEX_FILE_NAME

    should_refresh = force_refresh or _is_index_stale(path)

    if path.exists() and not should_refresh:
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if isinstance(data, list):
                return data

        except Exception:
            pass

    index = build_system_index()
    save_system_index(index)
    return index

def build_system_index_prompt(force_refresh: bool = False) -> str:
    """
    Compact text block for LLM target resolving.
    """
    index = load_or_build_system_index(force_refresh=force_refresh)

    if not index:
        return "SYSTEM INDEX: empty"

    lines = ["SYSTEM INDEX — available local targets:"]

    for item in index[:MAX_TARGETS_TOTAL]:
        name = item.get("name", "")
        kind = item.get("kind", "")
        path = item.get("path", "")
        aliases = item.get("aliases", [])

        alias_text = ", ".join(aliases[:8]) if isinstance(aliases, list) else ""

        lines.append(
            f"- name: {name}\n"
            f"  kind: {kind}\n"
            f"  path: {path}\n"
            f"  aliases: {alias_text}"
        )

    return "\n".join(lines)


def find_target_by_path_or_name(name_or_path: str) -> dict | None:
    """
    Find exact target from cached index by path, name or alias.
    """
    query = name_or_path.strip().lower()

    if not query:
        return None

    index = load_or_build_system_index(force_refresh=False)

    for item in index:
        name = str(item.get("name", "")).lower()
        path = str(item.get("path", "")).lower()
        aliases = item.get("aliases", [])

        if query == name or query == path:
            return item

        if isinstance(aliases, list):
            for alias in aliases:
                if query == str(alias).lower():
                    return item

    return None