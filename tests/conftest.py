from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from collectors.base import LimitWindow, ProviderSnapshot


@pytest.fixture
def mock_snapshot() -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="test_provider",
        plan_name="Test Plan",
        status="active",
        limits=[
            LimitWindow(
                window_type="rolling_5h",
                usage_value=25.0,
                limit_value=100.0,
                remaining_value=75.0,
                usage_percent=25.0,
                reset_at=datetime.now() + timedelta(hours=3),
                unit="percent",
            ),
            LimitWindow(
                window_type="weekly",
                usage_value=50.0,
                limit_value=200.0,
                remaining_value=150.0,
                usage_percent=25.0,
                reset_at=datetime.now() + timedelta(days=3),
                unit="usd",
            ),
        ],
    )


@pytest.fixture
def mock_snapshot_high_usage() -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="test_provider",
        plan_name="Test Plan",
        status="active",
        limits=[
            LimitWindow(
                window_type="rolling_5h",
                usage_value=90.0,
                limit_value=100.0,
                remaining_value=10.0,
                usage_percent=90.0,
                reset_at=datetime.now() + timedelta(minutes=15),
                unit="percent",
            ),
        ],
    )


@pytest.fixture
def mock_snapshot_no_limits() -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="empty_provider",
        plan_name="Empty",
        status="active",
        limits=[],
    )


@pytest.fixture
def mock_opencode_response() -> dict:
    return {
        "five_hour": {"used": 1.5, "limit": 5.0, "reset_at": "2026-07-22T15:00:00Z", "unit": "usd"},
        "weekly": {"used": 3.0, "limit": 10.0, "reset_at": "2026-07-27T00:00:00Z", "unit": "usd"},
        "monthly": {"used": 5.0, "limit": 10.0, "reset_at": "2026-08-01T00:00:00Z", "unit": "usd"},
        "today_usd": 0.5,
    }


@pytest.fixture
def mock_glm_response() -> dict:
    return {
        "data": {
            "level": "pro",
            "limits": [
                {"type": "TOKENS_LIMIT", "unit": 1, "percentage": 45.0, "nextResetTime": 1721650000000},
                {"type": "TOKENS_LIMIT", "unit": 5, "percentage": 30.0, "nextResetTime": 1722254800000},
                {"type": "TIME_LIMIT", "usage": 100, "currentValue": 23, "remaining": 77},
            ],
        },
    }
