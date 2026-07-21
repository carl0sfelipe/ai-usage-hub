from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from collectors.base import ProviderSnapshot


class SnapshotCache:
    def __init__(self, db_path: str = "~/.ai-usage-hub/cache.db", ttl_seconds: int = 300):
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    provider_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    collected_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider_id TEXT NOT NULL,
                    window_type TEXT NOT NULL,
                    usage_percent REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                )
            """)

    def get(self, provider_id: str) -> ProviderSnapshot | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT data, collected_at FROM snapshots WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
        if not row:
            return None
        collected_at = datetime.fromisoformat(row[1])
        if datetime.now() - collected_at > timedelta(seconds=self._ttl):
            return None
        data = json.loads(row[0])
        return self._dict_to_snapshot(data)

    def get_stale(self, provider_id: str) -> ProviderSnapshot | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT data, collected_at FROM snapshots WHERE provider_id = ?",
                (provider_id,),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return self._dict_to_snapshot(data)

    def put(self, snapshot: ProviderSnapshot):
        data = json.dumps(snapshot.to_dict())
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO snapshots (provider_id, data, collected_at) VALUES (?, ?, ?)",
                (snapshot.provider_id, data, snapshot.collected_at.isoformat()),
            )
            for limit in snapshot.limits:
                conn.execute(
                    "INSERT INTO usage_history (provider_id, window_type, usage_percent, recorded_at) VALUES (?, ?, ?, ?)",
                    (snapshot.provider_id, limit.window_type, limit.usage_percent, datetime.now().isoformat()),
                )

    def get_all(self) -> list[ProviderSnapshot]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT data FROM snapshots").fetchall()
        return [self._dict_to_snapshot(json.loads(r[0])) for r in rows]

    def get_burn_rate(self, provider_id: str, window_minutes: int = 15) -> float | None:
        cutoff = (datetime.now() - timedelta(minutes=window_minutes)).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT usage_percent, recorded_at FROM usage_history WHERE provider_id = ? AND recorded_at > ? ORDER BY recorded_at",
                (provider_id, cutoff),
            ).fetchall()
        if len(rows) < 2:
            return None
        first_pct, first_time = rows[0]
        last_pct, last_time = rows[-1]
        delta_pct = last_pct - first_pct
        t0 = datetime.fromisoformat(first_time)
        t1 = datetime.fromisoformat(last_time)
        delta_min = (t1 - t0).total_seconds() / 60
        if delta_min <= 0:
            return None
        return delta_pct / delta_min

    def _dict_to_snapshot(self, data: dict) -> ProviderSnapshot:
        from collectors.base import LimitWindow
        limits = []
        for l in data.get("limits", []):
            reset_at = None
            if l.get("reset_at"):
                try:
                    reset_at = datetime.fromisoformat(l["reset_at"])
                except (ValueError, TypeError):
                    pass
            limits.append(LimitWindow(
                window_type=l["window_type"],
                usage_value=l["usage_value"],
                limit_value=l["limit_value"],
                remaining_value=l["remaining_value"],
                usage_percent=l["usage_percent"],
                reset_at=reset_at,
                unit=l.get("unit", "percent"),
            ))
        collected_at = datetime.now()
        if data.get("collected_at"):
            try:
                collected_at = datetime.fromisoformat(data["collected_at"])
            except (ValueError, TypeError):
                pass
        return ProviderSnapshot(
            provider_id=data["provider_id"],
            plan_name=data.get("plan_name", ""),
            collected_at=collected_at,
            status=data.get("status", "active"),
            limits=limits,
            spend_today_usd=data.get("spend_today_usd"),
            error=data.get("error"),
        )
