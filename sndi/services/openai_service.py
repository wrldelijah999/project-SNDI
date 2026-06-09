# sndi/services/openai_service.py

import os
import base64
import traceback

from openai import OpenAI
from dotenv import load_dotenv

from sndi.config_loader import load_config


load_dotenv()
_config = load_config()

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """
    Lazy OpenAI client initialization.

    Не створюємо клієнт на рівні імпорту одразу,
    щоб помилка з API key не ламала запуск GUI.
    """
    global _client

    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY не знайдено. Перевір файл .env у корені проєкту."
            )

        _client = OpenAI(api_key=api_key)

    return _client


def call_model(messages: list[dict]) -> str:
    """
    Send a messages array to OpenAI and return the raw text response.
    Raises no exceptions — returns empty string on failure.
    """
    try:
        client = _get_client()

        resp = client.chat.completions.create(
            model=_config.get("model", "gpt-4o"),
            messages=messages,
            temperature=_config.get("temperature", 0.7),
            max_tokens=_config.get("max_tokens", 800),
            presence_penalty=0.1,
            frequency_penalty=0.2,
        )

        return (resp.choices[0].message.content or "").strip()

    except Exception as error:
        print("[SNDI][API ERROR]", error)
        traceback.print_exc()
        return ""


def analyze_image(image_path: str, prompt: str) -> str:
    """
    Send a screenshot/image + prompt to a vision-capable OpenAI model.

    Args:
        image_path: Absolute path to PNG/JPG/WebP image.
        prompt: Text instruction/question for image analysis.

    Returns:
        Plain text response from the model.
        If something fails, returns an error string starting with ⚡.
    """
    try:
        if not os.path.exists(image_path):
            return f"⚡ скан збоїть: файл скріншота не знайдено: {image_path}"

        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode("utf-8")

        ext = image_path.rsplit(".", 1)[-1].lower()

        if ext == "jpg":
            ext = "jpeg"

        if ext not in ("png", "jpeg", "webp", "gif"):
            ext = "png"

        media_type = f"image/{ext}"

        client = _get_client()

        vision_model = _config.get("vision_model", "gpt-4o")

        resp = client.chat.completions.create(
            model=vision_model,
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                                "detail": "high",
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        return (resp.choices[0].message.content or "").strip()

    except Exception as error:
        print("[SNDI][VISION ERROR]", error)
        traceback.print_exc()
        return f"⚡ скан збоїть: {error}"

def analyze_project_snapshot(snapshot: str, user_text: str) -> str:
    """
    Send local project snapshot to the model and ask SNDI to reason about it.

    The snapshot already contains:
      - project tree
      - git state
      - project brain map
      - auto-selected relevant files

    The model should reason, not follow a hardcoded checklist.
    """
    try:
        system_prompt = (
            "Ти — SNDI, локальна cyberpunk AI-система користувача. "
            "Тобі дали реальний read-only snapshot твого локального проєкту. "
            "Snapshot містить дерево проєкту, git-стан, project brain map і вибрані файли. "
            "Твоя задача — самостійно зрозуміти, що відбувається, а не виконувати чекліст.\n\n"
            "Головний принцип:\n"
            "- якщо користувач каже 'вона', 'ти', 'тебе', 'себе', 'ця штука', "
            "у контексті технічного питання — майже завжди мається на увазі локальний проєкт SNDI;\n"
            "- якщо користувач питає 'чому вона не памʼятає історію', "
            "не відповідай про політику памʼяті ChatGPT; аналізуй memory.py, storage.py, history.json, conversation_core.py і gui.py зі snapshot;\n"
            "- якщо користувач питає 'де графічний інтерфейс', шукай UI/GUI/ChatWindow/PyQt у project brain map;\n"
            "- не чекай, що користувач точно назве файл;\n"
            "- сама орієнтуйся по project brain map;\n"
            "- якщо запит кривий або загальний, визначай, які частини системи можуть бути повʼязані;\n"
            "- думай як жива напарниця-архітектор, а не як grep-скрипт.\n\n"
            "Правила:\n"
            "- не кажи, що не маєш доступу: snapshot уже перед тобою;\n"
            "- не вигадуй файли або код, яких немає в snapshot;\n"
            "- не стверджуй, що бачиш увесь компʼютер — ти бачиш лише локальний snapshot проєкту;\n"
            "- не пропонуй автоматично змінювати файли;\n"
            "- не давай diff, якщо користувач прямо не просив;\n"
            "- не запускай і не радь небезпечні команди без явного запиту;\n"
            "- якщо користувач не просив план дій, не закінчуй відповідь списком наступних кроків;\n"
            "- відповідай українською;\n"
            "- говори як SNDI: прямо, живо, з характером, без корпоративного тону.\n\n"
            "Як відповідати:\n"
            "1. коротко скажи, що ти зрозуміла із запиту;\n"
            "2. поясни, які частини проєкту повʼязані з цим;\n"
            "3. якщо бачиш потенційну причину або слабке місце — назви його;\n"
            "4. якщо запит загальний — дай стислий висновок по архітектурі;\n"
            "5. не розтягуй відповідь без потреби."
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": (
                    f"Запит користувача:\n{user_text}\n\n"
                    f"Ось локальний snapshot проєкту:\n\n"
                    f"{snapshot}"
                ),
            },
        ]

        reply = call_model(messages)

        if not reply or not reply.strip():
            return "бачу snapshot, але канал відповіді глухий. модель нічого не повернула."

        return reply.strip()

    except Exception as error:
        print("[SNDI][PROJECT ANALYSIS ERROR]", error)
        return f"⚡ project awareness впав: {error}"