from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from collectors.base import LimitWindow, ProviderSnapshot


class LocalTokenTracker:
    def __init__(self, config: dict):
        self.provider_id = config.get("provider_id", "qwen_token_plan")
        self._plan_name = config.get("plan_name", "Local Token Plan")
        self._db_path = Path(config.get("db_path", "~/.local/share/opencode/opencode.db")).expanduser()
        self._model_ids = config.get("model_ids", [])
        self._limits_path = Path(__file__).parent.parent / "limits.json"

    def _load_limits(self) -> dict:
        if self._limits_path.exists():
            data = json.loads(self._limits_path.read_text())
            return data.get(self.provider_id, {})
        return {}

    def _query_tokens(self, since_ms: int) -> int:
        if not self._db_path.exists():
            return 0
        placeholders = ",".join("?" for _ in self._model_ids)
        query = f"""
            SELECT COALESCE(SUM(tokens_input + tokens_output), 0)
            FROM session
            WHERE time_created > ?
            AND json_extract(model, '$.id') IN ({placeholders})
        """
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            result = conn.execute(query, [since_ms, *self._model_ids]).fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception:
            return 0

    def _oldest_in_window(self, since_ms: int) -> int | None:
        if not self._db_path.exists():
            return None
        placeholders = ",".join("?" for _ in self._model_ids)
        query = f"""
            SELECT MIN(time_created)
            FROM session
            WHERE time_created > ?
            AND json_extract(model, '$.id') IN ({placeholders})
        """
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            result = conn.execute(query, [since_ms, *self._model_ids]).fetchone()
            conn.close()
            return result[0] if result and result[0] else None
        except Exception:
            return None

    @staticmethod
    def _next_monday() -> datetime:
        now = datetime.now()
        days_ahead = (7 - now.weekday()) % 7
        if days_ahead == 0 and now.hour > 0:
            days_ahead = 7
        return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _next_month_first() -> datetime:
        now = datetime.now()
        if now.month == 12:
            return datetime(now.year + 1, 1, 1)
        return datetime(now.year, now.month + 1, 1)

    async def fetch(self) -> ProviderSnapshot | None:
        limits_cfg = self._load_limits()
        now = datetime.now()
        now_ms = int(now.timestamp() * 1000)

        windows = []

        five_h_ago_ms = now_ms - 5 * 3600 * 1000
        tokens_5h = self._query_tokens(five_h_ago_ms)
        limit_5h = limits_cfg.get("rolling_5h", {}).get("limit_tokens")
        oldest_5h = self._oldest_in_window(five_h_ago_ms)
        reset_5h = None
        if oldest_5h:
            reset_5h = datetime.fromtimestamp(oldest_5h / 1000) + timedelta(hours=5)
        pct_5h = (tokens_5h / limit_5h * 100) if limit_5h else 0.0
        windows.append(LimitWindow(
            window_type="rolling_5h",
            usage_value=float(tokens_5h),
            limit_value=float(limit_5h) if limit_5h else 0.0,
            remaining_value=float(limit_5h - tokens_5h) if limit_5h else 0.0,
            usage_percent=pct_5h,
            reset_at=reset_5h,
            unit="tokens",
        ))

        monday = self._next_monday()
        week_start = monday - timedelta(days=7)
        week_start_ms = int(week_start.timestamp() * 1000)
        tokens_week = self._query_tokens(week_start_ms)
        limit_week = limits_cfg.get("weekly", {}).get("limit_tokens")
        pct_week = (tokens_week / limit_week * 100) if limit_week else 0.0
        windows.append(LimitWindow(
            window_type="weekly",
            usage_value=float(tokens_week),
            limit_value=float(limit_week) if limit_week else 0.0,
            remaining_value=float(limit_week - tokens_week) if limit_week else 0.0,
            usage_percent=pct_week,
            reset_at=monday,
            unit="tokens",
        ))

        month_first = self._next_month_first()
        if now.month == 1:
            current_month_start = datetime(now.year - 1, 12, 1)
        else:
            current_month_start = datetime(now.year, now.month - 1, 1) if now.month > 1 else datetime(now.year, 1, 1)
        current_month_start = datetime(now.year, now.month, 1)
        month_start_ms = int(current_month_start.timestamp() * 1000)
        tokens_month = self._query_tokens(month_start_ms)
        limit_month = limits_cfg.get("monthly", {}).get("limit_tokens")
        pct_month = (tokens_month / limit_month * 100) if limit_month else 0.0
        windows.append(LimitWindow(
            window_type="monthly",
            usage_value=float(tokens_month),
            limit_value=float(limit_month) if limit_month else 0.0,
            remaining_value=float(limit_month - tokens_month) if limit_month else 0.0,
            usage_percent=pct_month,
            reset_at=self._next_month_first(),
            unit="tokens",
        ))

        return ProviderSnapshot(
            provider_id=self.provider_id,
            plan_name=self._plan_name,
            status="active",
            limits=windows,
        )

    async def health_check(self) -> bool:
        return self._db_path.exists()
