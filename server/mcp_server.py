from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from collectors.base import ProviderSnapshot
from collectors.opencode_go import OpenCodeGoCollector
from collectors.glm_pro import GLMProCollector
from collectors.claude_pro import ClaudeProCollector
from collectors.local_tracker import LocalTokenTracker
from collectors.openrouter import OpenRouterCollector
from server.cache import SnapshotCache
from server.scheduler import Scheduler
from server.forecast import Forecaster, forecast_to_dict


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


def build_collectors(config: dict) -> list:
    collectors = []
    providers = config.get("providers", {})
    for pid, pcfg in providers.items():
        if not pcfg.get("enabled"):
            continue
        if pcfg.get("type") == "local_tracking":
            pcfg["provider_id"] = pid
            collectors.append(LocalTokenTracker(pcfg))
        elif pid == "opencode_go":
            collectors.append(OpenCodeGoCollector(pcfg))
        elif pid == "glm_pro":
            collectors.append(GLMProCollector(pcfg))
        elif pid == "claude_pro":
            collectors.append(ClaudeProCollector(pcfg))
        elif pid == "openrouter":
            collectors.append(OpenRouterCollector(pcfg))
    return collectors


async def fetch_all(collectors: list, cache: SnapshotCache) -> list[ProviderSnapshot]:
    snapshots = []
    for c in collectors:
        cached = cache.get(c.provider_id)
        if cached:
            snapshots.append(cached)
            continue
        stale = cache.get_stale(c.provider_id)
        try:
            result = await c.fetch()
            if result:
                cache.put(result)
                snapshots.append(result)
            elif stale:
                snapshots.append(stale)
        except Exception:
            if stale:
                snapshots.append(stale)
    return snapshots


def create_server() -> Server:
    config = load_config()
    cache_cfg = config.get("cache", {})
    cache = SnapshotCache(
        db_path=cache_cfg.get("db_path", "~/.ai-usage-hub/cache.db"),
        ttl_seconds=cache_cfg.get("ttl_seconds", 300),
    )
    collectors = build_collectors(config)
    scheduler = Scheduler(config)
    sched_cfg = config.get("scheduler", {})
    forecaster = Forecaster(
        db_path=cache_cfg.get("db_path", "~/.ai-usage-hub/cache.db"),
        window_minutes=sched_cfg.get("burn_rate_window_minutes", 15),
    )
    priority = [
        p for p, cfg in sorted(
            config.get("providers", {}).items(),
            key=lambda x: x[1].get("priority", 99),
        )
        if cfg.get("enabled")
    ]

    server = Server("ai-usage-hub")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="get_all_usage",
                description="Get usage snapshot for all AI providers (usage%, remaining, reset times)",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_provider_usage",
                description="Get detailed usage for a specific provider",
                inputSchema={
                    "type": "object",
                    "properties": {"provider_id": {"type": "string", "description": "opencode_go | glm_pro | claude_pro | kimi | gemini_pro"}},
                    "required": ["provider_id"],
                },
            ),
            Tool(
                name="get_recommendation",
                description="Which AI provider to use right now (wait/delegate/use/consolidate logic)",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_reset_schedule",
                description="Next reset times for all providers, ordered by soonest",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="should_consolidate",
                description="Whether current session should consolidate context to memory before quota runs out",
                inputSchema={
                    "type": "object",
                    "properties": {"session_minutes": {"type": "number", "description": "How long current session has been running (minutes)"}},
                    "required": ["session_minutes"],
                },
            ),
            Tool(
                name="get_spend_today",
                description="Total USD spent today across all providers",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="get_forecast",
                description="Burn rate forecasts: %/min, minutes to exhaustion, and whether quota will run out before reset",
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="set_provider_limit",
                description="Set token limit for a provider window (persisted to limits.json)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "provider_id": {"type": "string", "description": "Provider ID (e.g. qwen_token_plan)"},
                        "window_type": {"type": "string", "description": "rolling_5h | weekly | monthly"},
                        "limit_tokens": {"type": "number", "description": "Token limit for this window"},
                    },
                    "required": ["provider_id", "window_type", "limit_tokens"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        snapshots = await fetch_all(collectors, cache)

        if name == "get_all_usage":
            data = [s.to_dict() for s in snapshots]
            return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

        elif name == "get_provider_usage":
            pid = arguments.get("provider_id", "")
            match = next((s for s in snapshots if s.provider_id == pid), None)
            if not match:
                return [TextContent(type="text", text=json.dumps({"error": f"Provider '{pid}' not found or no data"}))]
            return [TextContent(type="text", text=json.dumps(match.to_dict(), indent=2, default=str))]

        elif name == "get_recommendation":
            rec = scheduler.recommend(snapshots, priority)
            return [TextContent(type="text", text=json.dumps({
                "action": rec.action,
                "provider": rec.provider,
                "message": rec.message,
                "target_provider": rec.target_provider,
                "minutes_to_reset": rec.minutes_to_reset,
            }, indent=2))]

        elif name == "get_reset_schedule":
            resets = []
            for s in snapshots:
                for l in s.limits:
                    if l.reset_at:
                        minutes = max(0, int((l.reset_at - datetime.now()).total_seconds() / 60))
                        resets.append({
                            "provider": s.provider_id,
                            "window": l.window_type,
                            "reset_at": l.reset_at.isoformat(),
                            "minutes_until_reset": minutes,
                            "current_usage_percent": round(l.usage_percent, 1),
                        })
            resets.sort(key=lambda x: x["minutes_until_reset"])
            return [TextContent(type="text", text=json.dumps(resets, indent=2))]

        elif name == "should_consolidate":
            session_min = arguments.get("session_minutes", 0)
            result = scheduler.should_consolidate(snapshots, int(session_min))
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_spend_today":
            total = sum(s.spend_today_usd or 0 for s in snapshots)
            breakdown = {s.provider_id: s.spend_today_usd for s in snapshots if s.spend_today_usd}
            return [TextContent(type="text", text=json.dumps({"total_usd_today": round(total, 2), "breakdown": breakdown}, indent=2))]

        elif name == "get_forecast":
            forecasts = forecaster.forecast_all(snapshots)
            return [TextContent(type="text", text=json.dumps([forecast_to_dict(f) for f in forecasts], indent=2))]

        elif name == "set_provider_limit":
            pid = arguments.get("provider_id", "")
            window = arguments.get("window_type", "")
            limit = arguments.get("limit_tokens")
            limits_path = Path(__file__).parent.parent / "limits.json"
            data = json.loads(limits_path.read_text()) if limits_path.exists() else {}
            if pid not in data:
                data[pid] = {}
            if window not in data[pid]:
                data[pid][window] = {}
            data[pid][window]["limit_tokens"] = limit
            limits_path.write_text(json.dumps(data, indent=2) + "\n")
            return [TextContent(type="text", text=json.dumps({"ok": True, "provider_id": pid, "window_type": window, "limit_tokens": limit}))]

        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    return server


async def run():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
