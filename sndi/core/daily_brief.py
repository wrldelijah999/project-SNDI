from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

from sndi.core.decision_log import recall_decisions
from sndi.tools.git_tools import get_git_summary


MEMORY_DIR = Path("memory")
DAILY_LOG_PATH = MEMORY_DIR / "daily_log.json"


def _load_daily_log() -> list[dict]:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    if not DAILY_LOG_PATH.exists():
        return []

    try:
        raw = DAILY_LOG_PATH.read_text(encoding="utf-8").strip()

        if not raw:
            return []

        data = json.loads(raw)

        if isinstance(data, list):
            return data

    except Exception as error:
        print("[SNDI][DAILY LOG LOAD ERROR]", error)

    return []


def _save_daily_log(items: list[dict]) -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    DAILY_LOG_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_morning_brief() -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    git_summary = get_git_summary()
    decisions = recall_decisions(limit=5)

    return (
        f"ранковий бриф — {now}\n\n"
        f"{git_summary}\n\n"
        f"{decisions}\n\n"
        "план на сьогодні:\n"
        "- перевірити незакомічені зміни;\n"
        "- закрити поточний етап без ламання стабільної v1.8 бази;\n"
        "- після кожного робочого блоку робити маленький коміт;\n"
        "- в кінці дня зробити вечірній підсумок."
    )


def get_evening_debrief(user_text: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    text = (user_text or "").strip()

    items = _load_daily_log()

    item = {
        "timestamp": now,
        "summary_request": text,
    }

    items.append(item)
    _save_daily_log(items)

    git_summary = get_git_summary()

    return (
        f"вечірній підсумок — {now}\n\n"
        f"{git_summary}\n\n"
        "зафіксувала точку дня в daily_log.json.\n\n"
        "короткий шаблон підсумку:\n"
        "- що зробили: \n"
        "- що зламалось: \n"
        "- що пофіксили: \n"
        "- що не встигли: \n"
        "- наступний крок: "
    )