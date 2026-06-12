from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import os


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".json",
    ".jsonl",
    ".csv",
    ".log",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".toml",
    ".bat",
    ".cmd",
    ".ps1",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".xml",
}

EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".msi",
    ".bat",
    ".cmd",
    ".ps1",
    ".vbs",
    ".js",
    ".jar",
    ".scr",
    ".com",
}

SYSTEM_SENSITIVE_MARKERS = (
    "\\windows",
    "\\program files",
    "\\program files (x86)",
    "\\programdata",
    "\\system32",
    "\\syswow64",
    "\\appdata\\local\\microsoft",
    "\\appdata\\roaming\\microsoft\\windows",
)


@dataclass
class FileOpResult:
    ok: bool
    action: str
    message: str
    target: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class FileOpPreview:
    action: str
    target: str
    risk_level: str = "low"
    preview: dict[str, Any] = field(default_factory=dict)
    message: str = ""


def normalize_path(path: str | Path) -> Path:
    """
    Normalize user-provided path.

    This does not require the path to exist.
    It resolves relative paths from current working directory.
    """
    raw = str(path or "").strip().strip('"').strip("'")

    if not raw:
        raise ValueError("path is empty")

    expanded = os.path.expandvars(os.path.expanduser(raw))
    return Path(expanded).resolve()


def human_size(size_bytes: int | float | None) -> str:
    if size_bytes is None:
        return "unknown"

    size = float(size_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]

    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"

            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size_bytes} B"


def is_system_sensitive_path(path: str | Path) -> bool:
    try:
        normalized = str(normalize_path(path)).lower()
    except Exception:
        normalized = str(path).lower()

    normalized = normalized.replace("/", "\\")

    return any(marker in normalized for marker in SYSTEM_SENSITIVE_MARKERS)


def is_probably_binary(path: str | Path, sample_size: int = 2048) -> bool:
    path_obj = normalize_path(path)

    if path_obj.suffix.lower() in TEXT_EXTENSIONS:
        return False

    try:
        with path_obj.open("rb") as file:
            sample = file.read(sample_size)

        if b"\x00" in sample:
            return True

        if not sample:
            return False

        # Heuristic: many non-text bytes means probably binary.
        non_text = sum(
            1
            for byte in sample
            if byte < 9 or (13 < byte < 32)
        )

        return non_text / max(len(sample), 1) > 0.30

    except Exception:
        return True


def get_path_info(path: str | Path) -> FileOpResult:
    action = "get_path_info"

    try:
        path_obj = normalize_path(path)

        if not path_obj.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"шлях не існує: {path_obj}",
                error="path_not_found",
            )

        stat = path_obj.stat()
        is_file = path_obj.is_file()
        is_dir = path_obj.is_dir()

        data = {
            "path": str(path_obj),
            "name": path_obj.name,
            "exists": True,
            "type": "folder" if is_dir else "file" if is_file else "other",
            "suffix": path_obj.suffix,
            "size": stat.st_size if is_file else None,
            "size_human": human_size(stat.st_size) if is_file else "(folder)",
            "parent": str(path_obj.parent),
            "is_file": is_file,
            "is_dir": is_dir,
            "is_sensitive": is_system_sensitive_path(path_obj),
        }

        return FileOpResult(
            ok=True,
            action=action,
            target=str(path_obj),
            message=format_path_info(data),
            data=data,
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла прочитати info: {error}",
            error=str(error),
        )


def format_path_info(data: dict[str, Any]) -> str:
    warning = "\n- warning: system-sensitive path" if data.get("is_sensitive") else ""

    return (
        "path info:\n"
        f"- path: {data.get('path')}\n"
        f"- type: {data.get('type')}\n"
        f"- size: {data.get('size_human')}\n"
        f"- parent: {data.get('parent')}"
        f"{warning}"
    )


def list_directory(path: str | Path, limit: int = 80) -> FileOpResult:
    action = "file_list"

    try:
        path_obj = normalize_path(path)

        if not path_obj.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"папка не існує: {path_obj}",
                error="path_not_found",
            )

        if not path_obj.is_dir():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"це не папка: {path_obj}",
                error="not_a_directory",
            )

        entries = []

        for item in sorted(path_obj.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = item.stat()
                item_type = "folder" if item.is_dir() else "file" if item.is_file() else "other"

                entries.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "type": item_type,
                        "size": stat.st_size if item.is_file() else None,
                        "size_human": human_size(stat.st_size) if item.is_file() else "(folder)",
                    }
                )

            except Exception as item_error:
                entries.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "type": "unknown",
                        "size": None,
                        "size_human": "unknown",
                        "error": str(item_error),
                    }
                )

        total = len(entries)
        limited_entries = entries[: max(1, min(limit, 300))]

        lines = [
            f"вміст папки: {path_obj}",
            f"знайдено: {total}",
        ]

        for entry in limited_entries:
            lines.append(
                f"- [{entry['type']}] {entry['name']} — {entry['size_human']}"
            )

        if total > len(limited_entries):
            lines.append(f"...і ще {total - len(limited_entries)} елементів.")

        return FileOpResult(
            ok=True,
            action=action,
            target=str(path_obj),
            message="\n".join(lines),
            data={
                "path": str(path_obj),
                "entries": limited_entries,
                "total": total,
                "limit": len(limited_entries),
                "is_sensitive": is_system_sensitive_path(path_obj),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла прочитати папку: {error}",
            error=str(error),
        )


def find_paths(
    root: str | Path,
    query: str,
    limit: int = 50,
    max_depth: int = 5,
) -> FileOpResult:
    action = "file_find"

    try:
        root_path = normalize_path(root)
        query_normalized = (query or "").strip().lower()

        if not root_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(root_path),
                message=f"папка для пошуку не існує: {root_path}",
                error="path_not_found",
            )

        if not root_path.is_dir():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(root_path),
                message=f"це не папка для пошуку: {root_path}",
                error="not_a_directory",
            )

        if not query_normalized:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(root_path),
                message="порожній запит для пошуку.",
                error="empty_query",
            )

        matches: list[dict[str, Any]] = []
        base_depth = len(root_path.parts)

        for current_root, dir_names, file_names in os.walk(root_path):
            current_path = Path(current_root)
            current_depth = len(current_path.parts) - base_depth

            if current_depth >= max_depth:
                dir_names[:] = []

            names = list(dir_names) + list(file_names)

            for name in names:
                if query_normalized not in name.lower():
                    continue

                item = current_path / name

                try:
                    stat = item.stat()
                    item_type = "folder" if item.is_dir() else "file" if item.is_file() else "other"

                    matches.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "type": item_type,
                            "size": stat.st_size if item.is_file() else None,
                            "size_human": human_size(stat.st_size) if item.is_file() else "(folder)",
                        }
                    )

                except Exception:
                    matches.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "type": "unknown",
                            "size": None,
                            "size_human": "unknown",
                        }
                    )

                if len(matches) >= limit:
                    break

            if len(matches) >= limit:
                break

        lines = [
            f"пошук у: {root_path}",
            f"запит: {query}",
            f"знайдено: {len(matches)}",
        ]

        for match in matches:
            lines.append(
                f"- [{match['type']}] {match['name']} — {match['path']}"
            )

        if not matches:
            lines.append("нічого не знайшла.")

        return FileOpResult(
            ok=True,
            action=action,
            target=str(root_path),
            message="\n".join(lines),
            data={
                "root": str(root_path),
                "query": query,
                "matches": matches,
                "limit": limit,
                "max_depth": max_depth,
                "is_sensitive": is_system_sensitive_path(root_path),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(root),
            message=f"пошук впав: {error}",
            error=str(error),
        )


def read_text_preview(
    path: str | Path,
    max_chars: int = 5000,
    encoding: str = "utf-8",
) -> FileOpResult:
    action = "file_read_preview"

    try:
        path_obj = normalize_path(path)

        if not path_obj.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"файл не існує: {path_obj}",
                error="path_not_found",
            )

        if not path_obj.is_file():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"це не файл: {path_obj}",
                error="not_a_file",
            )

        if is_probably_binary(path_obj):
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"схоже, це binary-файл. не читаю як текст: {path_obj}",
                error="binary_file",
            )

        raw = path_obj.read_text(encoding=encoding, errors="replace")
        truncated = len(raw) > max_chars
        preview = raw[:max_chars]

        message = (
            f"preview файлу: {path_obj}\n"
            f"розмір: {human_size(path_obj.stat().st_size)}\n"
            f"обрізано: {'так' if truncated else 'ні'}\n\n"
            f"{preview}"
        )

        if truncated:
            message += "\n\n...[preview truncated]"

        return FileOpResult(
            ok=True,
            action=action,
            target=str(path_obj),
            message=message,
            data={
                "path": str(path_obj),
                "size": path_obj.stat().st_size,
                "size_human": human_size(path_obj.stat().st_size),
                "preview": preview,
                "truncated": truncated,
                "max_chars": max_chars,
                "encoding": encoding,
                "is_sensitive": is_system_sensitive_path(path_obj),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла прочитати preview: {error}",
            error=str(error),
        )


def open_path(path: str | Path) -> FileOpResult:
    """
    Open file/folder via Windows shell.

    Safety:
    - folders are ok;
    - common documents are ok;
    - executable/script files are blocked in v1.11 read-only core
      because opening them may execute code.
    """
    action = "file_open"

    try:
        path_obj = normalize_path(path)

        if not path_obj.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=f"шлях не існує: {path_obj}",
                error="path_not_found",
            )

        if path_obj.is_file() and path_obj.suffix.lower() in EXECUTABLE_EXTENSIONS:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(path_obj),
                message=(
                    "не відкриваю executable/script файл без окремого підтвердження: "
                    f"{path_obj}"
                ),
                error="executable_open_blocked",
            )

        os.startfile(str(path_obj))

        return FileOpResult(
            ok=True,
            action=action,
            target=str(path_obj),
            message=f"відкрила: {path_obj}",
            data={
                "path": str(path_obj),
                "type": "folder" if path_obj.is_dir() else "file",
                "is_sensitive": is_system_sensitive_path(path_obj),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла відкрити: {error}",
            error=str(error),
        )


def build_readonly_preview(action: str, target: str | Path, data: dict[str, Any] | None = None) -> FileOpPreview:
    path_obj = normalize_path(target)

    preview = {
        "type": "folder" if path_obj.is_dir() else "file" if path_obj.is_file() else "unknown",
        "mode": "read-only",
        "path": str(path_obj),
        "is_sensitive": is_system_sensitive_path(path_obj),
    }

    if path_obj.exists() and path_obj.is_file():
        try:
            preview["size"] = path_obj.stat().st_size
            preview["size_human"] = human_size(path_obj.stat().st_size)
        except Exception:
            preview["size_human"] = "unknown"

    if data:
        preview.update(data)

    return FileOpPreview(
        action=action,
        target=str(path_obj),
        risk_level="low",
        preview=preview,
        message="read-only file operation preview",
    )