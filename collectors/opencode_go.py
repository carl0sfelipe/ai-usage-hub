from __future__ import annotations

from datetime import datetime, timedelta

import httpx

from collectors.base import LimitWindow, ProviderSnapshot
from collectors.vault import get_vault_credential


class OpenCodeGoCollector:
    provider_id = "opencode_go"

    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "https://api.opencode.ai/zen/go/v1").rstrip("/")

    @property
    def _api_key(self) -> str:
        return get_vault_credential("OPENCODE_GO_API_KEY")

    async def fetch(self) -> ProviderSnapshot | None:
        key = self._api_key
        if not key:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="OpenCode Go",
                status="error",
                error="OPENCODE_GO_API_KEY not found in vault",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/usage",
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="OpenCode Go",
                status="error",
                error=str(e),
            )

        limits = []
        windows = [
            ("rolling_5h", "five_hour"),
            ("weekly", "weekly"),
            ("monthly", "monthly"),
        ]
        for window_type, key_name in windows:
            w = data.get(key_name) or data.get(window_type)
            if not w:
                continue
            used = float(w.get("used", w.get("usage", 0)))
            total = float(w.get("limit", w.get("total", 1)))
            remaining = max(0, total - used)
            pct = (used / total * 100) if total > 0 else 0
            reset_at = None
            if w.get("reset_at"):
                try:
                    reset_at = datetime.fromisoformat(w["reset_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            elif w.get("resets_in_seconds"):
                reset_at = datetime.now() + timedelta(seconds=int(w["resets_in_seconds"]))
            limits.append(LimitWindow(
                window_type=window_type,
                usage_value=used,
                limit_value=total,
                remaining_value=remaining,
                usage_percent=pct,
                reset_at=reset_at,
                unit="usd",
            ))

        return ProviderSnapshot(
            provider_id=self.provider_id,
            plan_name="OpenCode Go ($10/mo)",
            status="active",
            limits=limits,
            spend_today_usd=data.get("today_usd"),
        )

    async def health_check(self) -> bool:
        key = self._api_key
        if not key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self._base_url}/usage",
                    headers={"Authorization": f"Bearer {key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
