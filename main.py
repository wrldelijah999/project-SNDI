# main.py — Ініціалізація ядра SNDI та CLI-режим за потреби

import os
from dotenv import load_dotenv
from sndi.config_loader import load_config
from sndi.sndi_core import SNDI

# Завантаження .env та ініціалізація SNDI
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
config = load_config()
sndi = SNDI(api_key, config)

# CLI-режим для ручного тестування
if __name__ == "__main__":
    print("\U0001f527 SNDI запущено. Введи 'вихід' для завершення.")
    while True:
        user_input = input("\U0001f7e3 Ти: ")
        if user_input.lower() in ["вихід", "exit", "quit"]:
            print("\U0001f50c SNDI відключено.")
            break
        reply = sndi.ask(user_input)
        print("\U0001f535 SNDI:", reply)

#.\venv\Scripts\activate