from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionPlan:
    """
    Unified routing result for SNDI v1.9.

    ActionRouter returns this object for every user message.
    GUI will later decide what old/new flow to start based on plan.action.
    """

    action: str
    target: str = ""
    query: str = ""
    confidence: float = 0.0
    requires_confirmation: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_confident(self, threshold: float = 0.55) -> bool:
        return self.confidence >= threshold

    def is_chat(self) -> bool:
        return self.action == "chat"

    def needs_confirmation(self) -> bool:
        return self.requires_confirmation