from __future__ import annotations

import re
from dataclasses import dataclass


class SecurityException(Exception):
    """高危注入请求异常。"""


@dataclass
class InjectionFilter:
    score_threshold: int = 3

    _PATTERNS = [
        re.compile(r"\bignore\b", re.I),
        re.compile(r"system\s*prompt", re.I),
        re.compile(r"you\s+are\s+now", re.I),
        re.compile(r"developer\s+mode", re.I),
        re.compile(r"jailbreak", re.I),
        re.compile(r"do\s+anything\s+now|\bdan\b", re.I),
        re.compile(r"越狱|忽略(以上|之前|所有)?指令|系统提示词|你现在是", re.I),
    ]

    def evaluate(self, item_name: str, demand_text: str) -> tuple[bool, int, list[str]]:
        text = f"{item_name or ''}\n{demand_text or ''}".strip()
        if not text:
            return False, 0, []

        score = 0
        hits: list[str] = []
        for p in self._PATTERNS:
            if p.search(text):
                score += 2
                hits.append(p.pattern)

        lowered = text.lower()
        if any(k in lowered for k in ["ignore", "prompt", "system", "role"]):
            score += 1

        return score >= self.score_threshold, score, hits

    def check(self, item_name: str, demand_text: str) -> None:
        risky, score, hits = self.evaluate(item_name, demand_text)
        if risky:
            raise SecurityException(f"prompt_injection_blocked score={score} hits={hits}")
