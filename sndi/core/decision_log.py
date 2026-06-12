from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json


MEMORY_DIR = Path("memory")
DECISION_LOG_PATH = MEMORY_DIR / "decision_log.json"


def _load_decisions() -> list[dict]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    if not DECISION_LOG_PATH.exists():
        return []

    try:
        raw = DECISION_LOG_PATH.read_text(encoding="utf-8").strip()

        if not raw:
            return []

        data = json.loads(raw)

        if isinstance(data, list):
            return data

    except Exception as error:
        print("[SNDI][DECISION LOG LOAD ERROR]", error)

    return []


def _save_decisions(decisions: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    with DECISION_LOG_PATH.open("w", encoding="utf-8") as file:
        json.dump(decisions, file, ensure_ascii=False, indent=2)


def record_decision(text: str, context: str = "SNDI") -> str:
    text = (text or "").strip()

    if not text:
        return "чум, рішення порожнє. нічого фіксувати."

    decisions = _load_decisions()

    item = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "context": context,
        "decision": text,
    }

    decisions.append(item)
    _save_decisions(decisions)

    return f"зафіксувала рішення: {text}"


def recall_decisions(query: str = "", limit: int = 8) -> str:
    decisions = _load_decisions()

    if not decisions:
        return "журнал рішень поки порожній."

    recent = decisions[-limit:]

    lines = ["останні рішення:"]

    for item in recent:
        timestamp = item.get("timestamp", "no-time")
        decision = item.get("decision", "")
        lines.append(f"- {timestamp}: {decision}")

    return "\n".join(lines)