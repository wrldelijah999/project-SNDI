from __future__ import annotations

import re

from sndi.core.action_plan import ActionPlan
from sndi.core.intents import is_screen_scan_intent, is_project_awareness_intent


def _normalize(text: str) -> str:
    """
    Normalize user text for fast local routing checks.
    """
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _strip_decision_prefix(user_text: str) -> str:
    """
    Extract decision text from phrases like:
    - зафіксуй рішення: ...
    - запиши рішення ...
    - record decision: ...
    """
    return re.sub(
        r"^(сенді,?\s*)?(зафіксуй рішення|запиши рішення|record decision)\s*:?",
        "",
        user_text,
        flags=re.IGNORECASE,
    ).strip()


def looks_like_system_request(user_text: str) -> bool:
    """
    Local fast filter for obvious PC/system actions.
    No OpenAI call here.
    """
    text = _normalize(user_text)

    system_phrases = (
        "відкрий",
        "запусти",
        "закрий",
        "вируби",
        "заверши",
        "перезапусти",
        "відкрий сайт",
        "відкрий папку",
        "відкрий файл",
        "знайди файл",
        "онови індекс",
        "refresh index",
        "open",
        "close",
        "kill",
        "launch",
        "start",
    )

    return any(phrase in text for phrase in system_phrases)

def _extract_quoted_values(user_text: str) -> list[str]:
    """
    Extract values inside quotes.

    Supports:
    - "path"
    - 'path'
    - «path»
    """
    text = user_text or ""

    values: list[str] = []
    values.extend(re.findall(r'"([^"]+)"', text))
    values.extend(re.findall(r"'([^']+)'", text))
    values.extend(re.findall(r"«([^»]+)»", text))

    return [value.strip() for value in values if value.strip()]


def _looks_like_windows_path(value: str) -> bool:
    value = (value or "").strip()

    if not value:
        return False

    lowered = value.lower()

    return (
        bool(re.match(r"^[a-zA-Z]:[\\/]", value))
        or lowered.startswith("%userprofile%")
        or lowered.startswith("%appdata%")
        or lowered.startswith("~")
        or "\\" in value
        or "/" in value
    )


def _extract_first_path(user_text: str) -> str:
    """
    Conservative path extraction.

    Priority:
    1. quoted value;
    2. Windows path like C:\\... until sentence end;
    3. empty string.
    """
    quoted = _extract_quoted_values(user_text)

    for item in quoted:
        if _looks_like_windows_path(item):
            return item

    # C:\Something\Something.txt
    match = re.search(r"([a-zA-Z]:[\\/][^\n\r]+)", user_text or "")

    if match:
        value = match.group(1).strip()

        # Trim common trailing command words if user wrote a sentence.
        for stop_word in (
            " в ",
            " до ",
            " як ",
            " на ",
            " from ",
            " to ",
        ):
            if stop_word in value:
                value = value.split(stop_word, 1)[0].strip()

        return value.strip().strip('"').strip("'")

    return ""


def _extract_two_paths(user_text: str) -> tuple[str, str]:
    """
    Extract source and destination.

    Best UX: user should quote paths:
    скопіюй "C:\\a.txt" в "C:\\b.txt"
    """
    quoted = _extract_quoted_values(user_text)

    if len(quoted) >= 2:
        return quoted[0], quoted[1]

    text = user_text or ""

    # fallback: source to destination with simple unquoted Windows paths
    matches = re.findall(r"([a-zA-Z]:[\\/][^\n\r\"']+)", text)

    if len(matches) >= 2:
        return matches[0].strip(), matches[1].strip()

    return "", ""


def _extract_find_query_and_root(user_text: str) -> tuple[str, str]:
    """
    Expected:
    знайди файл "hello" в "C:\\SNDI_TEST_SAFE_OPS"
    """
    quoted = _extract_quoted_values(user_text)

    if len(quoted) >= 2:
        return quoted[0], quoted[1]

    if len(quoted) == 1:
        first = quoted[0]

        if _looks_like_windows_path(first):
            return "", first

        root = _extract_first_path(user_text)
        return first, root

    return "", _extract_first_path(user_text)


def _extract_new_name(user_text: str) -> str:
    """
    Expected:
    перейменуй "C:\\a.txt" на "b.txt"
    """
    quoted = _extract_quoted_values(user_text)

    if len(quoted) >= 2:
        return quoted[1]

    lowered = (user_text or "").lower()

    if " на " in lowered:
        return (user_text or "").split(" на ", 1)[1].strip().strip('"').strip("'")

    return ""


def _extract_create_file_content(user_text: str) -> str:
    lowered = (user_text or "").lower()

    for marker in (" з текстом ", " із текстом ", " with text "):
        if marker in lowered:
            index = lowered.find(marker)
            return user_text[index + len(marker):].strip().strip('"').strip("'")

    return ""


def _extract_replace_parts(user_text: str) -> tuple[str, str, str]:
    """
    Expected:
    заміни "old" на "new" у файлі "C:\\file.txt"

    Returns:
    old_text, new_text, path
    """
    quoted = _extract_quoted_values(user_text)

    if len(quoted) >= 3:
        return quoted[0], quoted[1], quoted[2]

    return "", "", _extract_first_path(user_text)


def _file_plan(
    action: str,
    user_text: str,
    target: str = "",
    confidence: float = 0.92,
    metadata: dict | None = None,
    reason: str = "",
):
    return ActionPlan(
        action=action,
        target=target,
        query=user_text,
        confidence=confidence,
        requires_confirmation=False,
        reason=reason or f"v1.11 file/app action: {action}",
        metadata=metadata or {},
    )


def decide_action(user_text: str) -> ActionPlan:
    """
    Hybrid Action Router for SNDI v1.9.

    Principle:
    - Fast local checks first.
    - No extra LLM call for simple chat.
    - Existing tools/threads will still be used by GUI.
    - This router decides the action type, not the final answer.
    """
    text = _normalize(user_text)

    if not text:
        return ActionPlan(
            action="chat",
            query=user_text,
            confidence=1.0,
            reason="empty or whitespace input",
        )

    if is_screen_scan_intent(user_text):
        return ActionPlan(
            action="screen_scan",
            query=user_text,
            confidence=1.0,
            reason="local screen scan intent matched",
        )

    if any(
        phrase in text
        for phrase in (
            "зафіксуй рішення",
            "запиши рішення",
            "record decision",
        )
    ):
        decision_text = _strip_decision_prefix(user_text)

        return ActionPlan(
            action="record_decision",
            target="decision_log",
            query=decision_text,
            confidence=0.98,
            requires_confirmation=False,
            reason="user explicitly wants to record a decision",
        )

    if any(
        phrase in text
        for phrase in (
            "що ми вирішили",
            "які рішення",
            "нагадай рішення",
            "покажи рішення",
            "decision log",
        )
    ):
        return ActionPlan(
            action="recall_decisions",
            target="decision_log",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user asks to recall previous decisions",
        )


    if any(
        phrase in text
        for phrase in (
            "що за помилка",
            "поясни помилку",
            "traceback",
            "exception",
            "nameerror",
            "typeerror",
            "attributeerror",
            "importerror",
            "modulenotfounderror",
            "syntaxerror",
        )
    ):
        return ActionPlan(
            action="error_explain",
            query=user_text,
            confidence=0.88,
            requires_confirmation=False,
            reason="user asks to explain an error or traceback",
        )

    if any(
        phrase in text
        for phrase in (
            "перевір код",
            "перевір цей код",
            "перевір код в буфері",
            "перевір код у буфері",
            "глянь код",
            "глянь цей код",
            "переглянь код",
            "проаналізуй код",
            "проаналізуй цей код",
            "що не так з кодом",
            "ревʼю коду",
            "рев'ю коду",
            "code review",
            "review code",
        )
    ):
        return ActionPlan(
            action="code_review",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user asks for code review",
        )
    
    if any(
        phrase in text
        for phrase in (
            "що в буфері",
            "в буфері",
            "буфер обміну",
            "скопійоване",
            "clipboard",
            "поясни це",
            "поясни скопійоване",
        )
    ):
        return ActionPlan(
            action="clipboard_explain",
            target="clipboard",
            query=user_text,
            confidence=0.85,
            requires_confirmation=False,
            reason="user refers to clipboard/copied content",
        )

    if any(
        phrase in text
        for phrase in (
            "що по проєкту",
            "що по проекту",
            "git status",
            "яка гілка",
            "що не закомічено",
            "що незакомічено",
            "останній коміт",
            "останній тег",
        )
    ):
        return ActionPlan(
            action="git_summary",
            target="current_project",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user asks about git/project state",
        )

    if any(
        phrase in text
        for phrase in (
            "що з компом",
            "стан компа",
            "стан пк",
            "pc health",
            "cpu",
            "ram",
            "оперативка",
            "диск",
            "навантаження",
        )
    ):
        return ActionPlan(
            action="pc_health",
            target="local_pc",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user asks about local PC health",
        )

    if any(
        phrase in text
        for phrase in (
            "ранковий бриф",
            "що сьогодні робимо",
            "план на сьогодні",
            "morning brief",
        )
    ):
        return ActionPlan(
            action="morning_brief",
            target="daily_state",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user asks for morning brief",
        )

    if any(
        phrase in text
        for phrase in (
            "вечірній підсумок",
            "підсумок дня",
            "запиши підсумок",
            "evening debrief",
        )
    ):
        return ActionPlan(
            action="evening_debrief",
            target="daily_state",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user wants daily debrief",
        )

    if any(
        phrase in text
        for phrase in (
            "увімкни автозапуск",
            "включи автозапуск",
            "запускайся разом з windows",
            "запускайся разом із windows",
            "запускайся при старті windows",
            "autostart on",
            "enable autostart",
        )
    ):
        return ActionPlan(
            action="autostart_enable",
            target="windows_startup",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to enable Windows autostart",
        )

    if any(
        phrase in text
        for phrase in (
            "вимкни автозапуск",
            "відключи автозапуск",
            "не запускайся разом з windows",
            "не запускайся разом із windows",
            "не запускайся при старті windows",
            "autostart off",
            "disable autostart",
        )
    ):
        return ActionPlan(
            action="autostart_disable",
            target="windows_startup",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to disable Windows autostart",
        )

    if any(
        phrase in text
        for phrase in (
            "статус автозапуску",
            "чи увімкнений автозапуск",
            "чи включений автозапуск",
            "autostart status",
        )
    ):
        return ActionPlan(
            action="autostart_status",
            target="windows_startup",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user asks for Windows autostart status",
        )
    
    if any(
        phrase in text
        for phrase in (
            "увімкни озвучку",
            "включи озвучку",
            "озвучуй відповіді",
            "tts on",
            "speak replies on",
        )
    ):
        return ActionPlan(
            action="voice_reply_enable",
            target="tts",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to enable voice replies",
        )

    if any(
        phrase in text
        for phrase in (
            "вимкни озвучку",
            "відключи озвучку",
            "не озвучуй відповіді",
            "tts off",
            "speak replies off",
        )
    ):
        return ActionPlan(
            action="voice_reply_disable",
            target="tts",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to disable voice replies",
        )

    if any(
        phrase in text
        for phrase in (
            "статус озвучки",
            "чи увімкнена озвучка",
            "tts status",
            "speak replies status",
        )
    ):
        return ActionPlan(
            action="voice_reply_status",
            target="tts",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user asks for voice reply status",
        )

    if any(
        phrase in text
        for phrase in (
            "слухай команду",
            "прослухай команду",
            "голосова команда",
            "listen once",
            "voice command",
        )
    ):
        return ActionPlan(
            action="voice_once",
            target="microphone",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants one-shot voice command input",
        )
    
    if any(
        phrase in text
        for phrase in (
            "почни слухати",
            "слухай мене",
            "увімкни голос",
            "включи голос",
            "start listening",
            "voice on",
        )
    ):
        return ActionPlan(
            action="voice_start",
            target="microphone",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to start wake word voice mode",
        )

    if any(
        phrase in text
        for phrase in (
            "перестань слухати",
            "вимкни голос",
            "відключи голос",
            "stop listening",
            "voice off",
        )
    ):
        return ActionPlan(
            action="voice_stop",
            target="microphone",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to stop wake word voice mode",
        )

    if any(
        phrase in text
        for phrase in (
            "перемкни голос",
            "toggle voice",
            "voice toggle",
        )
    ):
        return ActionPlan(
            action="voice_toggle",
            target="microphone",
            query=user_text,
            confidence=0.9,
            requires_confirmation=False,
            reason="user wants to toggle voice mode",
        )
    
        # ---------- v1.11 app mode actions ----------
    if any(
        phrase in text
        for phrase in (
            "закріпи себе як програму",
            "створи ярлик",
            "створи ярлик на робочому столі",
            "додай себе в пуск",
            "install shortcuts",
        )
    ):
        return _file_plan(
            action="app_install_shortcuts",
            user_text=user_text,
            target="windows_shortcuts",
            confidence=0.95,
            reason="user wants to install SNDI shortcuts",
        )

    if any(
        phrase in text
        for phrase in (
            "прибери ярлик",
            "видали ярлик",
            "remove shortcuts",
            "uninstall shortcuts",
        )
    ):
        return _file_plan(
            action="app_remove_shortcuts",
            user_text=user_text,
            target="windows_shortcuts",
            confidence=0.95,
            reason="user wants to remove SNDI shortcuts",
        )

    if any(
        phrase in text
        for phrase in (
            "статус програми",
            "ти dev чи exe",
            "ти dev або exe",
            "app status",
            "runtime status",
        )
    ):
        return _file_plan(
            action="app_runtime_status",
            user_text=user_text,
            target="runtime",
            confidence=0.95,
            reason="user asks for SNDI runtime status",
        )

    if any(
        phrase in text
        for phrase in (
            "статус білда",
            "статус build",
            "build status",
            "статус exe",
        )
    ):
        return _file_plan(
            action="app_build_status",
            user_text=user_text,
            target="build",
            confidence=0.95,
            reason="user asks for SNDI build status",
        )

    # ---------- v1.11 action log ----------
    if any(
        phrase in text
        for phrase in (
            "покажи action log",
            "останні дії",
            "що ти робила з файлами",
            "історія дій",
            "action log",
        )
    ):
        return _file_plan(
            action="action_log_show",
            user_text=user_text,
            target="action_log",
            confidence=0.95,
            reason="user asks for recent SNDI actions",
        )

    # ---------- v1.11 read-only file actions ----------
    if any(
        phrase in text
        for phrase in (
            "покажи файли в",
            "список файлів",
            "що в папці",
            "list folder",
            "list directory",
        )
    ):
        path = _extract_first_path(user_text)
        return _file_plan(
            action="file_list",
            user_text=user_text,
            target=path,
            metadata={"path": path},
            reason="user wants to list directory",
        )

    if any(
        phrase in text
        for phrase in (
            "знайди файл",
            "знайди папку",
            "пошук файлу",
            "find file",
            "find folder",
        )
    ):
        query, root = _extract_find_query_and_root(user_text)
        return _file_plan(
            action="file_find",
            user_text=user_text,
            target=root,
            metadata={"root": root, "query": query},
            reason="user wants to find file/folder",
        )

    if any(
        phrase in text
        for phrase in (
            "прочитай файл",
            "покажи preview файлу",
            "preview файлу",
            "read file",
            "read preview",
        )
    ):
        path = _extract_first_path(user_text)
        return _file_plan(
            action="file_read_preview",
            user_text=user_text,
            target=path,
            metadata={"path": path},
            reason="user wants text file preview",
        )

    if any(
        phrase in text
        for phrase in (
            "відкрий папку",
            "відкрий файл",
            "open folder",
            "open file",
        )
    ):
        path = _extract_first_path(user_text)
        return _file_plan(
            action="file_open",
            user_text=user_text,
            target=path,
            metadata={"path": path},
            reason="user wants to open a file/folder path",
        )

    # ---------- v1.11 mutation preview actions ----------
    if any(
        phrase in text
        for phrase in (
            "створи папку",
            "створити папку",
            "create folder",
            "make folder",
        )
    ):
        path = _extract_first_path(user_text)
        return _file_plan(
            action="file_create_folder",
            user_text=user_text,
            target=path,
            metadata={"path": path},
            reason="user wants to create folder with confirmation",
        )

    if any(
        phrase in text
        for phrase in (
            "створи файл",
            "створити файл",
            "create file",
        )
    ):
        path = _extract_first_path(user_text)
        content = _extract_create_file_content(user_text)

        return _file_plan(
            action="file_create_file",
            user_text=user_text,
            target=path,
            metadata={
                "path": path,
                "content": content,
                "overwrite": False,
            },
            reason="user wants to create file with confirmation",
        )

    if any(
        phrase in text
        for phrase in (
            "скопіюй файл",
            "скопіюй папку",
            "копіюй файл",
            "copy file",
            "copy folder",
        )
    ):
        source, destination = _extract_two_paths(user_text)

        return _file_plan(
            action="file_copy",
            user_text=user_text,
            target=destination,
            metadata={
                "source": source,
                "destination": destination,
            },
            reason="user wants to copy path with confirmation",
        )

    if any(
        phrase in text
        for phrase in (
            "перемісти файл",
            "перемісти папку",
            "move file",
            "move folder",
        )
    ):
        source, destination = _extract_two_paths(user_text)

        return _file_plan(
            action="file_move",
            user_text=user_text,
            target=destination,
            metadata={
                "source": source,
                "destination": destination,
            },
            reason="user wants to move path with confirmation",
        )

    if any(
        phrase in text
        for phrase in (
            "перейменуй файл",
            "перейменуй папку",
            "rename file",
            "rename folder",
        )
    ):
        path = _extract_first_path(user_text)
        new_name = _extract_new_name(user_text)

        return _file_plan(
            action="file_rename",
            user_text=user_text,
            target=path,
            metadata={
                "path": path,
                "new_name": new_name,
            },
            reason="user wants to rename path with confirmation",
        )

    if any(
        phrase in text
        for phrase in (
            "видали файл",
            "видали папку",
            "delete file",
            "delete folder",
        )
    ):
        path = _extract_first_path(user_text)

        return _file_plan(
            action="file_delete_safe",
            user_text=user_text,
            target=path,
            metadata={"path": path},
            reason="user wants safe delete with confirmation",
        )

    if (
        "заміни текст" in text
        or "replace text" in text
        or (
            text.startswith("заміни ")
            and " на " in text
            and (" у файлі " in text or " в файлі " in text)
        )
    ):
        
        old_text, new_text, path = _extract_replace_parts(user_text)

        return _file_plan(
            action="file_edit_preview",
            user_text=user_text,
            target=path,
            metadata={
                "path": path,
                "old_text": old_text,
                "new_text": new_text,
            },
            reason="user wants text replace preview with confirmation",
        )

    if looks_like_system_request(user_text):
        return ActionPlan(
            action="system_action",
            query=user_text,
            confidence=0.82,
            requires_confirmation=False,
            reason="message looks like a local system action",
        )
    
    if any(
        phrase in text
        for phrase in (
            "сховайся в трей",
            "сховай в трей",
            "згорнись в трей",
            "hide to tray",
            "minimize to tray",
        )
    ):
        return ActionPlan(
            action="tray_hide",
            target="system_tray",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to hide SNDI to tray",
        )

    if any(
        phrase in text
        for phrase in (
            "відкрийся з трея",
            "покажи вікно",
            "поверни вікно",
            "show window",
            "show sndi",
        )
    ):
        return ActionPlan(
            action="tray_show",
            target="system_tray",
            query=user_text,
            confidence=0.95,
            requires_confirmation=False,
            reason="user wants to show SNDI window from tray",
        )

    if is_project_awareness_intent(user_text):
        return ActionPlan(
            action="project_awareness",
            query=user_text,
            confidence=0.75,
            requires_confirmation=False,
            reason="message looks related to local SNDI project",
        )

    if any(
        phrase in text
        for phrase in (
            "знайди в інтернеті",
            "пошукай",
            "подивись в інтернеті",
            "актуально",
            "новини",
            "ціна",
            "курс",
            "погода",
            "сьогодні",
            "зараз",
            "дай лінк",
            "дай посилання",
        )
    ):
        return ActionPlan(
            action="web_search",
            query=user_text,
            confidence=0.78,
            requires_confirmation=False,
            reason="message likely needs current web data",
        )

    return ActionPlan(
        action="chat",
        query=user_text,
        confidence=1.0,
        requires_confirmation=False,
        reason="normal chat",
    )



def execute_action(plan: ActionPlan, user_text: str) -> str | None:
    """
    Execute only safe synchronous actions.

    GUI still handles async actions:
    - chat
    - system_action
    - web_search
    - screen_scan
    - project_awareness
    """

    if plan.action == "record_decision":
        from sndi.core.decision_log import record_decision

        return record_decision(plan.query or user_text)
    

    if plan.action == "recall_decisions":
        from sndi.core.decision_log import recall_decisions

        return recall_decisions(plan.query or user_text)
    
    if plan.action == "git_summary":
        from sndi.tools.git_tools import get_git_summary

        return get_git_summary()
    
    if plan.action == "morning_brief":
        from sndi.core.daily_brief import get_morning_brief

        return get_morning_brief()

    if plan.action == "evening_debrief":
        from sndi.core.daily_brief import get_evening_debrief

        return get_evening_debrief(plan.query or user_text)
    
    if plan.action == "pc_health":
        from sndi.tools.pc_health import get_pc_health_report

        return get_pc_health_report()
    
    return None