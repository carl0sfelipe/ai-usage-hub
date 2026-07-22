from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from collectors.base import LimitWindow, ProviderSnapshot
from server.cache import SnapshotCache


@pytest.fixture
def tmp_cache() -> SnapshotCache:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    cache = SnapshotCache(db_path=db_path, ttl_seconds=300)
    yield cache
    Path(db_path).unlink(missing_ok=True)


class TestSnapshotCache:
    def test_put_and_get(self, tmp_cache: SnapshotCache):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
        )
        tmp_cache.put(snap)
        retrieved = tmp_cache.get("p1")
        assert retrieved is not None
        assert retrieved.provider_id == "p1"
        assert retrieved.plan_name == "P1"
        assert len(retrieved.limits) == 1

    def test_get_expired_returns_none(self, tmp_cache: SnapshotCache):
        tmp_cache._ttl = 0
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
        )
        tmp_cache.put(snap)
        retrieved = tmp_cache.get("p1")
        assert retrieved is None

    def test_get_missing_returns_none(self, tmp_cache: SnapshotCache):
        assert tmp_cache.get("nonexistent") is None

    def test_get_stale_returns_data_even_if_expired(self, tmp_cache: SnapshotCache):
        tmp_cache._ttl = 0
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
        )
        tmp_cache.put(snap)
        stale = tmp_cache.get_stale("p1")
        assert stale is not None
        assert stale.provider_id == "p1"

    def test_get_stale_missing_returns_none(self, tmp_cache: SnapshotCache):
        assert tmp_cache.get_stale("nonexistent") is None

    def test_get_all_returns_multiple(self, tmp_cache: SnapshotCache):
        for pid in ["p1", "p2"]:
            tmp_cache.put(ProviderSnapshot(
                provider_id=pid,
                plan_name=pid,
                status="active",
                limits=[LimitWindow("a", 10, 100, 90, 10.0)],
            ))
        all_snaps = tmp_cache.get_all()
        assert len(all_snaps) == 2
        assert {s.provider_id for s in all_snaps} == {"p1", "p2"}

    def test_put_records_usage_history(self, tmp_cache: SnapshotCache):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[
                LimitWindow("a", 10, 100, 90, 10.0),
                LimitWindow("b", 20, 100, 80, 20.0),
            ],
        )
        tmp_cache.put(snap)
        with sqlite3.connect(tmp_cache._db_path) as conn:
            rows = conn.execute(
                "SELECT provider_id, window_type, usage_percent FROM usage_history WHERE provider_id = ?",
                ("p1",),
            ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "p1"
        assert rows[0][2] == 10.0

    def test_get_burn_rate_returns_rate(self, tmp_cache: SnapshotCache):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
        )
        tmp_cache.put(snap)
        snap.limits[0] = LimitWindow("a", 20, 100, 80, 20.0)
        snap.collected_at = datetime.now()
        tmp_cache.put(snap)
        rate = tmp_cache.get_burn_rate("p1", window_minutes=60)
        assert rate is not None
        assert rate > 0

    def test_get_burn_rate_insufficient_data_returns_none(self, tmp_cache: SnapshotCache):
        snap = ProviderSnapshot(
            provider_id="p1",
            plan_name="P1",
            status="active",
            limits=[LimitWindow("a", 10, 100, 90, 10.0)],
        )
        tmp_cache.put(snap)
        rate = tmp_cache.get_burn_rate("p1")
        assert rate is None
