from __future__ import annotations

import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from server.http_api import (
    find_recent_bad_observation,
    handle_observation,
    handle_observations,
    handle_recommendation,
    read_observations,
    VALID_OBSERVATION_KINDS,
)
from aiohttp import web


def _make_app(tmp_path, scheduler, priority=None):
    app = web.Application()
    app["cache"] = _NullCache()
    app["collectors"] = []
    app["scheduler"] = scheduler
    app["priority"] = priority or ["test_provider"]
    app["observations_file"] = tmp_path / "observations.jsonl"

    app.router.add_get("/recommendation", handle_recommendation)
    app.router.add_post("/observation", handle_observation)
    app.router.add_get("/observations", handle_observations)
    return app


class _NullCache:
    def get(self, provider_id):
        return None

    def get_stale(self, provider_id):
        return None

    def put(self, snapshot):
        pass


class _StubScheduler:
    def __init__(self, rec):
        self._rec = rec

    def recommend(self, snapshots, priority_order):
        return self._rec


class _Rec:
    def __init__(self, provider="test_provider"):
        self.action = "use"
        self.provider = provider
        self.message = f"{provider} at 0%. Safe to use."
        self.target_provider = None
        self.minutes_to_reset = 100


@pytest.fixture
async def client(tmp_path, monkeypatch):
    async def _fetch_all(collectors, cache):
        return []

    monkeypatch.setattr("server.http_api.fetch_all", _fetch_all)
    app = _make_app(tmp_path, _StubScheduler(_Rec()))
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


async def test_post_observation_valid(client):
    resp = await client.post("/observation", json={
        "provider": "opencode_go",
        "kind": "rate_limit",
        "message": "Rate limit exceeded",
        "source": "dispatch",
    })
    assert resp.status == 200
    body = await resp.json()
    assert body["provider"] == "opencode_go"
    assert body["kind"] == "rate_limit"
    assert "timestamp" in body


async def test_post_observation_invalid_kind(client):
    resp = await client.post("/observation", json={"provider": "x", "kind": "bogus"})
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


async def test_post_observation_missing_provider(client):
    resp = await client.post("/observation", json={"kind": "ok"})
    assert resp.status == 400


async def test_get_observations_filters_and_limits(client):
    for i in range(3):
        await client.post("/observation", json={"provider": "a", "kind": "ok", "message": str(i)})
    await client.post("/observation", json={"provider": "b", "kind": "ok"})

    resp = await client.get("/observations", params={"provider": "a", "limit": "2"})
    body = await resp.json()
    assert len(body) == 2
    assert all(r["provider"] == "a" for r in body)


async def test_recommendation_overridden_by_recent_rate_limit(client):
    await client.post("/observation", json={
        "provider": "test_provider",
        "kind": "rate_limit",
        "message": "Rate limit exceeded",
    })
    resp = await client.get("/recommendation")
    body = await resp.json()
    assert body["action"] == "wait"
    assert "rate_limit" in body["message"]
    assert set(body.keys()) == {"action", "provider", "message", "target_provider", "minutes_to_reset"}


async def test_recommendation_unaffected_without_observation(client):
    resp = await client.get("/recommendation")
    body = await resp.json()
    assert body["action"] == "use"
