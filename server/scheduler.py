from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from collectors.base import ProviderSnapshot


@dataclass
class Recommendation:
    action: str  # "use" | "wait" | "delegate" | "consolidate"
    provider: str
    message: str
    target_provider: str | None = None
    minutes_to_reset: int | None = None


class Scheduler:
    def __init__(self, config: dict):
        sched = config.get("scheduler", {})
        self._wait_threshold = sched.get("wait_threshold_percent", 85)
        self._wait_max_min = sched.get("wait_max_minutes", 30)
        self._delegate_threshold = sched.get("delegate_threshold_percent", 85)
        self._consolidate_threshold = sched.get("consolidate_threshold_percent", 70)

    def recommend(self, snapshots: list[ProviderSnapshot], priority_order: list[str]) -> Recommendation:
        active = {s.provider_id: s for s in snapshots if s.status == "active" and s.limits}
        if not active:
            return Recommendation(
                action="use",
                provider=priority_order[0] if priority_order else "unknown",
                message="No active providers with data. Use default.",
            )

        primary_id = next((p for p in priority_order if p in active), None)
        if not primary_id:
            primary_id = list(active.keys())[0]
        primary = active[primary_id]

        restrictive = primary.most_restrictive
        if not restrictive:
            return Recommendation(action="use", provider=primary_id, message=f"{primary_id} has no active limits.")

        usage_pct = restrictive.usage_percent
        minutes_to_reset = self._minutes_to_reset(restrictive.reset_at)

        all_above_consolidate = all(
            s.most_restrictive and s.most_restrictive.usage_percent >= self._consolidate_threshold
            for s in active.values()
        )
        if all_above_consolidate and len(active) > 1:
            return Recommendation(
                action="consolidate",
                provider=primary_id,
                message=f"All providers above {self._consolidate_threshold}%. Consolidate context to memory and pause non-critical work.",
                minutes_to_reset=minutes_to_reset,
            )

        if usage_pct >= self._wait_threshold:
            if minutes_to_reset is not None and minutes_to_reset <= self._wait_max_min:
                return Recommendation(
                    action="wait",
                    provider=primary_id,
                    message=f"{primary_id} at {usage_pct:.0f}%. Reset in {minutes_to_reset}min. Wait before new prompts.",
                    minutes_to_reset=minutes_to_reset,
                )
            else:
                alt = self._find_alternative(active, priority_order, primary_id)
                if alt:
                    return Recommendation(
                        action="delegate",
                        provider=primary_id,
                        target_provider=alt,
                        message=f"{primary_id} at {usage_pct:.0f}%, reset in {minutes_to_reset or '?'}min. Delegate to {alt}.",
                        minutes_to_reset=minutes_to_reset,
                    )
                return Recommendation(
                    action="wait",
                    provider=primary_id,
                    message=f"{primary_id} at {usage_pct:.0f}%. No alternative available. Wait for reset.",
                    minutes_to_reset=minutes_to_reset,
                )

        return Recommendation(
            action="use",
            provider=primary_id,
            message=f"{primary_id} at {usage_pct:.0f}%. Safe to use.",
            minutes_to_reset=minutes_to_reset,
        )

    def should_consolidate(self, snapshots: list[ProviderSnapshot], session_minutes: int) -> dict:
        active = [s for s in snapshots if s.status == "active" and s.limits]
        max_usage = 0.0
        for s in active:
            r = s.most_restrictive
            if r:
                max_usage = max(max_usage, r.usage_percent)

        should = False
        reason = ""
        if max_usage >= self._consolidate_threshold:
            should = True
            reason = f"Provider usage at {max_usage:.0f}% (threshold: {self._consolidate_threshold}%)"
        elif session_minutes > 120:
            should = True
            reason = f"Session running for {session_minutes}min (>2h). Consolidate before context grows."

        return {
            "should_consolidate": should,
            "reason": reason,
            "max_usage_percent": round(max_usage, 1),
            "session_minutes": session_minutes,
        }

    def _find_alternative(self, active: dict[str, ProviderSnapshot], priority: list[str], exclude: str) -> str | None:
        for pid in priority:
            if pid == exclude or pid not in active:
                continue
            snap = active[pid]
            r = snap.most_restrictive
            if r and r.usage_percent < self._delegate_threshold:
                return pid
        for pid, snap in active.items():
            if pid == exclude:
                continue
            r = snap.most_restrictive
            if r and r.usage_percent < self._delegate_threshold:
                return pid
        return None

    def _minutes_to_reset(self, reset_at: datetime | None) -> int | None:
        if not reset_at:
            return None
        delta = (reset_at - datetime.now()).total_seconds() / 60
        return max(0, int(delta))
