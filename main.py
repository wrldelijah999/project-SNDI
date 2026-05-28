# main.py
"""
SNDI main entry point.

Цей файл більше НЕ містить:
- OpenAI API logic
- memory/history logic
- profile logic
- prompt assembly
- SystemManager logic

Він залишений як тонкий entry point і compatibility layer,
щоб старий gui.py міг далі робити: from main import sndi
"""

from sndi.core.conversation_core import ask


def sndi(user_text: str) -> str:
    """
    Backward-compatible wrapper для старого gui.py.

    Старий код у gui.py очікує функцію sndi(user_text),
    тому ми залишаємо цю функцію, але всередині вона просто
    викликає нове ядро conversation_core.ask().
    """
    return ask(user_text)


def main() -> None:
    """
    Запуск GUI-додатку.
    """
    from gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()