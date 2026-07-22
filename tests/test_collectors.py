from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest


class MockResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


@pytest.mark.asyncio
class TestOpenCodeGoCollector:
    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_returns_three_windows(self, mock_vault, mock_opencode_response):
        from collectors.opencode_go import OpenCodeGoCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, mock_opencode_response)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = OpenCodeGoCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot is not None
            assert snapshot.status == "active"
            assert len(snapshot.limits) == 3

            window_types = {w.window_type for w in snapshot.limits}
            assert "rolling_5h" in window_types
            assert "weekly" in window_types
            assert "monthly" in window_types

    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_sets_correct_usage_percent(self, mock_vault, mock_opencode_response):
        from collectors.opencode_go import OpenCodeGoCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, mock_opencode_response)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = OpenCodeGoCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            rolling = [w for w in snapshot.limits if w.window_type == "rolling_5h"][0]
            assert rolling.usage_value == 1.5
            assert rolling.limit_value == 5.0
            assert rolling.usage_percent == 30.0
            assert rolling.unit == "usd"

    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_handles_api_error(self, mock_vault):
        from collectors.opencode_go import OpenCodeGoCollector

        async def mock_get(self, url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = OpenCodeGoCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "Connection refused" in snapshot.error

    async def test_fetch_no_key_returns_error(self):
        from collectors.opencode_go import OpenCodeGoCollector

        with patch("collectors.opencode_go.get_vault_credential", return_value=""):
            collector = OpenCodeGoCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "API_KEY not found" in snapshot.error

    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_sets_reset_at_from_resets_in_seconds(self, mock_vault):
        from collectors.opencode_go import OpenCodeGoCollector

        resp = {
            "five_hour": {"used": 0, "limit": 5, "resets_in_seconds": 3600},
        }

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, resp)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = OpenCodeGoCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert len(snapshot.limits) == 1
            assert snapshot.limits[0].reset_at is not None


@pytest.mark.asyncio
class TestGLMProCollector:
    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_returns_limits(self, mock_vault, mock_glm_response):
        from collectors.glm_pro import GLMProCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, mock_glm_response)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = GLMProCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot is not None
            assert snapshot.status == "active"
            assert len(snapshot.limits) > 0
            assert "pro" in snapshot.plan_name

    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_token_limits_have_correct_windows(self, mock_vault, mock_glm_response):
        from collectors.glm_pro import GLMProCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, mock_glm_response)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = GLMProCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            windows = {w.window_type for w in snapshot.limits}
            assert "rolling_5h" in windows  # unit_code <= 3
            assert "weekly" in windows  # unit_code > 3
            assert "monthly" in windows  # TIME_LIMIT

    @patch("collectors.vault.get_vault_credential", return_value="fake_key")
    async def test_fetch_handles_api_error(self, mock_vault):
        from collectors.glm_pro import GLMProCollector

        async def mock_get(self, url, **kwargs):
            raise httpx.HTTPStatusError("500 error", request=None, response=MockResponse(500, {}))

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = GLMProCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"

    async def test_fetch_no_key_returns_error(self):
        from collectors.glm_pro import GLMProCollector

        with patch("collectors.glm_pro.get_vault_credential", return_value=""):
            collector = GLMProCollector({"base_url": "https://fake.url"})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "API_KEY" in snapshot.error


@pytest.mark.asyncio
class TestClaudeProCollector:
    async def test_fetch_no_token_returns_error(self):
        from collectors.claude_pro import ClaudeProCollector

        with patch("collectors.claude_pro.get_vault_credential", return_value=""):
            collector = ClaudeProCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "TOKEN not found" in snapshot.error

    @patch("collectors.vault.get_vault_credential", return_value="fake_token")
    async def test_fetch_returns_snapshot(self, mock_vault):
        from collectors.claude_pro import ClaudeProCollector

        resp = {
            "limits": [
                {"window": "5h", "used": 10, "limit": 100, "reset_at": "2026-07-22T18:00:00Z", "unit": "percent"},
            ],
        }

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, resp)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = ClaudeProCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "active"
            assert len(snapshot.limits) == 1
            assert snapshot.limits[0].usage_percent == 10.0

    @patch("collectors.vault.get_vault_credential", return_value="fake_token")
    async def test_fetch_handles_rate_limit(self, mock_vault):
        from collectors.claude_pro import ClaudeProCollector

        async def mock_get(self, url, **kwargs):
            return MockResponse(429, {})

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = ClaudeProCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "error"
            assert "Rate limited" in snapshot.error

    @patch("collectors.vault.get_vault_credential", return_value="fake_token")
    async def test_fetch_fallback_usage_percent(self, mock_vault):
        from collectors.claude_pro import ClaudeProCollector

        resp = {"usage_percent": 75.0, "reset_at": "2026-07-22T18:00:00Z"}

        async def mock_get(self, url, **kwargs):
            return MockResponse(200, resp)

        with patch.object(httpx.AsyncClient, "get", mock_get):
            collector = ClaudeProCollector({})
            snapshot = await collector.fetch()
            assert snapshot.status == "active"
            assert len(snapshot.limits) == 1
            assert snapshot.limits[0].usage_percent == 75.0
