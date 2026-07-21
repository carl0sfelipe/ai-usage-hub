from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class LimitWindow:
    window_type: str
    usage_value: float
    limit_value: float
    remaining_value: float
    usage_percent: float
    reset_at: datetime | None = None
    unit: str = "percent"

    def to_dict(self) -> dict:
        return {
            "window_type": self.window_type,
            "usage_value": self.usage_value,
            "limit_value": self.limit_value,
            "remaining_value": self.remaining_value,
            "usage_percent": round(self.usage_percent, 1),
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "unit": self.unit,
        }


@dataclass
class ProviderSnapshot:
    provider_id: str
    plan_name: str
    collected_at: datetime = field(default_factory=datetime.now)
    status: str = "active"
    limits: list[LimitWindow] = field(default_factory=list)
    spend_today_usd: float | None = None
    error: str | None = None

    @property
    def most_restrictive(self) -> LimitWindow | None:
        active = [l for l in self.limits if l.remaining_value > 0]
        if not active:
            return self.limits[0] if self.limits else None
        return min(active, key=lambda l: l.remaining_value)

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "plan_name": self.plan_name,
            "collected_at": self.collected_at.isoformat(),
            "status": self.status,
            "limits": [l.to_dict() for l in self.limits],
            "spend_today_usd": self.spend_today_usd,
            "error": self.error,
            "most_restrictive": self.most_restrictive.to_dict() if self.most_restrictive else None,
        }


@runtime_checkable
class BaseCollector(Protocol):
    provider_id: str

    async def fetch(self) -> ProviderSnapshot | None: ...
    async def health_check(self) -> bool: ...
