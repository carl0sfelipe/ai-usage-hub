from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from collectors.base import LimitWindow, ProviderSnapshot
from collectors.vault import get_vault_credential


class GLMProCollector:
    provider_id = "glm_pro"

    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "https://api.z.ai").rstrip("/")

    @property
    def _api_key(self) -> str:
        return get_vault_credential("GLM_API_KEY")

    async def fetch(self) -> ProviderSnapshot | None:
        key = self._api_key
        if not key:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="GLM Pro",
                status="error",
                error="GLM_API_KEY not found in vault",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/api/monitor/usage/quota/limit",
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="GLM Pro",
                status="error",
                error=str(e),
            )

        limits = []
        result = data.get("data", data)
        raw_limits = result.get("limits", [])
        plan_level = result.get("level", "unknown")

        for item in raw_limits:
            limit_type = item.get("type", "")
            unit_code = item.get("unit", 0)
            percentage = float(item.get("percentage", 0))
            next_reset_ms = item.get("nextResetTime")

            if limit_type == "TOKENS_LIMIT":
                if unit_code <= 3:
                    window_type = "rolling_5h"
                else:
                    window_type = "weekly"
                used = percentage
                total = 100.0
                remaining = max(0, 100.0 - percentage)
                unit = "percent"
            elif limit_type == "TIME_LIMIT":
                window_type = "monthly"
                total = float(item.get("usage", 1))
                used = float(item.get("currentValue", 0))
                remaining = float(item.get("remaining", max(0, total - used)))
                percentage = (used / total * 100) if total > 0 else 0
                unit = "calls"
            else:
                window_type = f"unit_{unit_code}"
                used = percentage
                total = 100.0
                remaining = max(0, 100.0 - percentage)
                unit = "percent"

            reset_at = None
            if next_reset_ms:
                try:
                    reset_at = datetime.fromtimestamp(next_reset_ms / 1000)
                except (ValueError, TypeError, OSError):
                    pass

            limits.append(LimitWindow(
                window_type=window_type,
                usage_value=used,
                limit_value=total,
                remaining_value=remaining,
                usage_percent=percentage,
                reset_at=reset_at,
                unit=unit,
            ))

        return ProviderSnapshot(
            provider_id=self.provider_id,
            plan_name=f"GLM Pro ({plan_level})",
            status="active",
            limits=limits,
        )

    async def health_check(self) -> bool:
        return bool(self._api_key)
