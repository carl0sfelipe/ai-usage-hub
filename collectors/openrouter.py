from __future__ import annotations

import json
from pathlib import Path

import httpx

from collectors.base import LimitWindow, ProviderSnapshot


def _read_openrouter_key(auth_path: Path) -> str:
    if not auth_path.exists():
        return ""
    try:
        data = json.loads(auth_path.read_text())
    except Exception:
        return ""
    entry = data.get("openrouter") or {}
    return entry.get("key", "") or ""


class OpenRouterCollector:
    provider_id = "openrouter"

    def __init__(self, config: dict):
        self._base_url = config.get("base_url", "https://openrouter.ai/api/v1").rstrip("/")
        self._auth_path = Path(
            config.get("auth_path", "~/.local/share/opencode/auth.json")
        ).expanduser()

    @property
    def _api_key(self) -> str:
        return _read_openrouter_key(self._auth_path)

    async def fetch(self) -> ProviderSnapshot | None:
        key = self._api_key
        if not key:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="OpenRouter",
                status="error",
                error="openrouter key not found in opencode auth store",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/key",
                    headers={"Authorization": f"Bearer {key}"},
                )
                resp.raise_for_status()
                try:
                    body = resp.json()
                except Exception:
                    return ProviderSnapshot(
                        provider_id=self.provider_id,
                        plan_name="OpenRouter",
                        status="error",
                        error=f"Non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}",
                    )
        except Exception as e:
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="OpenRouter",
                status="error",
                error=str(e),
            )

        data = body.get("data")
        if not isinstance(data, dict):
            return ProviderSnapshot(
                provider_id=self.provider_id,
                plan_name="OpenRouter",
                status="error",
                error=f"Unexpected /key response shape: {json.dumps(body)[:200]}",
            )

        limit = data.get("limit")
        usage = float(data.get("usage") or 0)
        limits = []
        status = "active"

        if limit is None:
            # chave sem teto fixo (ex: free tier / sem limite definido); nada a reportar como janela
            pass
        else:
            limit = float(limit)
            remaining = data.get("limit_remaining")
            remaining = float(remaining) if remaining is not None else max(0.0, limit - usage)
            pct = (usage / limit * 100) if limit > 0 else 0.0
            limits.append(LimitWindow(
                window_type="key_total",
                usage_value=usage,
                limit_value=limit,
                remaining_value=remaining,
                usage_percent=pct,
                unit="usd",
            ))
            if remaining <= 0:
                status = "exhausted"

        return ProviderSnapshot(
            provider_id=self.provider_id,
            plan_name="OpenRouter",
            status=status,
            limits=limits,
            spend_today_usd=data.get("usage_daily"),
        )

    async def health_check(self) -> bool:
        key = self._api_key
        if not key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self._base_url}/key",
                    headers={"Authorization": f"Bearer {key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
