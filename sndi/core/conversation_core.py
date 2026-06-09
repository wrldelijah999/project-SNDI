# sndi/core/conversation_core.py

from sndi.config_loader import load_config
from sndi.sanitize import sanitize
from sndi.core.memory import (
    maybe_update_profile,
    load_history,
    append_history,
    get_profile_context_prompt,
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
        {
            "role": "system",
            "content": _config["system_prompt"],
        }
    ]

    dev = _config.get("developer_prompt")
    if dev:
        messages.append(
            {
                "role": "system",
                "content": dev,
            }
        )

    profile_context = get_profile_context_prompt()
    if profile_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Стабільний профіль, стан і можливості SNDI:\n"
                    f"{profile_context}\n\n"
                    "Це актуальний стан самої SNDI у цьому desktop-застосунку.\n"
                    "Не супереч цьому в normal chat.\n"
                    "Якщо web_sensor активний — не кажи, що інтернету немає.\n"
                    "Якщо project_sensor активний — не кажи, що немає доступу до локального проєкту.\n"
                    "Якщо screen_sensor активний — не кажи, що не можеш бачити екран, коли користувач просить скан.\n"
                    "Пояснюй чесно: web sensor — це OpenAI web_search tool, project sensor — локальний snapshot/brain map, screen sensor — скріншот екрана."
                ),
            }
        )

    messages.extend(load_history(max_turns=8))

    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    raw = call_model(messages)

    clean = sanitize(raw)
    if not clean.strip():
        clean = "шум глушить канал. повтори."

    append_history(user_text, clean)
    return clean