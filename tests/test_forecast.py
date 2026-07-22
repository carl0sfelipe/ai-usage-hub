from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from collectors.base import LimitWindow, ProviderSnapshot
from server.forecast import Forecaster, Forecast, forecast_to_dict


@pytest.fixture
def forecaster_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    _init_db(db_path)
    yield db_path
    Path(db_path).unlink(missing_ok=True)


def _init_db(db_path: str):
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                window_type TEXT NOT NULL,
                usage_percent REAL NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """)


def _insert_history(db_path: str, provider_id: str, window_type: str, pct: float, minutes_ago: int):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO usage_history (provider_id, window_type, usage_percent, recorded_at) VALUES (?, ?, ?, ?)",
            (provider_id, window_type, pct, ts),
        )


def _make_snapshot(limits: list[LimitWindow]) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="test_provider",
        plan_name="Test",
        status="active",
        limits=limits,
    )


class TestForecast:
    def test_to_dict(self):
        f = Forecast(
            provider_id="p1",
            window_type="rolling_5h",
            burn_rate_per_min=0.5,
            minutes_to_exhaustion=120,
            will_exhaust_before_reset=True,
        )
        d = forecast_to_dict(f)
        assert d["provider_id"] == "p1"
        assert d["window_type"] == "rolling_5h"
        assert d["burn_rate_per_min"] == 0.5
        assert d["minutes_to_exhaustion"] == 120
        assert d["will_exhaust_before_reset"] is True


class TestForecaster:
    def test_forecast_no_history_returns_zero_burn_rate(self, forecaster_db: str):
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 50, 100, 50, 50.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].burn_rate_per_min == 0.0
        assert forecasts[0].minutes_to_exhaustion is None
        assert forecasts[0].will_exhaust_before_reset is False

    def test_forecast_stable_history_zero_burn(self, forecaster_db: str):
        for mins in [14, 10, 5]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", 50.0, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 50, 100, 50, 50.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].burn_rate_per_min == 0.0
        assert forecasts[0].minutes_to_exhaustion is None

    def test_forecast_rising_history(self, forecaster_db: str):
        for mins, pct in [(14, 20.0), (10, 30.0), (5, 40.0)]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 55, 100, 45, 55.0, reset_at=datetime.now() + timedelta(hours=5)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        f = forecasts[0]
        assert f.burn_rate_per_min > 0
        assert f.minutes_to_exhaustion is not None
        assert f.minutes_to_exhaustion > 0
        assert f.will_exhaust_before_reset is True

    def test_forecast_exhausted_returns_zero_exhaustion(self, forecaster_db: str):
        for mins in [14, 10, 5]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", 100.0, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 100, 100, 0, 100.0, reset_at=datetime.now() + timedelta(hours=1)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].minutes_to_exhaustion == 0

    def test_forecast_will_exhaust_before_reset_false_when_far(self, forecaster_db: str):
        for mins, pct in [(14, 20.0), (10, 22.0), (5, 24.0)]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 30, 100, 70, 30.0, reset_at=datetime.now() + timedelta(minutes=10)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].will_exhaust_before_reset is False

    def test_forecast_minutes_to_exhaustion_none_when_burn_rate_negative(self, forecaster_db: str):
        for mins, pct in [(14, 50.0), (10, 40.0), (5, 30.0)]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 25, 100, 75, 25.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].burn_rate_per_min < 0
        assert forecasts[0].minutes_to_exhaustion is None

    def test_forecast_multiple_windows(self, forecaster_db: str):
        for mins, pct in [(14, 10.0), (10, 20.0), (5, 30.0)]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", pct, mins)
        for mins, pct in [(14, 40.0), (10, 50.0), (5, 60.0)]:
            _insert_history(forecaster_db, "test_provider", "weekly", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 40, 100, 60, 40.0, reset_at=datetime.now() + timedelta(hours=3)),
            LimitWindow("weekly", 70, 200, 130, 35.0, reset_at=datetime.now() + timedelta(days=3)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 2
        assert forecasts[0].window_type == "rolling_5h"
        assert forecasts[1].window_type == "weekly"

    def test_forecast_all_skips_error_snapshots(self, forecaster_db: str):
        fc = Forecaster(db_path=forecaster_db)
        error_snap = ProviderSnapshot(
            provider_id="broken",
            plan_name="Broken",
            status="error",
            error="API down",
        )
        forecasts = fc.forecast_all([error_snap])
        assert forecasts == []

    def test_forecast_no_reset_at_will_exhaust_false(self, forecaster_db: str):
        for mins, pct in [(14, 20.0), (10, 40.0), (5, 60.0)]:
            _insert_history(forecaster_db, "test_provider", "rolling_5h", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 80, 100, 20, 80.0, reset_at=None),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].will_exhaust_before_reset is False
        assert forecasts[0].minutes_to_exhaustion is not None

    def test_forecast_single_data_point_returns_zero_burn(self, forecaster_db: str):
        _insert_history(forecaster_db, "test_provider", "rolling_5h", 50.0, 5)
        fc = Forecaster(db_path=forecaster_db)
        snap = _make_snapshot([
            LimitWindow("rolling_5h", 55, 100, 45, 55.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        forecasts = fc.forecast(snap)
        assert len(forecasts) == 1
        assert forecasts[0].burn_rate_per_min == 0.0

    def test_forecast_all_combines_multiple_providers(self, forecaster_db: str):
        for mins, pct in [(14, 10.0), (10, 20.0), (5, 30.0)]:
            _insert_history(forecaster_db, "p1", "rolling_5h", pct, mins)
        for mins, pct in [(14, 5.0), (10, 10.0), (5, 15.0)]:
            _insert_history(forecaster_db, "p2", "rolling_5h", pct, mins)
        fc = Forecaster(db_path=forecaster_db)
        snap1 = _make_snapshot([
            LimitWindow("rolling_5h", 40, 100, 60, 40.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        snap1.provider_id = "p1"
        snap2 = _make_snapshot([
            LimitWindow("rolling_5h", 20, 100, 80, 20.0, reset_at=datetime.now() + timedelta(hours=3)),
        ])
        snap2.provider_id = "p2"
        forecasts = fc.forecast_all([snap1, snap2])
        assert len(forecasts) == 2
