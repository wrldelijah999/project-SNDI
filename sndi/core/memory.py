# sndi/core/memory.py

import re
from sndi.storage import load_json, save_json


_AGE_RE = re.compile(
    r"\bмені\s+(\d{1,3})\b|\bмені\s+(\d{1,3})\s*рок(и|ів|у)?\b",
    re.IGNORECASE,
)


def load_profile() -> dict:
    profile, _ = load_json("profile.json", "memory/profile.json", {})
    if not isinstance(profile, dict):
        profile = {}
    return profile


def save_profile(p: dict) -> None:
    save_json("profile.json", p)


def maybe_update_profile(user_text: str) -> None:
    prof = load_profile()

    m = _AGE_RE.search(user_text)
    if m:
        age = next((g for g in m.groups() if g and g.isdigit()), None)
        if age:
            prof["age"] = int(age)
            save_profile(prof)


def ensure_sndi_capabilities() -> dict:
    """
    Ensure stable self-knowledge about SNDI capabilities.

    This writes to the REAL user profile:
      %APPDATA%\\SNDI\\profile.json

    Not to the seed file in project memory/profile.json.
    """
    prof = load_profile()

    capabilities = prof.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}

    capabilities.update(
        {
            "web_sensor": True,
            "screen_sensor": True,
            "project_sensor": True,
        }
    )

    sndi_state = prof.get("sndi_state")
    if not isinstance(sndi_state, dict):
        sndi_state = {}

    sndi_state.update(
        {
            "current_version": "1.6-dev",
            "canonical_name": "SNDI",
            "web_sensor_note": (
                "SNDI має доступ до інтернету через OpenAI web_search tool. "
                "Це не браузер напряму і не Google як сайт, а web sensor для актуальної інформації."
            ),
            "screen_sensor_note": (
                "SNDI має screen sensor і може аналізувати скріншот екрана, "
                "коли користувач просить подивитись на екран."
            ),
            "project_sensor_note": (
                "SNDI має local project sensor і може аналізувати локальний проєкт, "
                "project brain map, структуру файлів і git-стан."
            ),
        }
    )

    prof["capabilities"] = capabilities
    prof["sndi_state"] = sndi_state

    save_profile(prof)
    return prof


def get_profile_context_prompt() -> str:
    """
    Build stable profile/capabilities context for normal chat.

    This prevents SNDI from saying:
      - "I have no internet"
      - "I have no project access"
    after those sensors already exist.
    """
    profile = ensure_sndi_capabilities()

    capabilities = profile.get("capabilities", {})
    sndi_state = profile.get("sndi_state", {})

    lines: list[str] = []

    lines.append("Поточні стабільні можливості SNDI:")

    if capabilities.get("web_sensor"):
        lines.append(
            "- web_sensor: активний. SNDI може виходити в інтернет через OpenAI web_search tool, "
            "коли потрібна актуальна або зовнішня інформація."
        )

    if capabilities.get("screen_sensor"):
        lines.append(
            "- screen_sensor: активний. SNDI може аналізувати скріншот екрана."
        )

    if capabilities.get("project_sensor"):
        lines.append(
            "- project_sensor: активний. SNDI може аналізувати локальний проєкт SNDI, "
            "project brain map, структуру файлів і git-стан."
        )

    version = sndi_state.get("current_version")
    canonical_name = sndi_state.get("canonical_name")
    web_note = sndi_state.get("web_sensor_note")
    screen_note = sndi_state.get("screen_sensor_note")
    project_note = sndi_state.get("project_sensor_note")

    if version:
        lines.append(f"- current_version: {version}")

    if canonical_name:
        lines.append(f"- canonical_name: {canonical_name}")

    if web_note:
        lines.append(f"- web_sensor_note: {web_note}")

    if screen_note:
        lines.append(f"- screen_sensor_note: {screen_note}")

    if project_note:
        lines.append(f"- project_sensor_note: {project_note}")

    age = profile.get("age")
    if age:
        lines.append(f"- user_age: {age}")

    return "\n".join(lines)


def load_history(max_turns: int = 8) -> list[dict]:
    hist, _ = load_json("history.json", "memory/history.json", [])

    if not isinstance(hist, list):
        hist = []

    norm: list[dict] = []

    for m in hist:
        if not isinstance(m, dict):
            continue

        role = m.get("role")
        content = m.get("content")

        if not isinstance(content, str) or not content.strip():
            continue

        if role == "sndi":
            role = "assistant"

        if role in ("user", "assistant"):
            norm.append({"role": role, "content": content})

    return norm[-(max_turns * 2):]


def append_history(user_text: str, assistant_text: str) -> None:
    hist, _ = load_json("history.json", "memory/history.json", [])

    if not isinstance(hist, list):
        hist = []

    hist.append({"role": "user", "content": user_text})
    hist.append({"role": "assistant", "content": assistant_text})

    save_json("history.json", hist)