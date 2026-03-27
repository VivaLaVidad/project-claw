from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _norm_tags(v: Any) -> set[str]:
    if not v:
        return set()
    if isinstance(v, str):
        return {v.strip().lower()} if v.strip() else set()
    if isinstance(v, list):
        return {str(x).strip().lower() for x in v if str(x).strip()}
    return set()


@dataclass
class PreferenceWeights:
    tag_hit_unit: float = 4.0
    tag_hit_cap: float = 12.0
    avoid_hit_unit: float = 5.0
    avoid_hit_cap: float = 15.0
    eta_base_minutes: float = 20.0
    eta_penalty_scale: float = 0.25
    budget_bonus_scale: float = 20.0
    budget_penalty_scale: float = 30.0
    budget_bonus_threshold_ratio: float = 0.85
    budget_penalty_cap: float = 20.0


@dataclass
class PreferenceDecision:
    final_score: float
    delta: float
    reasons: list[str]
    strategy: str


class PreferenceMatcher:
    """B/C 个性化偏好匹配引擎（可热更新权重 + A/B 策略）。"""

    def __init__(self):
        self._weights_by_strategy: dict[str, PreferenceWeights] = {
            "balanced": PreferenceWeights(),
            "aggressive": PreferenceWeights(tag_hit_unit=5.0, tag_hit_cap=15.0, avoid_hit_unit=6.0),
        }
        self._ab_rollout = {"balanced": 80, "aggressive": 20}

    def get_runtime(self) -> dict[str, Any]:
        return {
            "strategies": {k: v.__dict__ for k, v in self._weights_by_strategy.items()},
            "ab_rollout": self._ab_rollout,
        }

    def apply_runtime(self, runtime: dict[str, Any]) -> dict[str, Any]:
        runtime = runtime or {}
        strategies = runtime.get("strategies", {})
        for name, cfg in strategies.items():
            self.update_strategy_weights(str(name), dict(cfg or {}))
        rollout = runtime.get("ab_rollout", {})
        if isinstance(rollout, dict) and rollout:
            self.update_ab_rollout(rollout)
        return self.get_runtime()

    def update_strategy_weights(self, strategy: str, patch: dict[str, Any]) -> dict[str, Any]:
        if strategy not in self._weights_by_strategy:
            self._weights_by_strategy[strategy] = PreferenceWeights()
        w = self._weights_by_strategy[strategy]
        for k, v in (patch or {}).items():
            if hasattr(w, k):
                setattr(w, k, float(v))
        return w.__dict__

    def update_ab_rollout(self, rollout: dict[str, Any]) -> dict[str, int]:
        total = 0
        cleaned: dict[str, int] = {}
        for k, v in (rollout or {}).items():
            n = max(0, int(v))
            cleaned[str(k)] = n
            total += n
        if total <= 0:
            return self._ab_rollout
        self._ab_rollout = cleaned
        return self._ab_rollout

    def _choose_strategy(self, sticky_id: str) -> str:
        bucket = abs(hash(sticky_id or "default")) % 100
        acc = 0
        for strategy, ratio in self._ab_rollout.items():
            acc += ratio
            if bucket < acc:
                return strategy
        return next(iter(self._weights_by_strategy.keys()))

    def decide(
        self,
        base_match_score: float,
        client_profile: dict[str, Any],
        merchant_profile: dict[str, Any],
        offer: dict[str, Any],
        sticky_id: str = "",
    ) -> PreferenceDecision:
        strategy = self._choose_strategy(sticky_id or f"{offer.get('merchant_id','')}:{offer.get('final_price','')}")
        w = self._weights_by_strategy.get(strategy) or PreferenceWeights()

        score = float(base_match_score)
        reasons: list[str] = []

        client_like = _norm_tags(client_profile.get("preferred_tags"))
        client_dislike = _norm_tags(client_profile.get("avoid_tags"))
        merchant_tags = _norm_tags(merchant_profile.get("tags")) | _norm_tags(offer.get("offer_tags"))

        if client_like and merchant_tags:
            hit = len(client_like & merchant_tags)
            if hit > 0:
                boost = min(w.tag_hit_cap, hit * w.tag_hit_unit)
                score += boost
                reasons.append(f"偏好命中 +{boost:.1f}")

        if client_dislike and merchant_tags:
            bad = len(client_dislike & merchant_tags)
            if bad > 0:
                drop = min(w.avoid_hit_cap, bad * w.avoid_hit_unit)
                score -= drop
                reasons.append(f"避雷冲突 -{drop:.1f}")

        eta_pref = float(client_profile.get("eta_sensitivity", 0.5) or 0.5)
        eta = float(offer.get("eta_minutes", 0) or 0)
        if eta > 0:
            eta_penalty = max(0.0, (eta - w.eta_base_minutes) * eta_pref * w.eta_penalty_scale)
            if eta_penalty > 0:
                score -= eta_penalty
                reasons.append(f"时效惩罚 -{eta_penalty:.1f}")

        budget_pref = float(client_profile.get("budget_sensitivity", 0.5) or 0.5)
        max_price = float(client_profile.get("max_price", 0) or 0)
        final_price = float(offer.get("final_price", 0) or 0)
        if max_price > 0 and final_price > 0:
            ratio = final_price / max_price
            if ratio <= w.budget_bonus_threshold_ratio:
                bonus = (w.budget_bonus_threshold_ratio - ratio) * budget_pref * w.budget_bonus_scale
                score += bonus
                reasons.append(f"预算友好 +{bonus:.1f}")
            elif ratio > 1:
                penalty = min(w.budget_penalty_cap, (ratio - 1) * budget_pref * w.budget_penalty_scale)
                score -= penalty
                reasons.append(f"预算超限 -{penalty:.1f}")

        score = max(0.0, min(100.0, score))
        return PreferenceDecision(
            final_score=round(score, 2),
            delta=round(score - float(base_match_score), 2),
            reasons=reasons,
            strategy=strategy,
        )
