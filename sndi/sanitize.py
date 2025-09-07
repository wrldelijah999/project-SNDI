# sndi/sanitize.py
import re

BANNED_SUBSTRINGS = [
    "я тут", "щоб допомогти", "дай знати", "якщо потрібно",
    "підтримк", "натхнен", "я рада допомогти",
    "ми зробимо краще разом", "що далі", "на порядку денному"
]

EMOJI_RE = re.compile(
    r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF"
    r"\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF"
    r"\u2600-\u27BF]+", flags=re.UNICODE
)

def _remove_emojis(text: str) -> str:
    return EMOJI_RE.sub("", text)

def _purge_banned_substrings(ln: str) -> str:
    low = ln.lower()
    out = ln
    for s in BANNED_SUBSTRINGS:
        if s in low:
            # вирізаємо рівно підрядок (без краю рядка)
            out = re.sub(re.escape(s), "", out, flags=re.IGNORECASE)
    # колапс пробілів
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def sanitize(text: str) -> str:
    if not text:
        return "шум глушить канал. повтори."

    text = _remove_emojis(text)
    cleaned_lines = []

    for raw_ln in text.splitlines():
        ln = raw_ln.strip()
        if not ln:
            continue
        ln = _purge_banned_substrings(ln)
        if len(ln) < 3:  # занадто коротко після чистки — скипаємо
            continue
        cleaned_lines.append(ln)

    clean = "\n".join(cleaned_lines).strip()
    clean = re.sub(r"\s{2,}", " ", clean)

    if not clean:
        clean = "шум глушить канал. повтори."
    return clean




