from __future__ import annotations

from PyQt6.QtWidgets import QApplication


def get_clipboard_text(max_chars: int = 6000) -> str:
    """
    Read text from system clipboard.

    Safe rule:
    SNDI should call this only when user explicitly asks about copied text.
    """
    app = QApplication.instance()

    if app is None:
        return ""

    text = app.clipboard().text() or ""
    text = text.strip()

    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...clipboard truncated...]"

    return text