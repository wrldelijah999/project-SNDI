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
            "ревʼю коду",
            "рев'ю коду",
            "code review",
            "що не так з кодом",
            "проаналізуй код",
        )
    ):
        return ActionPlan(
            action="code_review",
            query=user_text,
            confidence=0.86,
            requires_confirmation=False,
            reason="user asks for code review",
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

    if looks_like_system_request(user_text):
        return ActionPlan(
            action="system_action",
            query=user_text,
            confidence=0.82,
            requires_confirmation=False,
            reason="message looks like a local system action",
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

    For Stage 1 this is intentionally empty.
    Later stages will add decision log, git summary, PC health, daily brief.
    """
    return None