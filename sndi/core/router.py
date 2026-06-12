from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RouteKind(Enum):
    SYSTEM = "system"
    SCAN = "scan"
    ASYNC = "async"


@dataclass
class RouteResult:
    kind: RouteKind
    reply: str = ""
    status: str = "thinking"
    metadata: dict = field(default_factory=dict)


def route_sync(user_text: str, system_mgr) -> RouteResult | None:
    """
    Fast sync routing only.

    No LLM calls here.
    No web calls here.
    No GUI imports here.

    This is a v1.8 skeleton for the future AI Action Router.
    """
    from sndi.core.intents import is_screen_scan_intent

    if is_screen_scan_intent(user_text):
        return RouteResult(kind=RouteKind.SCAN, status="scanning")

    handled, reply = system_mgr.dispatch(user_text)
    if handled:
        return RouteResult(kind=RouteKind.SYSTEM, reply=reply, status="online")

    return None