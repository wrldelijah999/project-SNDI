from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid


CONFIRMATION_TEXTS = {
    "так",
    "так підтверджую",
    "підтверджую",
    "виконуй",
    "можна",
    "ок",
    "окей",
    "go",
    "confirm",
    "yes",
}

CANCEL_TEXTS = {
    "скасувати",
    "відміна",
    "відмінити",
    "не треба",
    "ні",
    "стоп",
    "cancel",
    "no",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _normalize_intent_text(text: str) -> str:
    normalized = (text or "").strip().lower()

    replacements = {
        ",": " ",
        ".": " ",
        "!": " ",
        "?": " ",
        "  ": " ",
    }

    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    while "  " in normalized:
        normalized = normalized.replace("  ", " ")

    return normalized.strip()


def is_confirmation_text(text: str) -> bool:
    """
    Conservative confirmation detector.

    Important:
    - confirmation must be explicit;
    - do not confirm long unrelated messages accidentally.
    """
    normalized = _normalize_intent_text(text)
    return normalized in CONFIRMATION_TEXTS


def is_cancel_text(text: str) -> bool:
    """
    Conservative cancel detector.
    """
    normalized = _normalize_intent_text(text)
    return normalized in CANCEL_TEXTS


@dataclass
class PendingAction:
    """
    Runtime pending action.

    v1.11 rule:
    A mutation action must be created as PendingAction first,
    then executed only after explicit confirmation.
    """

    id: str
    action: str
    target: str
    params: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    user_text: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    expires_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return utc_now() > expires
        except Exception:
            return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "params": self.params,
            "preview": self.preview,
            "risk_level": self.risk_level,
            "user_text": self.user_text,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }


class ConfirmationManager:
    """
    Manages one active pending action.

    Important design choice:
    - pending actions are runtime-only;
    - after app restart there is no pending action;
    - this avoids accidentally confirming an old dangerous action.
    """

    def __init__(self, default_ttl_seconds: int = 600):
        self.default_ttl_seconds = default_ttl_seconds
        self._pending_action: PendingAction | None = None

    def create_pending_action(
        self,
        action: str,
        target: str | Path,
        params: dict[str, Any] | None = None,
        preview: dict[str, Any] | None = None,
        risk_level: str = "medium",
        user_text: str = "",
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PendingAction:
        created = utc_now()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires = created + timedelta(seconds=ttl)

        pending_action = PendingAction(
            id=str(uuid.uuid4()),
            action=str(action),
            target=str(target),
            params=params or {},
            preview=preview or {},
            risk_level=risk_level,
            user_text=user_text or "",
            created_at=created.isoformat(),
            expires_at=expires.isoformat(),
            metadata=metadata or {},
        )

        self._pending_action = pending_action
        return pending_action

    def get_pending_action(self) -> PendingAction | None:
        if self._pending_action is None:
            return None

        if self._pending_action.is_expired():
            self._pending_action = None
            return None

        return self._pending_action

    def has_pending_action(self) -> bool:
        return self.get_pending_action() is not None

    def clear_pending_action(self) -> None:
        self._pending_action = None

    def confirm_pending_action(self) -> PendingAction | None:
        pending_action = self.get_pending_action()

        if pending_action is None:
            return None

        self._pending_action = None
        return pending_action

    def cancel_pending_action(self) -> PendingAction | None:
        pending_action = self.get_pending_action()
        self._pending_action = None
        return pending_action

    def get_pending_action_id(self) -> str | None:
        pending_action = self.get_pending_action()

        if pending_action is None:
            return None

        return pending_action.id


def format_pending_action_message(pending_action: PendingAction) -> str:
    """
    User-facing confirmation message.
    """
    preview = pending_action.preview or {}

    type_text = preview.get("type", "невідомо")
    size_text = preview.get("size_human") or preview.get("size") or "невідомо"
    mode_text = preview.get("mode", "preview + confirmation")
    warning = preview.get("warning")

    message = (
        "потрібне підтвердження.\n\n"
        f"ID: {pending_action.id}\n"
        f"Дія: {pending_action.action}\n"
        f"Ціль: {pending_action.target}\n"
        f"Тип: {type_text}\n"
        f"Розмір: {size_text}\n"
        f"Режим: {mode_text}\n"
        f"Ризик: {pending_action.risk_level}\n"
    )

    if warning:
        message += f"\nУвага: {warning}\n"

    message += (
        "\nНапиши “підтверджую”, щоб виконати, "
        "або “скасувати”, щоб відмінити."
    )

    return message


def format_no_pending_action_message() -> str:
    return "немає активної дії для підтвердження."


def format_pending_action_cancelled_message(pending_action: PendingAction | None) -> str:
    if pending_action is None:
        return "скасовано. активної дії вже не було."

    return (
        "скасовано. нічого не змінено.\n\n"
        f"Дія: {pending_action.action}\n"
        f"Ціль: {pending_action.target}"
    )


def format_pending_action_expired_message() -> str:
    return "час підтвердження минув. дію скасовано, нічого не змінено."