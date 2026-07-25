from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest


class MockResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json = json_data
        self.text = str(json_data)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


MOCK_KEY_RESPONSE = {
    "data": {
        "label": "sk-or-v1-fake",
        "is_management_key": False,
        "is_provisioning_key": False,
        "limit": 32,
        "limit_reset": None,
        "limit_remaining": 22.6199,
        "usage": 9.3800,
        "usage_daily": 0.418,
        "usage_weekly": 9.38,
        "usage_monthly": 9.38,
        "is_free_tier": False,
        "expires_at": None,
    }
}


@pytest.mark.asyncio
class TestOpenRouterCollector:
    async def test_fetch_returns_key_window(self):
        from collectors.openrouter import OpenRouterCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, MOCK_KEY_RESPONSE)

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot is not None
            assert snapshot.status == "active"
            assert len(snapshot.limits) == 1
            window = snapshot.limits[0]
            assert window.window_type == "key_total"
            assert window.usage_value == 9.38
            assert window.limit_value == 32.0
            assert round(window.usage_percent, 1) == 29.3
            assert window.unit == "usd"

    async def test_fetch_marks_exhausted_when_remaining_zero(self):
        from collectors.openrouter import OpenRouterCollector

        resp = {
            "data": {
                "limit": 32,
                "limit_remaining": 0,
                "usage": 32,
            }
        }

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, resp)

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "exhausted"

    async def test_fetch_handles_unlimited_key(self):
        from collectors.openrouter import OpenRouterCollector

        resp = {"data": {"limit": None, "usage": 5.0}}

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, resp)

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "active"
            assert snapshot.limits == []

    async def test_fetch_handles_api_error(self):
        from collectors.openrouter import OpenRouterCollector

        async def mock_get(self, url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "Connection refused" in snapshot.error

    async def test_fetch_handles_unexpected_shape(self):
        from collectors.openrouter import OpenRouterCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, {"unexpected": True})

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "Unexpected /key response" in snapshot.error

    async def test_fetch_no_key_returns_error(self):
        from collectors.openrouter import OpenRouterCollector

        with patch("collectors.openrouter._read_openrouter_key", return_value=""):
            collector = OpenRouterCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "key not found" in snapshot.error

    async def test_health_check_true_on_200(self):
        from collectors.openrouter import OpenRouterCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, MOCK_KEY_RESPONSE)

        with (
            patch("collectors.openrouter._read_openrouter_key", return_value="fake_key"),
            patch.object(httpx.AsyncClient, "get", mock_get),
        ):
            collector = OpenRouterCollector({})
            assert await collector.health_check() is True

    async def test_health_check_false_without_key(self):
        from collectors.openrouter import OpenRouterCollector

        with patch("collectors.openrouter._read_openrouter_key", return_value=""):
            collector = OpenRouterCollector({})
            assert await collector.health_check() is False
