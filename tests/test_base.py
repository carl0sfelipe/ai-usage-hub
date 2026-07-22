from __future__ import annotations

from datetime import datetime

from collectors.base import LimitWindow, ProviderSnapshot


class TestLimitWindow:
    def test_to_dict_returns_keys(self):
        w = LimitWindow(
            window_type="rolling_5h",
            usage_value=25.0,
            limit_value=100.0,
            remaining_value=75.0,
            usage_percent=25.0,
            reset_at=datetime(2026, 7, 22, 15, 0, 0),
            unit="percent",
        )
        d = w.to_dict()
        assert d["window_type"] == "rolling_5h"
        assert d["usage_value"] == 25.0
        assert d["limit_value"] == 100.0
        assert d["remaining_value"] == 75.0
        assert d["usage_percent"] == 25.0
        assert d["reset_at"] == "2026-07-22T15:00:00"
        assert d["unit"] == "percent"

    def test_to_dict_rounds_usage_percent(self):
        w = LimitWindow(
            window_type="rolling_5h",
            usage_value=1,
            limit_value=3,
            remaining_value=2,
            usage_percent=33.333333,
            unit="percent",
        )
        assert w.to_dict()["usage_percent"] == 33.3

    def test_to_dict_reset_at_none(self):
        w = LimitWindow(
            window_type="rolling_5h",
            usage_value=0,
            limit_value=1,
            remaining_value=1,
            usage_percent=0.0,
        )
        assert w.to_dict()["reset_at"] is None


class TestProviderSnapshot:
    def test_most_restrictive_returns_smallest_remaining(self):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            limits=[
                LimitWindow("a", 50, 100, 50, 50.0),
                LimitWindow("b", 80, 100, 20, 80.0),
                LimitWindow("c", 10, 100, 90, 10.0),
            ],
        )
        mr = snap.most_restrictive
        assert mr is not None
        assert mr.window_type == "b"

    def test_most_restrictive_skips_exhausted_limits(self):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            limits=[
                LimitWindow("a", 100, 100, 0, 100.0),
                LimitWindow("b", 50, 100, 50, 50.0),
            ],
        )
        mr = snap.most_restrictive
        assert mr is not None
        assert mr.window_type == "b"

    def test_most_restrictive_all_exhausted_returns_first(self):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            limits=[
                LimitWindow("a", 100, 100, 0, 100.0),
                LimitWindow("b", 100, 100, 0, 100.0),
            ],
        )
        mr = snap.most_restrictive
        assert mr is not None
        assert mr.window_type == "a"

    def test_most_restrictive_no_limits(self):
        snap = ProviderSnapshot(provider_id="p1", plan_name="P1", limits=[])
        assert snap.most_restrictive is None

    def test_to_dict_returns_all_keys(self):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
            spend_today_usd=1.23,
            error=None,
        )
        d = snap.to_dict()
        assert d["provider_id"] == "p1"
        assert d["plan_name"] == "P1"
        assert d["status"] == "active"
        assert "collected_at" in d
        assert len(d["limits"]) == 1
        assert d["spend_today_usd"] == 1.23
        assert d["error"] is None
        assert d["most_restrictive"] is not None

    def test_to_dict_with_error(self):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="error",
            error="Something broke",
        )
        d = snap.to_dict()
        assert d["status"] == "error"
        assert d["error"] == "Something broke"
        assert d["most_restrictive"] is None
