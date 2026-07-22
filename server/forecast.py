from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from collectors.base import LimitWindow, ProviderSnapshot


@dataclass
class Forecast:
    provider_id: str
    window_type: str
    burn_rate_per_min: float
    minutes_to_exhaustion: int | None
    will_exhaust_before_reset: bool


class Forecaster:
    def __init__(self, db_path: str, window_minutes: int = 15):
        self._db_path = Path(db_path).expanduser()
        self._window = window_minutes

    def forecast(self, snapshot: ProviderSnapshot) -> list[Forecast]:
        forecasts: list[Forecast] = []
        for limit in snapshot.limits:
            history = self._query_history(snapshot.provider_id, limit.window_type)
            burn_rate = self._calc_burn_rate(history)
            minutes_to_exhaustion = self._calc_exhaustion(limit, burn_rate)
            will_exhaust = self._will_exhaust_before_reset(minutes_to_exhaustion, limit)

            forecasts.append(Forecast(
                provider_id=snapshot.provider_id,
                window_type=limit.window_type,
                burn_rate_per_min=round(burn_rate, 4),
                minutes_to_exhaustion=minutes_to_exhaustion,
                will_exhaust_before_reset=will_exhaust,
            ))
        return forecasts

    def forecast_all(self, snapshots: list[ProviderSnapshot]) -> list[Forecast]:
        results: list[Forecast] = []
        for snap in snapshots:
            if snap.status == "active":
                results.extend(self.forecast(snap))
        return results

    def _query_history(self, provider_id: str, window_type: str) -> list[tuple[float, datetime]]:
        cutoff = (datetime.now() - timedelta(minutes=self._window)).isoformat()
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT usage_percent, recorded_at FROM usage_history "
                "WHERE provider_id = ? AND window_type = ? AND recorded_at > ? "
                "ORDER BY recorded_at ASC",
                (provider_id, window_type, cutoff),
            ).fetchall()
        return [(float(r[0]), datetime.fromisoformat(r[1])) for r in rows]

    def _calc_burn_rate(self, history: list[tuple[float, datetime]]) -> float:
        if len(history) < 2:
            return 0.0
        first_pct, first_time = history[0]
        last_pct, last_time = history[-1]
        delta_pct = last_pct - first_pct
        delta_min = (last_time - first_time).total_seconds() / 60
        if delta_min <= 0:
            return 0.0
        return delta_pct / delta_min

    def _calc_exhaustion(self, limit: LimitWindow, burn_rate: float) -> int | None:
        if limit.usage_percent >= 100:
            return 0
        if burn_rate <= 0:
            return None
        remaining = 100.0 - limit.usage_percent
        minutes = remaining / burn_rate
        return max(0, int(minutes))

    def _will_exhaust_before_reset(self, minutes_to_exhaustion: int | None, limit: LimitWindow) -> bool:
        if minutes_to_exhaustion is None or limit.reset_at is None:
            return False
        exhaust_at = datetime.now() + timedelta(minutes=minutes_to_exhaustion)
        return exhaust_at < limit.reset_at


def forecast_to_dict(f: Forecast) -> dict:
    return {
        "provider_id": f.provider_id,
        "window_type": f.window_type,
        "burn_rate_per_min": f.burn_rate_per_min,
        "minutes_to_exhaustion": f.minutes_to_exhaustion,
        "will_exhaust_before_reset": f.will_exhaust_before_reset,
    }
