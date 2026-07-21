from __future__ import annotations

import asyncio
import json
from datetime import datetime

from aiohttp import web
from pathlib import Path
import yaml

from collectors.opencode_go import OpenCodeGoCollector
from collectors.glm_pro import GLMProCollector
from collectors.claude_pro import ClaudeProCollector
from server.cache import SnapshotCache
from server.scheduler import Scheduler
from server.mcp_server import load_config, build_collectors, fetch_all


async def handle_status(request: web.Request) -> web.Response:
    app = request.app
    snapshots = await fetch_all(app["collectors"], app["cache"])
    data = [s.to_dict() for s in snapshots]
    return web.json_response(data)


async def handle_recommendation(request: web.Request) -> web.Response:
    app = request.app
    snapshots = await fetch_all(app["collectors"], app["cache"])
    rec = app["scheduler"].recommend(snapshots, app["priority"])
    return web.json_response({
        "action": rec.action,
        "provider": rec.provider,
        "message": rec.message,
        "target_provider": rec.target_provider,
        "minutes_to_reset": rec.minutes_to_reset,
    })


async def handle_resets(request: web.Request) -> web.Response:
    app = request.app
    snapshots = await fetch_all(app["collectors"], app["cache"])
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
                    "usage_percent": round(l.usage_percent, 1),
                })
    resets.sort(key=lambda x: x["minutes_until_reset"])
    return web.json_response(resets)


def create_app() -> web.Application:
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

    app = web.Application()
    app["cache"] = cache
    app["collectors"] = collectors
    app["scheduler"] = scheduler
    app["priority"] = priority

    app.router.add_get("/status", handle_status)
    app.router.add_get("/recommendation", handle_recommendation)
    app.router.add_get("/resets", handle_resets)
    return app


def main():
    config = load_config()
    port = config.get("server", {}).get("http_port", 6737)
    app = create_app()
    print(f"AI Usage Hub HTTP API on http://127.0.0.1:{port}")
    print(f"  GET /status       — all providers snapshot")
    print(f"  GET /recommendation — which provider to use")
    print(f"  GET /resets       — next reset times")
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
