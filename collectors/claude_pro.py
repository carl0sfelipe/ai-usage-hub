from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from collectors.base import LimitWindow, ProviderSnapshot


CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
OAUTH_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


def _read_credentials() -> dict | None:
    try:
        raw = CREDENTIALS_PATH.read_text()
        return json.loads(raw).get("claudeAiOauth")
    except Exception:
        return None


def _is_expired(expires_at_ms: int | None) -> bool:
    if expires_at_ms is None:
        return True
    return time.time() * 1000 >= expires_at_ms


class ClaudeProCollector:
    provider_id = "claude_pro"

    def __init__(self, config: dict):
        pass

    async def _get_valid_token(self) -> str | None:
        creds = _read_credentials()
        if not creds:
            return None
        access_token = creds.get("accessToken")
        expires_at = creds.get("expiresAt")
        if not access_token:
            return None
        if not _is_expired(expires_at):
            return access_token
        refresh_token = creds.get("refreshToken")
        if not refresh_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    OAUTH_TOKEN_URL,
                    json={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": CLIENT_ID,
                    },
                )
                if resp.status_code == 429:
                    return None
                resp.raise_for_status()
                data = resp.json()
                return data.get("access_token") or data.get("accessToken")
        except Exception:
            return None

    async def fetch(self) -> ProviderSnapshot | None:
        token = await self._get_valid_token()
        if not token:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="Claude Pro",
                status="error",
                error="No valid Claude Pro token available (credentials missing, expired, or refresh failed)",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    USAGE_URL,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 429:
                    return ProviderSnapshot(
                        provider_id=self.provider_id,
                        plan_name="Claude Pro",
                        status="error",
                        error="Rate limited by Anthropic (429)",
                    )
                resp.raise_for_status()
                try:
                    data = resp.json()
                except Exception:
                    return ProviderSnapshot(
                        provider_id=self.provider_id,
                        plan_name="Claude Pro",
                        status="error",
                        error=f"Non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}",
                    )
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text[:300]
            except Exception:
                pass
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="Claude Pro",
                status="error",
                error=f"Anthropic API error (HTTP {e.response.status_code}): {body}",
            )
        except Exception as e:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="Claude Pro",
                status="error",
                error=str(e),
            )

        limits = []
        for item in data.get("limits", data.get("usage", [])):
            if isinstance(item, dict):
                window_type = item.get("window", item.get("type", "rolling_5h"))
                if "week" in str(window_type).lower() or "7" in str(window_type):
                    window_type = "weekly"
                else:
                    window_type = "rolling_5h"

                used = float(item.get("used", item.get("usage", 0)))
                total = float(item.get("limit", item.get("total", 100)))
                remaining = max(0, total - used)
                pct = (used / total * 100) if total > 0 else 0

                reset_at = None
                if item.get("reset_at"):
                    try:
                        reset_at = datetime.fromisoformat(str(item["reset_at"]).replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                elif item.get("resets_in_seconds"):
                    reset_at = datetime.now() + timedelta(seconds=int(item["resets_in_seconds"]))

                limits.append(LimitWindow(
                    window_type=window_type,
                    usage_value=used,
                    limit_value=total,
                    remaining_value=remaining,
                    usage_percent=pct,
                    reset_at=reset_at,
                    unit=item.get("unit", "percent"),
                ))

        if not limits and data.get("usage_percent") is not None:
            pct = float(data["usage_percent"])
            reset_at = None
            if data.get("reset_at"):
                try:
                    reset_at = datetime.fromisoformat(str(data["reset_at"]).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            limits.append(LimitWindow(
                window_type="rolling_5h",
                usage_value=pct,
                limit_value=100.0,
                remaining_value=100.0 - pct,
                usage_percent=pct,
                reset_at=reset_at,
                unit="percent",
            ))

        return ProviderSnapshot(
            provider_id=self.provider_id,
            plan_name="Claude Pro",
            status="active",
            limits=limits,
        )

    async def health_check(self) -> bool:
        creds = _read_credentials()
        return creds is not None and bool(creds.get("accessToken"))
