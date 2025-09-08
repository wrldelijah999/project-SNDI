# main.py
from dotenv import load_dotenv
import os, re, traceback
from openai import OpenAI

from sndi.config_loader import load_config
from sndi.sanitize import sanitize
from sndi.storage import load_json, save_json  # робота з %APPDATA%\SNDI

# --- конфіг + клієнт ---
config = load_config()
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# ---------- utils: profile ----------
def _load_profile() -> dict:
    profile, _ = load_json("profile.json", "memory/profile.json", {})
    return profile

def _save_profile(p: dict) -> None:
    save_json("profile.json", p)

# простенький приклад витягання факту (вік) з тексту користувача
AGE_RE = re.compile(r"\bмені\s+(\d{1,3})\b|\bмені\s+(\d{1,3})\s*рок(и|ів|у)?\b", re.IGNORECASE)

def _maybe_update_profile(user_text: str):
    prof = _load_profile()
    m = AGE_RE.search(user_text)
    if m:
        age = next((g for g in m.groups() if g), None)
        if age:
            prof["age"] = int(age)
            _save_profile(prof)

# ---------- utils: history ----------
def _load_history(max_turns: int = 8) -> list[dict]:
    """
    Читає історію з %APPDATA%\\SNDI\\history.json (seed: memory/history.json у пакеті),
    нормалізує ролі й повертає хвіст останніх ходів.
    """
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
    return norm[-max_turns * 2:]

def _append_history(user_text: str, assistant_text: str) -> None:
    hist, _ = load_json("history.json", "memory/history.json", [])
    if not isinstance(hist, list):
        hist = []
    hist.append({"role": "user", "content": user_text})
    hist.append({"role": "assistant", "content": assistant_text})
    save_json("history.json", hist)

# ---------- головна розмова ----------
def sndi(user_text: str) -> str:
    # 1) оновимо профіль базовими фактами
    _maybe_update_profile(user_text)

    # 2) промпт
    messages: list[dict] = [{"role": "system", "content": config["system_prompt"]}]
    dev = config.get("developer_prompt")
    if dev:
        messages.append({"role": "system", "content": dev})

    # підкинемо відомі факти з профілю
    prof = _load_profile()
    if "age" in prof:
        messages.append({"role": "system", "content": f"Факт профілю: вік користувача = {prof['age']}."})

    # історія
    messages.extend(_load_history(max_turns=8))

    # поточний запит
    messages.append({"role": "user", "content": user_text})

    # 3) виклик моделі
    raw = ""
    try:
        resp = client.chat.completions.create(
            model=config.get("model", "gpt-4o"),
            messages=messages,
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 800),
            presence_penalty=0.1,
            frequency_penalty=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("[SNDI][API ERROR]", e)
        traceback.print_exc()
        raw = ""

    # 4) санітизація
    clean = sanitize(raw)
    if not clean.strip():
        clean = "шум глушить канал. повтори."

    # 5) запис у пам'ять
    _append_history(user_text, clean)

    return clean
