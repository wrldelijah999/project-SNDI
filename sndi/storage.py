import os
import sys
import json
import shutil

APP_NAME = "SNDI"

def _resource_base() -> str:
    """База для ресурсів (dist або корінь проєкту)."""
    return getattr(sys, "_MEIPASS", os.path.abspath("."))

def resource_path(rel: str) -> str:
    return os.path.join(_resource_base(), rel)

def user_data_dir(app: str = APP_NAME) -> str:
    """%APPDATA%\SNDI — тека для робочих файлів користувача."""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, app)
    os.makedirs(path, exist_ok=True)
    return path

def _seed_copy_if_missing(name: str, seed_rel: str, default_obj):
    """Створює %APPDATA%\SNDI\<name>, копіюючи seed із пакета або пише дефолт."""
    dst = os.path.join(user_data_dir(), name)
    if not os.path.exists(dst):
        src = resource_path(seed_rel)
        if os.path.exists(src):
            shutil.copyfile(src, dst)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(default_obj, f, ensure_ascii=False, indent=2)
    return dst

def load_json(name: str, seed_rel: str, default_obj):
    """
    name: як назвати файл у %APPDATA%\\SNDI (напр. 'history.json')
    seed_rel: шлях до насіннєвого файлу в пакеті (напр. 'memory/history.json')
    """
    path = _seed_copy_if_missing(name, seed_rel, default_obj)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path
    except Exception:
        # робимо бекап і відновлюємо дефолт
        try:
            shutil.copyfile(path, path + ".bak")
        except Exception:
            pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_obj, f, ensure_ascii=False, indent=2)
        return default_obj, path

def save_json(name: str, data):
    path = os.path.join(user_data_dir(), name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path

# Зручні обгортки для історії (не обов'язково, але хай будуть)
def load_history(default_system_prompt: str = ""):
    default = [{"role": "system", "content": default_system_prompt}] if default_system_prompt else []
    return load_json("history.json", "memory/history.json", default)[0]

def save_history(history):
    return save_json("history.json", history)
