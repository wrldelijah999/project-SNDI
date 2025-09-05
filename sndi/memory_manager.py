import os
import json

MEMORY_PATH = "memory/history.json"

def ensure_memory_dir():
    os.makedirs("memory", exist_ok=True)

def load_history(system_prompt):
    ensure_memory_dir()
    if os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return [{"role": "system", "content": system_prompt}]

def save_history(history):
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
