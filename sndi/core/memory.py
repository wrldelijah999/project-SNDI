# sndi/core/memory.py

import re
from sndi.storage import load_json, save_json

_AGE_RE = re.compile(
    r"\bмені\s+(\d{1,3})\b|\bмені\s+(\d{1,3})\s*рок(и|ів|у)?\b",
    re.IGNORECASE
)

def load_profile() -> dict:
    profile, _ = load_json("profile.json", "memory/profile.json", {})
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

def load_history(max_turns: int = 8) -> list[dict]:
    hist, _ = load_json("history.json", "memory/history.json", [])
    norm: list[dict] = []
    for m in hist:
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