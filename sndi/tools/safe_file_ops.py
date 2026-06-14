from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import difflib
import os
import shutil
import uuid

from sndi.core.app_paths import (
    get_runtime_safe_trash_dir,
    get_runtime_file_backups_dir,
)

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


def _path_type(path: Path) -> str:
    if path.is_dir():
        return "folder"

    if path.is_file():
        return "file"

    return "unknown"


def _safe_stat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "type": "missing",
            "size": None,
            "size_human": "missing",
        }

    try:
        stat = path.stat()
        is_file = path.is_file()

        return {
            "exists": True,
            "type": _path_type(path),
            "size": stat.st_size if is_file else None,
            "size_human": human_size(stat.st_size) if is_file else "(folder)",
        }

    except Exception as error:
        return {
            "exists": True,
            "type": "unknown",
            "size": None,
            "size_human": "unknown",
            "stat_error": str(error),
        }


def _preview_warning_for_path(path: Path) -> str | None:
    if is_system_sensitive_path(path):
        return "шлях схожий на системний або чутливий. дія потребує особливо уважного підтвердження."

    return None


def _build_preview_message(preview: FileOpPreview) -> str:
    data = preview.preview or {}

    lines = [
        "preview файлової дії:",
        f"- action: {preview.action}",
        f"- target: {preview.target}",
        f"- risk: {preview.risk_level}",
    ]

    source = data.get("source")
    destination = data.get("destination")
    new_name = data.get("new_name")

    if source:
        lines.append(f"- source: {source}")

    if destination:
        lines.append(f"- destination: {destination}")

    if new_name:
        lines.append(f"- new name: {new_name}")

    lines.extend(
        [
            f"- type: {data.get('type', 'unknown')}",
            f"- exists: {data.get('exists', 'unknown')}",
            f"- size: {data.get('size_human', 'unknown')}",
            f"- mode: {data.get('mode', 'mutation preview')}",
        ]
    )

    if data.get("parent"):
        lines.append(f"- parent: {data.get('parent')}")

    if data.get("will_overwrite"):
        lines.append("- warning: destination already exists / conflict")

    if data.get("warning"):
        lines.append(f"- warning: {data.get('warning')}")

    if data.get("diff"):
        lines.append("")
        lines.append("diff preview:")
        lines.append(data.get("diff"))

    lines.append("")
    lines.append("ця дія ще НЕ виконана. вона має пройти confirmation layer.")

    return "\n".join(lines)


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


def build_create_folder_preview(path: str | Path) -> FileOpPreview:
    target = normalize_path(path)
    parent = target.parent

    preview = {
        "type": "folder",
        "exists": target.exists(),
        "size": None,
        "size_human": "(folder)",
        "parent": str(parent),
        "parent_exists": parent.exists(),
        "mode": "create folder",
        "will_overwrite": target.exists(),
        "is_sensitive": is_system_sensitive_path(target),
        "warning": _preview_warning_for_path(target),
    }

    risk = "medium"

    if preview["is_sensitive"]:
        risk = "high"

    if target.exists():
        risk = "high"
        preview["warning"] = "ціль уже існує. створення папки може бути зайвим або конфліктним."

    if not parent.exists():
        risk = "medium"
        preview["warning"] = "батьківська папка не існує. виконання має або створити її, або впасти залежно від executor logic."

    result = FileOpPreview(
        action="file_create_folder",
        target=str(target),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_create_text_file_preview(
    path: str | Path,
    content: str = "",
    overwrite: bool = False,
) -> FileOpPreview:
    target = normalize_path(path)
    parent = target.parent
    exists = target.exists()

    content_preview = content[:500]

    if len(content) > 500:
        content_preview += "…[truncated]"

    preview = {
        "type": "file",
        "exists": exists,
        "size": len(content.encode("utf-8")),
        "size_human": human_size(len(content.encode("utf-8"))),
        "parent": str(parent),
        "parent_exists": parent.exists(),
        "mode": "create text file",
        "overwrite": overwrite,
        "will_overwrite": exists and overwrite,
        "content_preview": content_preview,
        "is_sensitive": is_system_sensitive_path(target),
        "warning": _preview_warning_for_path(target),
    }

    risk = "medium"

    if preview["is_sensitive"]:
        risk = "high"

    if exists and not overwrite:
        risk = "high"
        preview["warning"] = "файл уже існує. без overwrite виконання має бути заблоковане."

    if exists and overwrite:
        risk = "high"
        preview["warning"] = "файл уже існує і буде перезаписаний після підтвердження."

    result = FileOpPreview(
        action="file_create_file",
        target=str(target),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_copy_path_preview(source: str | Path, destination: str | Path) -> FileOpPreview:
    source_path = normalize_path(source)
    destination_path = normalize_path(destination)

    source_stat = _safe_stat(source_path)
    destination_stat = _safe_stat(destination_path)

    preview = {
        "type": source_stat.get("type", "unknown"),
        "exists": source_path.exists(),
        "source": str(source_path),
        "destination": str(destination_path),
        "destination_exists": destination_path.exists(),
        "will_overwrite": destination_path.exists(),
        "size": source_stat.get("size"),
        "size_human": source_stat.get("size_human"),
        "mode": "copy",
        "is_sensitive": (
            is_system_sensitive_path(source_path)
            or is_system_sensitive_path(destination_path)
        ),
        "source_info": source_stat,
        "destination_info": destination_stat,
        "warning": None,
    }

    risk = "medium"

    if not source_path.exists():
        risk = "high"
        preview["warning"] = "source не існує. виконання буде неможливим."

    elif destination_path.exists():
        risk = "high"
        preview["warning"] = "destination уже існує. можливий conflict/overwrite."

    elif preview["is_sensitive"]:
        risk = "high"
        preview["warning"] = _preview_warning_for_path(source_path) or _preview_warning_for_path(destination_path)

    result = FileOpPreview(
        action="file_copy",
        target=str(destination_path),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_move_path_preview(source: str | Path, destination: str | Path) -> FileOpPreview:
    source_path = normalize_path(source)
    destination_path = normalize_path(destination)

    source_stat = _safe_stat(source_path)
    destination_stat = _safe_stat(destination_path)

    preview = {
        "type": source_stat.get("type", "unknown"),
        "exists": source_path.exists(),
        "source": str(source_path),
        "destination": str(destination_path),
        "destination_exists": destination_path.exists(),
        "will_overwrite": destination_path.exists(),
        "size": source_stat.get("size"),
        "size_human": source_stat.get("size_human"),
        "mode": "move",
        "is_sensitive": (
            is_system_sensitive_path(source_path)
            or is_system_sensitive_path(destination_path)
        ),
        "source_info": source_stat,
        "destination_info": destination_stat,
        "warning": None,
    }

    risk = "medium"

    if not source_path.exists():
        risk = "high"
        preview["warning"] = "source не існує. виконання буде неможливим."

    elif destination_path.exists():
        risk = "high"
        preview["warning"] = "destination уже існує. move може перезаписати або впасти."

    elif preview["is_sensitive"]:
        risk = "high"
        preview["warning"] = _preview_warning_for_path(source_path) or _preview_warning_for_path(destination_path)

    result = FileOpPreview(
        action="file_move",
        target=str(destination_path),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_rename_path_preview(source: str | Path, new_name: str) -> FileOpPreview:
    source_path = normalize_path(source)
    clean_new_name = (new_name or "").strip().strip('"').strip("'")

    if not clean_new_name:
        destination_path = source_path
    else:
        destination_path = source_path.with_name(clean_new_name)

    source_stat = _safe_stat(source_path)
    destination_stat = _safe_stat(destination_path)

    preview = {
        "type": source_stat.get("type", "unknown"),
        "exists": source_path.exists(),
        "source": str(source_path),
        "destination": str(destination_path),
        "new_name": clean_new_name,
        "destination_exists": destination_path.exists(),
        "will_overwrite": destination_path.exists(),
        "size": source_stat.get("size"),
        "size_human": source_stat.get("size_human"),
        "mode": "rename",
        "is_sensitive": (
            is_system_sensitive_path(source_path)
            or is_system_sensitive_path(destination_path)
        ),
        "source_info": source_stat,
        "destination_info": destination_stat,
        "warning": None,
    }

    risk = "medium"

    if not source_path.exists():
        risk = "high"
        preview["warning"] = "source не існує. rename неможливий."

    elif not clean_new_name:
        risk = "high"
        preview["warning"] = "нова назва порожня."

    elif destination_path.exists():
        risk = "high"
        preview["warning"] = "файл або папка з новою назвою вже існує."

    elif preview["is_sensitive"]:
        risk = "high"
        preview["warning"] = _preview_warning_for_path(source_path) or _preview_warning_for_path(destination_path)

    result = FileOpPreview(
        action="file_rename",
        target=str(source_path),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_delete_path_preview(path: str | Path) -> FileOpPreview:
    target = normalize_path(path)
    target_stat = _safe_stat(target)

    preview = {
        "type": target_stat.get("type", "unknown"),
        "exists": target.exists(),
        "size": target_stat.get("size"),
        "size_human": target_stat.get("size_human"),
        "mode": "safe delete only",
        "delete_policy": "send2trash if available, otherwise AppData safe_trash fallback",
        "is_sensitive": is_system_sensitive_path(target),
        "warning": None,
    }

    risk = "destructive"

    if not target.exists():
        preview["warning"] = "шлях не існує. delete буде неможливий."

    elif preview["is_sensitive"]:
        preview["warning"] = _preview_warning_for_path(target)

    result = FileOpPreview(
        action="file_delete_safe",
        target=str(target),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result


def build_text_replace_preview(
    path: str | Path,
    old_text: str,
    new_text: str,
    max_diff_lines: int = 120,
) -> FileOpPreview:
    target = normalize_path(path)
    target_stat = _safe_stat(target)

    preview: dict[str, Any] = {
        "type": target_stat.get("type", "unknown"),
        "exists": target.exists(),
        "size": target_stat.get("size"),
        "size_human": target_stat.get("size_human"),
        "mode": "text replace preview",
        "old_text_preview": (old_text or "")[:300],
        "new_text_preview": (new_text or "")[:300],
        "is_sensitive": is_system_sensitive_path(target),
        "warning": None,
    }

    risk = "medium"

    if not target.exists():
        risk = "high"
        preview["warning"] = "файл не існує. edit неможливий."

    elif not target.is_file():
        risk = "high"
        preview["warning"] = "це не файл. edit неможливий."

    elif is_probably_binary(target):
        risk = "high"
        preview["warning"] = "схоже, це binary-файл. text edit заблокований."

    elif not old_text:
        risk = "high"
        preview["warning"] = "old_text порожній. replace заблокований."

    else:
        try:
            original = target.read_text(encoding="utf-8", errors="replace")

            if old_text not in original:
                risk = "high"
                preview["warning"] = "old_text не знайдено у файлі. replace нічого не змінить."

            modified = original.replace(old_text, new_text, 1)

            diff_lines = list(
                difflib.unified_diff(
                    original.splitlines(),
                    modified.splitlines(),
                    fromfile=str(target),
                    tofile=f"{target} (after)",
                    lineterm="",
                )
            )

            truncated = len(diff_lines) > max_diff_lines
            limited_diff = diff_lines[:max_diff_lines]

            if truncated:
                limited_diff.append("...[diff truncated]")

            preview["diff"] = "\n".join(limited_diff) if limited_diff else "(no diff)"
            preview["diff_truncated"] = truncated
            preview["replace_count_preview"] = 1

        except Exception as error:
            risk = "high"
            preview["warning"] = f"не змогла побудувати diff: {error}"

    if preview["is_sensitive"] and risk != "high":
        risk = "high"
        preview["warning"] = _preview_warning_for_path(target)

    result = FileOpPreview(
        action="file_edit_preview",
        target=str(target),
        risk_level=risk,
        preview=preview,
    )
    result.message = _build_preview_message(result)
    return result

def _mutation_blocked_for_sensitive_paths(*paths: str | Path) -> str | None:
    """
    v1.11 safety guard.

    We do not mutate Windows/system-sensitive locations.
    This avoids accidental destructive operations in system folders.
    """
    for path in paths:
        if path and is_system_sensitive_path(path):
            return f"mutation blocked for system-sensitive path: {path}"

    return None


def _ensure_parent_exists(path: Path) -> FileOpResult | None:
    parent = path.parent

    if not parent.exists():
        return FileOpResult(
            ok=False,
            action="parent_check",
            target=str(path),
            message=f"батьківська папка не існує: {parent}",
            error="parent_not_found",
        )

    if not parent.is_dir():
        return FileOpResult(
            ok=False,
            action="parent_check",
            target=str(path),
            message=f"parent існує, але це не папка: {parent}",
            error="parent_not_directory",
        )

    return None


def execute_create_folder(path: str | Path) -> FileOpResult:
    action = "file_create_folder"

    try:
        target = normalize_path(path)

        blocked = _mutation_blocked_for_sensitive_paths(target)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if target.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"папка/файл уже існує: {target}",
                error="target_exists",
            )

        target.mkdir(parents=True, exist_ok=False)

        return FileOpResult(
            ok=True,
            action=action,
            target=str(target),
            message=f"папку створено: {target}",
            data={
                "path": str(target),
                "type": "folder",
                "created": True,
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла створити папку: {error}",
            error=str(error),
        )


def execute_create_text_file(
    path: str | Path,
    content: str = "",
    overwrite: bool = False,
) -> FileOpResult:
    action = "file_create_file"

    try:
        target = normalize_path(path)

        blocked = _mutation_blocked_for_sensitive_paths(target)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        parent_error = _ensure_parent_exists(target)
        if parent_error is not None:
            parent_error.action = action
            return parent_error

        if target.exists() and not overwrite:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"файл уже існує, overwrite=False: {target}",
                error="target_exists",
            )

        if target.exists() and target.is_dir():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"target існує і це папка, не файл: {target}",
                error="target_is_directory",
            )

        target.write_text(content or "", encoding="utf-8")

        return FileOpResult(
            ok=True,
            action=action,
            target=str(target),
            message=f"текстовий файл створено: {target}",
            data={
                "path": str(target),
                "type": "file",
                "size": target.stat().st_size,
                "size_human": human_size(target.stat().st_size),
                "overwrite": overwrite,
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла створити файл: {error}",
            error=str(error),
        )


def execute_copy_path(source: str | Path, destination: str | Path) -> FileOpResult:
    action = "file_copy"

    try:
        source_path = normalize_path(source)
        destination_path = normalize_path(destination)

        blocked = _mutation_blocked_for_sensitive_paths(source_path, destination_path)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not source_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"source не існує: {source_path}",
                error="source_not_found",
            )

        parent_error = _ensure_parent_exists(destination_path)
        if parent_error is not None:
            parent_error.action = action
            return parent_error

        if destination_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"destination уже існує, copy заблоковано: {destination_path}",
                error="destination_exists",
            )

        if source_path.is_dir():
            shutil.copytree(source_path, destination_path)
            copied_type = "folder"
            size = None
            size_text = "(folder)"
        else:
            shutil.copy2(source_path, destination_path)
            copied_type = "file"
            size = destination_path.stat().st_size
            size_text = human_size(size)

        return FileOpResult(
            ok=True,
            action=action,
            target=str(destination_path),
            message=f"скопійовано: {source_path} → {destination_path}",
            data={
                "source": str(source_path),
                "destination": str(destination_path),
                "type": copied_type,
                "size": size,
                "size_human": size_text,
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(destination),
            message=f"не змогла скопіювати: {error}",
            error=str(error),
        )


def execute_move_path(source: str | Path, destination: str | Path) -> FileOpResult:
    action = "file_move"

    try:
        source_path = normalize_path(source)
        destination_path = normalize_path(destination)

        blocked = _mutation_blocked_for_sensitive_paths(source_path, destination_path)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not source_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"source не існує: {source_path}",
                error="source_not_found",
            )

        parent_error = _ensure_parent_exists(destination_path)
        if parent_error is not None:
            parent_error.action = action
            return parent_error

        if destination_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(destination_path),
                message=f"destination уже існує, move заблоковано: {destination_path}",
                error="destination_exists",
            )

        moved_path = shutil.move(str(source_path), str(destination_path))

        return FileOpResult(
            ok=True,
            action=action,
            target=str(destination_path),
            message=f"переміщено: {source_path} → {destination_path}",
            data={
                "source": str(source_path),
                "destination": str(destination_path),
                "result_path": str(moved_path),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(destination),
            message=f"не змогла перемістити: {error}",
            error=str(error),
        )


def execute_rename_path(path: str | Path, new_name: str) -> FileOpResult:
    action = "file_rename"

    try:
        source_path = normalize_path(path)
        clean_new_name = (new_name or "").strip().strip('"').strip("'")

        if not clean_new_name:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message="нова назва порожня.",
                error="empty_new_name",
            )

        if "\\" in clean_new_name or "/" in clean_new_name:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message="нова назва не має містити шлях або слеші. тільки імʼя файлу/папки.",
                error="new_name_contains_path_separator",
            )

        destination_path = source_path.with_name(clean_new_name)

        blocked = _mutation_blocked_for_sensitive_paths(source_path, destination_path)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not source_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"source не існує: {source_path}",
                error="source_not_found",
            )

        if destination_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"цільова назва вже існує: {destination_path}",
                error="destination_exists",
            )

        source_path.rename(destination_path)

        return FileOpResult(
            ok=True,
            action=action,
            target=str(destination_path),
            message=f"перейменовано: {source_path} → {destination_path}",
            data={
                "source": str(source_path),
                "destination": str(destination_path),
                "new_name": clean_new_name,
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла перейменувати: {error}",
            error=str(error),
        )


def _build_safe_trash_destination(source_path: Path) -> Path:
    safe_trash_dir = get_runtime_safe_trash_dir()
    safe_trash_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]
    safe_name = f"{timestamp}_{unique}_{source_path.name}"

    return safe_trash_dir / safe_name


def execute_safe_delete_path(path: str | Path) -> FileOpResult:
    """
    Safe delete only.

    Priority:
    1. send2trash if installed;
    2. fallback move to %APPDATA%\\SNDI\\safe_trash.

    Never uses permanent delete.
    """
    action = "file_delete_safe"

    try:
        target = normalize_path(path)

        blocked = _mutation_blocked_for_sensitive_paths(target)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not target.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"шлях не існує: {target}",
                error="path_not_found",
            )

        original_info = _safe_stat(target)

        try:
            from send2trash import send2trash  # type: ignore

            send2trash(str(target))

            return FileOpResult(
                ok=True,
                action=action,
                target=str(target),
                message=f"переміщено в кошик: {target}",
                data={
                    "path": str(target),
                    "method": "send2trash",
                    "original_info": original_info,
                },
            )

        except Exception as send2trash_error:
            fallback_destination = _build_safe_trash_destination(target)
            moved_path = shutil.move(str(target), str(fallback_destination))

            return FileOpResult(
                ok=True,
                action=action,
                target=str(target),
                message=(
                    "send2trash недоступний або впав, тому перемістила у safe_trash:\n"
                    f"{target} → {fallback_destination}"
                ),
                data={
                    "path": str(target),
                    "method": "safe_trash_fallback",
                    "safe_trash_path": str(fallback_destination),
                    "result_path": str(moved_path),
                    "send2trash_error": str(send2trash_error),
                    "original_info": original_info,
                },
            )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла безпечно видалити: {error}",
            error=str(error),
        )

def _sanitize_backup_filename(value: str) -> str:
    safe = value or "file"

    for char in '<>:"/\\|?*':
        safe = safe.replace(char, "_")

    safe = safe.strip().strip(".")

    if not safe:
        safe = "file"

    return safe[:180]


def _build_file_backup_destination(source_path: Path) -> Path:
    backup_dir = get_runtime_file_backups_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]

    source_marker = str(source_path).replace(":", "")
    source_marker = _sanitize_backup_filename(source_marker.replace("\\", "__").replace("/", "__"))

    backup_name = f"{timestamp}_{unique}_{source_marker}.bak"
    return backup_dir / backup_name


def create_text_file_backup(path: str | Path) -> FileOpResult:
    action = "file_backup"

    try:
        source_path = normalize_path(path)

        if not source_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"backup неможливий: файл не існує: {source_path}",
                error="path_not_found",
            )

        if not source_path.is_file():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"backup неможливий: це не файл: {source_path}",
                error="not_a_file",
            )

        backup_path = _build_file_backup_destination(source_path)
        shutil.copy2(source_path, backup_path)

        return FileOpResult(
            ok=True,
            action=action,
            target=str(source_path),
            message=f"backup створено: {backup_path}",
            data={
                "source": str(source_path),
                "backup_path": str(backup_path),
                "size": backup_path.stat().st_size,
                "size_human": human_size(backup_path.stat().st_size),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла створити backup: {error}",
            error=str(error),
        )


def execute_text_replace(
    path: str | Path,
    old_text: str,
    new_text: str,
) -> FileOpResult:
    """
    Execute safe text replace.

    Safety:
    - only confirmed action should call this;
    - blocks system-sensitive paths;
    - blocks binary files;
    - creates backup before writing;
    - replaces only first occurrence to match preview behavior.
    """
    action = "file_edit_preview"

    try:
        target = normalize_path(path)

        blocked = _mutation_blocked_for_sensitive_paths(target)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not target.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"файл не існує: {target}",
                error="path_not_found",
            )

        if not target.is_file():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"це не файл: {target}",
                error="not_a_file",
            )

        if is_probably_binary(target):
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"схоже, це binary-файл. text edit заблокований: {target}",
                error="binary_file",
            )

        if not old_text:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message="old_text порожній. replace заблокований.",
                error="empty_old_text",
            )

        original = target.read_text(encoding="utf-8", errors="replace")

        if old_text not in original:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message="old_text не знайдено у файлі. нічого не змінено.",
                error="old_text_not_found",
            )

        backup_result = create_text_file_backup(target)

        if not backup_result.ok:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"edit заблокований, бо backup не створився: {backup_result.message}",
                error="backup_failed",
                data={
                    "backup_error": backup_result.error,
                },
            )

        modified = original.replace(old_text, new_text, 1)
        target.write_text(modified, encoding="utf-8")

        return FileOpResult(
            ok=True,
            action=action,
            target=str(target),
            message=(
                "текст у файлі оновлено.\n"
                f"Файл: {target}\n"
                f"Backup: {backup_result.data.get('backup_path')}\n"
                "Заміна: 1 occurrence"
            ),
            data={
                "path": str(target),
                "backup_path": backup_result.data.get("backup_path"),
                "old_text_preview": old_text[:300],
                "new_text_preview": new_text[:300],
                "replace_count": 1,
                "size": target.stat().st_size,
                "size_human": human_size(target.stat().st_size),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла виконати text replace: {error}",
            error=str(error),
        )
    
def _sanitize_backup_filename(value: str) -> str:
    safe = value or "file"

    for char in '<>:"/\\|?*':
        safe = safe.replace(char, "_")

    safe = safe.strip().strip(".")

    if not safe:
        safe = "file"

    return safe[:180]


def _build_file_backup_destination(source_path: Path) -> Path:
    backup_dir = get_runtime_file_backups_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:8]

    source_marker = str(source_path).replace(":", "")
    source_marker = _sanitize_backup_filename(source_marker.replace("\\", "__").replace("/", "__"))

    backup_name = f"{timestamp}_{unique}_{source_marker}.bak"
    return backup_dir / backup_name


def create_text_file_backup(path: str | Path) -> FileOpResult:
    action = "file_backup"

    try:
        source_path = normalize_path(path)

        if not source_path.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"backup неможливий: файл не існує: {source_path}",
                error="path_not_found",
            )

        if not source_path.is_file():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(source_path),
                message=f"backup неможливий: це не файл: {source_path}",
                error="not_a_file",
            )

        backup_path = _build_file_backup_destination(source_path)
        shutil.copy2(source_path, backup_path)

        return FileOpResult(
            ok=True,
            action=action,
            target=str(source_path),
            message=f"backup створено: {backup_path}",
            data={
                "source": str(source_path),
                "backup_path": str(backup_path),
                "size": backup_path.stat().st_size,
                "size_human": human_size(backup_path.stat().st_size),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла створити backup: {error}",
            error=str(error),
        )


def execute_text_replace(
    path: str | Path,
    old_text: str,
    new_text: str,
) -> FileOpResult:
    """
    Execute safe text replace.

    Safety:
    - only confirmed action should call this;
    - blocks system-sensitive paths;
    - blocks binary files;
    - creates backup before writing;
    - replaces only first occurrence to match preview behavior.
    """
    action = "file_edit_preview"

    try:
        target = normalize_path(path)

        blocked = _mutation_blocked_for_sensitive_paths(target)
        if blocked:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"заблоковано: {blocked}",
                error="sensitive_path_blocked",
            )

        if not target.exists():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"файл не існує: {target}",
                error="path_not_found",
            )

        if not target.is_file():
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"це не файл: {target}",
                error="not_a_file",
            )

        if is_probably_binary(target):
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"схоже, це binary-файл. text edit заблокований: {target}",
                error="binary_file",
            )

        if not old_text:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message="old_text порожній. replace заблокований.",
                error="empty_old_text",
            )

        original = target.read_text(encoding="utf-8", errors="replace")

        if old_text not in original:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message="old_text не знайдено у файлі. нічого не змінено.",
                error="old_text_not_found",
            )

        backup_result = create_text_file_backup(target)

        if not backup_result.ok:
            return FileOpResult(
                ok=False,
                action=action,
                target=str(target),
                message=f"edit заблокований, бо backup не створився: {backup_result.message}",
                error="backup_failed",
                data={
                    "backup_error": backup_result.error,
                },
            )

        modified = original.replace(old_text, new_text, 1)
        target.write_text(modified, encoding="utf-8")

        return FileOpResult(
            ok=True,
            action=action,
            target=str(target),
            message=(
                "текст у файлі оновлено.\n"
                f"Файл: {target}\n"
                f"Backup: {backup_result.data.get('backup_path')}\n"
                "Заміна: 1 occurrence"
            ),
            data={
                "path": str(target),
                "backup_path": backup_result.data.get("backup_path"),
                "old_text_preview": old_text[:300],
                "new_text_preview": new_text[:300],
                "replace_count": 1,
                "size": target.stat().st_size,
                "size_human": human_size(target.stat().st_size),
            },
        )

    except Exception as error:
        return FileOpResult(
            ok=False,
            action=action,
            target=str(path),
            message=f"не змогла виконати text replace: {error}",
            error=str(error),
        )


def execute_file_mutation(action: str, params: dict[str, Any] | None = None) -> FileOpResult:
    """
    Execute confirmed file mutation.

    This function must be called only after confirmation layer.
    """
    params = params or {}

    if action == "file_create_folder":
        return execute_create_folder(params.get("path", ""))

    if action == "file_create_file":
        return execute_create_text_file(
            path=params.get("path", ""),
            content=params.get("content", ""),
            overwrite=bool(params.get("overwrite", False)),
        )

    if action == "file_copy":
        return execute_copy_path(
            source=params.get("source", ""),
            destination=params.get("destination", ""),
        )

    if action == "file_move":
        return execute_move_path(
            source=params.get("source", ""),
            destination=params.get("destination", ""),
        )

    if action == "file_rename":
        return execute_rename_path(
            path=params.get("path", ""),
            new_name=params.get("new_name", ""),
        )

    if action == "file_delete_safe":
        return execute_safe_delete_path(params.get("path", ""))

    if action == "file_edit_preview":
        return execute_text_replace(
            path=params.get("path", ""),
            old_text=params.get("old_text", ""),
            new_text=params.get("new_text", ""),
        )

    return FileOpResult(
        ok=False,
        action=action,
        target=str(params.get("path") or params.get("target") or ""),
        message=f"невідома mutation дія: {action}",
        error="unknown_mutation_action",
    )