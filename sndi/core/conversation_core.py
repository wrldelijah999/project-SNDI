# sndi/core/conversation_core.py

from sndi.config_loader import load_config
from sndi.sanitize import sanitize
from sndi.core.memory import (
    load_profile, maybe_update_profile,
    load_history, append_history
)
from sndi.services.openai_service import call_model

_config = load_config()

def ask(user_text: str) -> str:
    """
    Build context, call the model, sanitize and persist the response.
    Does NOT handle system intents — caller is responsible for that.
    """
    maybe_update_profile(user_text)

    messages: list[dict] = [
        {"role": "system", "content": _config["system_prompt"]}
    ]

    dev = _config.get("developer_prompt")
    if dev:
        messages.append({"role": "system", "content": dev})

    prof = load_profile()
    if "age" in prof:
        messages.append({
            "role": "system",
            "content": f"Факт профілю: вік користувача = {prof['age']}."
        })

    messages.extend(load_history(max_turns=8))
    messages.append({"role": "user", "content": user_text})

    raw = call_model(messages)

    clean = sanitize(raw)
    if not clean.strip():
        clean = "шум глушить канал. повтори."

    append_history(user_text, clean)
    return clean