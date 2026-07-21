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
from server.cache import SnapshotCache
from server.scheduler import Scheduler


def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


def build_collectors(config: dict) -> list:
    collectors = []
    providers = config.get("providers", {})
    if providers.get("opencode_go", {}).get("enabled"):
        collectors.append(OpenCodeGoCollector(providers["opencode_go"]))
    if providers.get("glm_pro", {}).get("enabled"):
        collectors.append(GLMProCollector(providers["glm_pro"]))
    if providers.get("claude_pro", {}).get("enabled"):
        collectors.append(ClaudeProCollector(providers["claude_pro"]))
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
