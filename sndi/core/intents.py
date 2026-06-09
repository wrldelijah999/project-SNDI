# sndi/core/intents.py
"""
Lightweight intent detection for SNDI.

Each function returns True/False.
No OpenAI calls. No GUI imports. No side effects.

Add new intent checkers here as the feature set grows.
"""

import re


# ---------------------------------------------------------------------------
# Screen-scan intent
# ---------------------------------------------------------------------------

# Exact command triggers (stripped, lowercased comparison)
_SCAN_EXACT: frozenset[str] = frozenset({
    "/scan",
    "відскануй",
    "відскануй екран",
    "зроби скан",
    "зроби скан екрану",
    "scan",
    "scan screen",
    "look at screen",
    "analyze screen",
    "що ти бачиш",
    "що ти бачиш?",
})

# Substring / pattern triggers — any of these appearing anywhere in the message
_SCAN_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in [
        r"\b/scan\b",
        r"\bscan\b",
        r"відскануй",
        r"скан(уй|увати|ануй)?",
        r"зроби\s+скан",
        r"зроби\s+скрін",
        r"подивись\s+на\s+екран",
        r"глянь\s+на\s+екран",
        r"поглянь\s+на\s+екран",
        r"проаналізуй\s+екран",
        r"подивись\s+що\s+я\s+відкрив",
        r"глянь\s+що\s+в\s+мене\s+на\s+екрані",
        r"що\s+відбувається\s+на\s+екрані",
        r"що\s+тут\s+не\s+так",
        r"глянь\s+на\s+це",
        r"подивись\s+на\s+це",
        r"що\s+ти\s+бачиш",
        r"look\s+at\s+(my\s+)?screen",
        r"scan\s+(the\s+)?screen",
        r"analyze\s+(the\s+)?screen",
        r"what\s+do\s+you\s+see",
        r"check\s+(my\s+)?screen",
    ]
]


def is_screen_scan_intent(user_text: str) -> bool:
    """
    Return True if the user's message is a request for screen analysis.

    Works both for exact commands and natural phrases with extra words:
    - "відскануй екран"
    - "а ну відскануй екран, як тобі мої шпалери?"
    - "подивись на екран"
    - "що тут не так?"
    """
    text = user_text.strip()
    text_lower = text.lower()

    if text_lower in _SCAN_EXACT:
        return True

    for pattern in _SCAN_PATTERNS:
        if pattern.search(text):
            return True

    return False