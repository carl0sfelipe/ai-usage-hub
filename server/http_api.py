from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta

from aiohttp import web
from pathlib import Path
import yaml

from collectors.opencode_go import OpenCodeGoCollector
from collectors.glm_pro import GLMProCollector
from collectors.claude_pro import ClaudeProCollector
from server.cache import SnapshotCache
from server.scheduler import Scheduler
from server.mcp_server import load_config, build_collectors, fetch_all

VALID_OBSERVATION_KINDS = {"rate_limit", "balance", "key_limit", "ok"}
RECOMMENDATION_LOOKBACK_MINUTES = 15


def get_observations_path() -> Path:
    env_path = os.environ.get("OBSERVATIONS_FILE")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).parent.parent / "observations.jsonl"


def read_observations(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def find_recent_bad_observation(
    path: Path, provider: str, kinds: tuple[str, ...] = ("rate_limit", "balance")
) -> dict | None:
    cutoff = datetime.now() - timedelta(minutes=RECOMMENDATION_LOOKBACK_MINUTES)
    for record in reversed(read_observations(path)):
        if record.get("provider") != provider:
            continue
        if record.get("kind") not in kinds:
            continue
        try:
            ts = datetime.fromisoformat(record["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            return record
    return None


async def handle_status(request: web.Request) -> web.Response:
    app = request.app
    snapshots = await fetch_all(app["collectors"], app["cache"])
    data = [s.to_dict() for s in snapshots]
    return web.json_response(data)


async def handle_recommendation(request: web.Request) -> web.Response:
    app = request.app
    snapshots = await fetch_all(app["collectors"], app["cache"])
    queried_provider = request.query.get("provider")

    if queried_provider:
        scoped_rec = app["scheduler"].recommend(snapshots, [queried_provider])
        if scoped_rec.provider == queried_provider:
            action = scoped_rec.action
            message = scoped_rec.message
            target_provider = scoped_rec.target_provider
            minutes_to_reset = scoped_rec.minutes_to_reset
        else:
            action = "use"
            message = f"{queried_provider} has no active data available."
            target_provider = None
            minutes_to_reset = None

        bad_obs = find_recent_bad_observation(
            app["observations_file"], queried_provider, kinds=("rate_limit", "balance", "key_limit")
        )
        if bad_obs is not None:
            action = "wait"
            if minutes_to_reset is None:
                message = (
                    f"{queried_provider} reported {bad_obs['kind']} "
                    f"({bad_obs.get('message', 'no details')}) via observation, reset time unknown. {message}"
                )
            else:
                message = (
                    f"{queried_provider} reported {bad_obs['kind']} "
                    f"({bad_obs.get('message', 'no details')}) via observation. {message}"
                )

        return web.json_response({
            "action": action,
            "provider": queried_provider,
            "message": message,
            "target_provider": target_provider,
            "minutes_to_reset": minutes_to_reset,
        })

    rec = app["scheduler"].recommend(snapshots, app["priority"])

    action = rec.action
    message = rec.message
    bad_obs = find_recent_bad_observation(app["observations_file"], rec.provider)
    minutes_to_reset = rec.minutes_to_reset
    if bad_obs is not None:
        action = "wait"
        if minutes_to_reset is None:
            message = (
                f"{rec.provider} reported {bad_obs['kind']} "
                f"({bad_obs.get('message', 'no details')}) via observation, reset time unknown. {message}"
            )
        else:
            message = (
                f"{rec.provider} reported {bad_obs['kind']} "
                f"({bad_obs.get('message', 'no details')}) via observation. {message}"
            )

    return web.json_response({
        "action": action,
        "provider": rec.provider,
        "message": message,
        "target_provider": rec.target_provider,
        "minutes_to_reset": minutes_to_reset,
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


async def handle_observation(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON body."}, status=400)

    provider = payload.get("provider")
    kind = payload.get("kind")

    if not provider or not isinstance(provider, str):
        return web.json_response({"error": "Field 'provider' is required."}, status=400)
    if kind not in VALID_OBSERVATION_KINDS:
        return web.json_response({
            "error": f"Invalid 'kind': {kind!r}. Must be one of {sorted(VALID_OBSERVATION_KINDS)}.",
        }, status=400)

    record = {
        "provider": provider,
        "model": payload.get("model"),
        "kind": kind,
        "message": payload.get("message"),
        "source": payload.get("source"),
        "timestamp": datetime.now().isoformat(),
    }

    path = request.app["observations_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")

    return web.json_response(record)


async def handle_observations(request: web.Request) -> web.Response:
    provider = request.query.get("provider")
    try:
        limit = int(request.query.get("limit", 20))
    except ValueError:
        return web.json_response({"error": "'limit' must be an integer."}, status=400)

    records = read_observations(request.app["observations_file"])
    if provider:
        records = [r for r in records if r.get("provider") == provider]
    return web.json_response(records[-limit:])


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
    app["observations_file"] = get_observations_path()

    app.router.add_get("/status", handle_status)
    app.router.add_get("/recommendation", handle_recommendation)
    app.router.add_get("/resets", handle_resets)
    app.router.add_post("/observation", handle_observation)
    app.router.add_get("/observations", handle_observations)
    return app


def main():
    config = load_config()
    port = config.get("server", {}).get("http_port", 6737)
    app = create_app()
    print(f"AI Usage Hub HTTP API on http://127.0.0.1:{port}")
    print(f"  GET /status       — all providers snapshot")
    print(f"  GET /recommendation — which provider to use")
    print(f"  GET /resets       — next reset times")
    print(f"  POST /observation — record an agent-reported observation")
    print(f"  GET /observations — recent observations")
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
