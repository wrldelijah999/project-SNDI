from pathlib import Path
from dotenv import load_dotenv
import json
import os
import re
import traceback
from openai import OpenAI

from sndi.config_loader import load_config
from sndi.sanitize import sanitize

# --- конфіг + клієнт ---
config = load_config()
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# --- шляхи пам'яті ---
MEMORY_PATH = Path("memory/history.json")
PROFILE_PATH = Path("memory/profile.json")
MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------- utils: profile memory ----------
def _load_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            traceback.print_exc()
    return {}

def _save_profile(p: dict) -> None:
    try:
        PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        traceback.print_exc()

# витягаємо прості факти з юзерського тексту (наприклад: "мені 23", "мені 23 роки")
AGE_RE = re.compile(r"\bмені\s+(\d{1,3})\b|\bмені\s+(\d{1,3})\s*рок(и|ів|ів|у)?\b", re.IGNORECASE)

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
    Читає останні max_turns*2 повідомлень з history.json і нормалізує ролі:
    - "sndi" -> "assistant"
    - пропускає порожні контенти
    """
    if not MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        norm = []
        for m in data:
            role = m.get("role")
            content = m.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if role == "sndi":
                role = "assistant"
            if role in ("user", "assistant"):  # тільки ці дві ролі даємо в модель
                norm.append({"role": role, "content": content})
        return norm[-max_turns * 2:]
    except Exception:
        traceback.print_exc()
        return []

def _append_history(user_text: str, assistant_text: str) -> None:
    """Додає пару ходів у кінець history.json, нічого не видаляючи."""
    try:
        if MEMORY_PATH.exists():
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        else:
            data = []
        data.append({"role": "user", "content": user_text})
        # ЗБЕРІГАЄМО як 'assistant' (НЕ 'sndi'), щоб потім не губити
        data.append({"role": "assistant", "content": assistant_text})
        MEMORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        traceback.print_exc()

# ---------- головна розмова ----------
def sndi(user_text: str) -> str:
    # 1) оновимо профіль простими фактами з юзерського меседжа
    _maybe_update_profile(user_text)

    # 2) будуємо промпт
    messages = [{"role": "system", "content": config["system_prompt"]}]
    dev = config.get("developer_prompt")
    if dev:
        messages.append({"role": "system", "content": dev})

    # 2.1) якщо в профілі є вік — підкинемо як контекстну довідку (system)
    prof = _load_profile()
    if "age" in prof:
        messages.append({"role": "system", "content": f"Факт профілю: вік користувача = {prof['age']}."})

    # 2.2) тягнемо історію ходів
    messages.extend(_load_history(max_turns=8))

    # 2.3) поточний запит
    messages.append({"role": "user", "content": user_text})

    # 3) виклик моделі
    raw = ""
    try:
        resp = client.chat.completions.create(
            model=config["model"],
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
