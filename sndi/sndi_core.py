from openai import OpenAI
from .memory_manager import load_history, save_history
import re

class SNDI:
    def __init__(self, api_key, config):
        self.client = OpenAI(api_key=api_key)
        self.config = config
        self.system_prompt = config["system_prompt"]
        self.model = config.get("model", "gpt-4o")
        self.chat_history = load_history(self.system_prompt)

    def ask(self, prompt):
        self.chat_history.append({"role": "user", "content": prompt})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.chat_history,
            temperature=self.config.get("temperature", 0.9),
            max_tokens=self.config.get("max_tokens", 1200)
        )
        reply = response.choices[0].message.content

        reply = enforce_behavior(reply, self.config)
        
        self.chat_history.append({"role": "assistant", "content": reply})
        save_history(self.chat_history)
        return reply

def enforce_behavior(message, config):
    behavior = config.get("behavior", {})
    if behavior.get("avoid_redundant_questions", False):
        message = re.sub(r"(що на думці|що нового|обговоримо\?)", "", message, flags=re.I)
    if behavior.get("avoid_help_offers", False):
        message = re.sub(r"(дай знати.*допомога.*|я тут щоб допомогти.*)", "", message, flags=re.I)
    return message.strip()
