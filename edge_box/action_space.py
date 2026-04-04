from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SUPPORTED_ACTIONS = {"CLICK", "SWIPE", "TYPE", "WAIT"}


@dataclass
class Action:
    type: str
    params: dict[str, Any]

    def normalized(self) -> "Action":
        t = (self.type or "").upper().strip()
        return Action(type=t, params=self.params or {})

    def validate(self) -> None:
        t = (self.type or "").upper().strip()
        if t not in SUPPORTED_ACTIONS:
            raise ValueError(f"unsupported action type: {self.type}")
        if not isinstance(self.params, dict):
            raise ValueError("params must be dict")


def parse_actions(payload: dict[str, Any]) -> list[Action]:
    raw = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return []

    out: list[Action] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        act = Action(type=str(item.get("type", "")).upper(), params=item.get("params") or {})
        act.validate()
        out.append(act)
    return out
