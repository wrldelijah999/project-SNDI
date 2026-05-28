# sndi/services/openai_service.py

import os
import traceback
from openai import OpenAI
from dotenv import load_dotenv
from sndi.config_loader import load_config

load_dotenv()
_config = load_config()
_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def call_model(messages: list[dict]) -> str:
    """
    Send a messages array to OpenAI and return the raw text response.
    Raises no exceptions — returns empty string on failure.
    """
    try:
        resp = _client.chat.completions.create(
            model=_config.get("model", "gpt-4o"),
            messages=messages,
            temperature=_config.get("temperature", 0.7),
            max_tokens=_config.get("max_tokens", 800),
            presence_penalty=0.1,
            frequency_penalty=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("[SNDI][API ERROR]", e)
        traceback.print_exc()
        return ""