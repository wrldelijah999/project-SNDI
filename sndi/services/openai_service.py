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