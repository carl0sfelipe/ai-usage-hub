from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from collectors.base import LimitWindow, ProviderSnapshot
from collectors.vault import get_vault_credential


class ClaudeProCollector:
    provider_id = "claude_pro"

    def __init__(self, config: dict):
        pass

    @property
    def _token(self) -> str:
        return get_vault_credential("CLAUDE_OAUTH_TOKEN")

    async def fetch(self) -> ProviderSnapshot | None:
        token = self._token
        if not token:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="Claude Pro",
                status="error",
                error="CLAUDE_OAUTH_TOKEN not found in vault",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/api/oauth/usage",
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
                data = resp.json()
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
        return bool(self._token)
