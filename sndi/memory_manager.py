import os
import sys
import json
import shutil

APP_NAME = "SNDI"
SEED_PATH = os.path.join("memory", "history.json")

def _resource_base() -> str:
    """Базовий шлях до ресурсів (працює і в dev, і в зібраному exe)."""
    return getattr(sys, "_MEIPASS", os.path.abspath("."))

def resource_path(rel: str) -> str:
    return os.path.join(_resource_base(), rel)

def user_data_dir(app: str = APP_NAME) -> str:
    """Папка для робочих файлів користувача (APPDATA\SNDI)."""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, app)
    os.makedirs(path, exist_ok=True)
    return path

MEMORY_PATH = os.path.join(user_data_dir(), "history.json")

def load_history(system_prompt: str):
    """Завантажити історію або створити нову."""
    # якщо немає робочого history.json → копіюємо seed
    if not os.path.exists(MEMORY_PATH):
        seed = resource_path(SEED_PATH)
        if os.path.exists(seed):
            shutil.copyfile(seed, MEMORY_PATH)
        else:
            # fallback: створюємо з дефолтного промпта
            save_history([{"role": "system", "content": system_prompt}])
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # якщо файл битий → відновлюємо
        data = [{"role": "system", "content": system_prompt}]
        save_history(data)
        return data

def save_history(history):
    """Атомарно зберегти історію."""
    tmp = MEMORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MEMORY_PATH)
