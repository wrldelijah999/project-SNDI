# sndi/core/intents.py

import re


def _normalize(text: str) -> str:
    """
    Soft normalization for Ukrainian/Russian/English mixed casual text.
    Мета — не ідеальна NLP-магія, а зробити router менш тупим.
    """
    text = text.strip().lower()

    replacements = {
        "ё": "е",
        "’": "'",
        "`": "'",
        "ʼ": "'",
        "проєкт": "проект",
        "памʼять": "память",
        "пам'ять": "память",
        "інтерфейс": "интерфейс",
        "історія": "история",
        "історію": "историю",
        "файлі": "файлі",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)
    return text


# ---------- screen scan intents ----------
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
    text = _normalize(user_text)

    for pattern in _SCAN_PATTERNS:
        if pattern.search(text):
            return True

    return False


# ---------- local project awareness intents ----------

_PROJECT_NAMES = {
    "sndi",
    "sndі",
    "сенді",
    "sandy",
    "санді",
    "асистент",
    "асистентка",
    "помічник",
    "помічниця",
}

_SELF_REFERENCES = {
    "ти",
    "тебе",
    "тобі",
    "твій",
    "твоя",
    "твоє",
    "вона",
    "її",
    "неї",
    "себе",
    "свій",
    "своя",
    "своє",
}

_PROJECT_WORDS = {
    "проект",
    "код",
    "репозиторій",
    "репа",
    "гіт",
    "git",
    "файл",
    "файли",
    "файлі",
    "папка",
    "папці",
    "директорія",
    "директорії",
    "структура",
    "архітектура",
    "модуль",
    "модулі",
    "клас",
    "класи",
    "функція",
    "функції",
    "скрипт",
    "скрипти",
    "python",
    "py",
}

_SYSTEM_PARTS = {
    "gui",
    "ui",
    "інтерфейс",
    "интерфейс",
    "графічний",
    "вікно",
    "окно",
    "чат",
    "повідомлення",
    "кнопка",
    "аватар",
    "sidebar",
    "екран",
    "скан",
    "скрін",
    "screenshot",
    "openai",
    "api",
    "модель",
    "відповідь",
    "відповіді",
    "промпт",
    "prompt",
    "характер",
    "тон",
    "config",
    "конфіг",
    "yaml",
    "память",
    "пам'ять",
    "історія",
    "история",
    "history",
    "memory",
    "storage",
    "appdata",
    "env",
    ".env",
    "ключ",
    "токен",
}

_PROBLEM_WORDS = {
    "чому",
    "чого",
    "чо",
    "чомуто",
    "нащо",
    "де",
    "куди",
    "звідки",
    "як",
    "який",
    "яка",
    "яке",
    "які",
    "що",
    "хто",
    "коли",
    "знайди",
    "подивись",
    "глянь",
    "перевір",
    "розбери",
    "розберися",
    "проаналізуй",
    "поясни",
    "покажи",
}

_ACTION_OR_DEBUG_WORDS = {
    "не працює",
    "не паше",
    "ламається",
    "зламалось",
    "зламалася",
    "не бачить",
    "не розуміє",
    "не памятає",
    "не пам'ятає",
    "не зберігає",
    "не записує",
    "не відкриває",
    "не запускається",
    "не відповідає",
    "не знаходить",
    "помилка",
    "error",
    "traceback",
    "bug",
    "баг",
    "проблема",
    "де знаходиться",
    "де лежить",
    "де записується",
    "де зберігається",
    "де прописано",
    "в якому файлі",
    "у якому файлі",
    "який файл",
    "які файли",
    "що відповідає",
    "хто відповідає",
    "як влаштовано",
    "як працює",
    "з чого складається",
}


_DIRECT_PROJECT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in [
        r"подивись\s+проект",
        r"глянь\s+проект",
        r"переглянь\s+проект",
        r"проаналізуй\s+проект",
        r"оцін(и|ити)\s+проект",
        r"стан\s+проекту",
        r"структур(а|у)\s+проекту",
        r"директор(ія|ію)\s+проекту",
        r"папк(а|у)\s+проекту",
        r"локальн(ий|ого)\s+проект",
        r"подивись\s+sndi",
        r"глянь\s+sndi",
        r"проаналізуй\s+sndi",
        r"подивись\s+себе",
        r"розбери\s+себе",
        r"як\s+ти\s+влаштована",
        r"як\s+ти\s+працюєш",
        r"з\s+чого\s+ти\s+складаєшся",
        r"що\s+в\s+тебе\s+під\s+капотом",
        r"project\s+awareness",
        r"look\s+at\s+project",
        r"analyze\s+project",
        r"check\s+project",
        r"project\s+structure",
    ]
]


def _contains_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


def _contains_problem_phrase(text: str) -> bool:
    return any(phrase in text for phrase in _ACTION_OR_DEBUG_WORDS)


def is_project_awareness_intent(user_text: str) -> bool:
    """
    Broad router for SNDI local project awareness.

    Important:
    This function does NOT answer the question.
    It only decides whether SNDI should collect local project context.

    Philosophy:
    If user talks about "you / her / SNDI / project / files / where / why broken",
    assume they likely mean the local SNDI project.
    """
    text = _normalize(user_text)

    # 1. Direct project-awareness phrases.
    for pattern in _DIRECT_PROJECT_PATTERNS:
        if pattern.search(text):
            return True

    has_project_name = _contains_any(text, _PROJECT_NAMES)
    has_self_reference = _contains_any(text, _SELF_REFERENCES)
    has_project_word = _contains_any(text, _PROJECT_WORDS)
    has_system_part = _contains_any(text, _SYSTEM_PARTS)
    has_question_word = _contains_any(text, _PROBLEM_WORDS)
    has_problem_phrase = _contains_problem_phrase(text)

    # 2. "подивись проект, де..." / "глянь код, чому..."
    if has_project_word and (has_question_word or has_problem_phrase or has_system_part):
        return True

    # 3. "де gui", "де памʼять", "де openai", "що відповідає за інтерфейс"
    if has_system_part and (has_question_word or has_problem_phrase):
        return True

    # 4. "чому вона не памʼятає історію?"
    # "вона" + memory/history/problem => це майже точно про SNDI.
    if has_self_reference and (has_system_part or has_problem_phrase):
        return True

    # 5. "що в тебе з памʼяттю", "де в тебе промпт"
    if has_self_reference and has_question_word:
        return True

    # 6. "SNDI не памʼятає", "SNDI не бачить", "SNDI відповідає дивно"
    if has_project_name and (has_system_part or has_problem_phrase or has_question_word):
        return True

    # 7. Дуже часті живі фрази без слова "проект"
    fuzzy_phrases = [
        "графічний интерфейс",
        "графічний інтерфейс",
        "файл графічного",
        "де gui",
        "де ui",
        "де чат",
        "де память",
        "де пам'ять",
        "де історія",
        "де history",
        "де memory",
        "де промпт",
        "де prompt",
        "де openai",
        "де api",
        "де конфіг",
        "де config",
        "де аватар",
        "де кнопка",
        "де відповідь",
        "де повідомлення",
        "що за що відповідає",
        "хто за що відповідає",
        "чого вона не",
        "чому вона не",
        "чого ти не",
        "чому ти не",
        "де воно лежить",
        "де це лежить",
        "де воно знаходиться",
        "де це знаходиться",
    ]

    if any(phrase in text for phrase in fuzzy_phrases):
        return True

    return False