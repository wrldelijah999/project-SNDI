from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re
import uuid

from sndi.core.app_paths import ensure_runtime_dirs, get_runtime_memory_dir


ACTION_LOG_FILENAME = "action_log.jsonl"


SECRET_PATTERNS = (
    # OpenAI / common API keys
    re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"\bsk-proj-[A-Za-z0-9_\-]{10,}\b"),

    # Generic tokens / secrets in key=value style
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*[^\s,;]+"
    ),

    # Long bearer-like strings
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
)


def get_action_log_path() -> Path:
    ensure_runtime_dirs()
    return get_runtime_memory_dir() / ACTION_LOG_FILENAME


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_text(value: str, max_chars: int = 1200) -> str:
    text = value or ""

    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…[truncated]"

    return text


def _sanitize_for_log(value: Any, depth: int = 0) -> Any:
    """
    Make data safe/small enough for JSONL action log.

    Rules:
    - redact common secrets;
    - truncate long strings;
    - limit nesting;
    - keep JSON-serializable shapes.
    """
    if depth > 6:
        return "[max_depth]"

    if value is None:
        return None

    if isinstance(value, str):
        return _redact_text(value)

    if isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for key, item in value.items():
            safe_key = _redact_text(str(key), max_chars=120)

            if any(
                sensitive in safe_key.lower()
                for sensitive in ("api_key", "apikey", "token", "secret", "password", "passwd")
            ):
                sanitized[safe_key] = "[REDACTED]"
                continue

            sanitized[safe_key] = _sanitize_for_log(item, depth=depth + 1)

        return sanitized

    if isinstance(value, (list, tuple, set)):
        items = list(value)

        if len(items) > 50:
            items = items[:50] + ["...[truncated]"]

        return [_sanitize_for_log(item, depth=depth + 1) for item in items]

    return _redact_text(str(value))


def append_action_log(
    action: str,
    status: str,
    target: str | Path | None = None,
    user_text: str | None = None,
    preview: dict[str, Any] | None = None,
    result: Any | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append one JSONL event to action log.

    status examples:
    - requested
    - confirmed
    - cancelled
    - executed
    - failed
    """
    ensure_runtime_dirs()

    event: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "timestamp": utc_now_iso(),
        "action": _sanitize_for_log(action),
        "status": _sanitize_for_log(status),
        "target": _sanitize_for_log(str(target)) if target is not None else None,
        "user_text": _sanitize_for_log(user_text or ""),
        "preview": _sanitize_for_log(preview or {}),
        "result": _sanitize_for_log(result),
        "error": _sanitize_for_log(error),
        "metadata": _sanitize_for_log(metadata or {}),
    }

    log_path = get_action_log_path()

    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")

    return event


def _load_action_log_lines() -> list[dict[str, Any]]:
    log_path = get_action_log_path()

    if not log_path.exists():
        return []

    entries: list[dict[str, Any]] = []

    try:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)

                if isinstance(item, dict):
                    entries.append(item)

            except json.JSONDecodeError:
                entries.append(
                    {
                        "id": "broken-line",
                        "timestamp": utc_now_iso(),
                        "action": "action_log_read",
                        "status": "failed",
                        "target": str(log_path),
                        "user_text": "",
                        "preview": {},
                        "result": None,
                        "error": "broken JSONL line skipped",
                        "metadata": {},
                    }
                )

    except Exception as error:
        return [
            {
                "id": "read-error",
                "timestamp": utc_now_iso(),
                "action": "action_log_read",
                "status": "failed",
                "target": str(log_path),
                "user_text": "",
                "preview": {},
                "result": None,
                "error": str(error),
                "metadata": {},
            }
        ]

    return entries


def get_recent_actions(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 100))
    entries = _load_action_log_lines()
    return entries[-limit:]


def format_action_log_entry(entry: dict[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""

    timestamp = entry.get("timestamp", "?")
    action = entry.get("action", "?")
    status = entry.get("status", "?")
    target = entry.get("target") or "(no target)"
    error = entry.get("error")

    line = (
        f"{prefix}{timestamp}\n"
        f"   action: {action}\n"
        f"   status: {status}\n"
        f"   target: {target}"
    )

    if error:
        line += f"\n   error: {error}"

    return line


def format_recent_actions(entries: list[dict[str, Any]] | None = None, limit: int = 20) -> str:
    """
    Backward-compatible readable action log formatter.

    If entries are passed directly, format those entries.
    Otherwise use the new action log viewer.
    """
    if entries is None:
        return format_recent_actions_view(limit=limit)

    if not entries:
        return "action log порожній."

    lines = [
        f"SNDI action log — останні {len(entries)} дій:",
        "",
    ]

    for index, entry in enumerate(entries, start=1):
        lines.append(format_action_log_entry_compact(entry, index=index))
        lines.append("")

    return "\n".join(lines).rstrip()


def get_action_log_status() -> str:
    log_path = get_action_log_path()
    entries = _load_action_log_lines()

    return (
        "SNDI action log status:\n"
        f"- path: {log_path}\n"
        f"- entries: {len(entries)}\n"
        f"- exists: {log_path.exists()}"
    )

def _shorten(value: Any, max_chars: int = 160) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", " ").replace("\r", " ").strip()

    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "…"

    return text


def _status_icon(status: str) -> str:
    normalized = (status or "").lower().strip()

    if normalized == "executed":
        return "✅"

    if normalized == "confirmed":
        return "☑️"

    if normalized == "requested":
        return "🕓"

    if normalized == "cancelled":
        return "🚫"

    if normalized == "failed":
        return "⚠️"

    return "•"


def _risk_from_entry(entry: dict[str, Any]) -> str:
    metadata = entry.get("metadata") or {}
    preview = entry.get("preview") or {}

    if isinstance(metadata, dict):
        confirmed = metadata.get("confirmed_action") or {}

        if isinstance(confirmed, dict):
            risk = confirmed.get("risk_level")

            if risk:
                return str(risk)

    if isinstance(preview, dict):
        risk = preview.get("risk_level") or preview.get("risk")

        if risk:
            return str(risk)

    return ""


def format_action_log_entry_compact(entry: dict[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""

    status = str(entry.get("status", "?"))
    action = str(entry.get("action", "?"))
    target = _shorten(entry.get("target") or "(no target)", 180)
    timestamp = _shorten(entry.get("timestamp", "?"), 32)
    error = entry.get("error")
    risk = _risk_from_entry(entry)

    icon = _status_icon(status)

    lines = [
        f"{prefix}{icon} {action} — {status}",
        f"   target: {target}",
        f"   time: {timestamp}",
    ]

    if risk:
        lines.append(f"   risk: {risk}")

    if error:
        lines.append(f"   error: {_shorten(error, 220)}")

    return "\n".join(lines)


def format_recent_actions_view(
    limit: int = 20,
    status_filter: str | None = None,
    action_filter: str | None = None,
) -> str:
    entries = get_recent_actions(limit=100)

    if status_filter:
        wanted = status_filter.lower().strip()
        entries = [
            entry for entry in entries
            if str(entry.get("status", "")).lower().strip() == wanted
        ]

    if action_filter:
        wanted_action = action_filter.lower().strip()
        entries = [
            entry for entry in entries
            if wanted_action in str(entry.get("action", "")).lower()
        ]

    limit = max(1, min(int(limit or 20), 50))
    entries = entries[-limit:]

    if not entries:
        return "action log порожній або немає дій за таким фільтром."

    lines = [
        f"SNDI action log — останні {len(entries)} дій:",
        "",
    ]

    for index, entry in enumerate(entries, start=1):
        lines.append(format_action_log_entry_compact(entry, index=index))
        lines.append("")

    return "\n".join(lines).rstrip()


def get_action_log_stats() -> dict[str, Any]:
    entries = _load_action_log_lines()

    stats: dict[str, Any] = {
        "path": str(get_action_log_path()),
        "exists": get_action_log_path().exists(),
        "total": len(entries),
        "by_status": {},
        "by_action": {},
        "last_timestamp": None,
    }

    for entry in entries:
        status = str(entry.get("status", "unknown"))
        action = str(entry.get("action", "unknown"))

        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        stats["by_action"][action] = stats["by_action"].get(action, 0) + 1
        stats["last_timestamp"] = entry.get("timestamp") or stats["last_timestamp"]

    return stats


def format_action_log_stats() -> str:
    stats = get_action_log_stats()

    lines = [
        "SNDI action log status:",
        f"- path: {stats.get('path')}",
        f"- exists: {stats.get('exists')}",
        f"- total entries: {stats.get('total')}",
        f"- last timestamp: {stats.get('last_timestamp') or '(none)'}",
        "",
        "by status:",
    ]

    by_status = stats.get("by_status") or {}

    if by_status:
        for status, count in sorted(by_status.items()):
            lines.append(f"- {status}: {count}")
    else:
        lines.append("- empty")

    lines.append("")
    lines.append("top actions:")

    by_action = stats.get("by_action") or {}

    if by_action:
        top_actions = sorted(
            by_action.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:12]

        for action, count in top_actions:
            lines.append(f"- {action}: {count}")
    else:
        lines.append("- empty")

    return "\n".join(lines)