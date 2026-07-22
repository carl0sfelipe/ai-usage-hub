from __future__ import annotations

from datetime import datetime, timedelta

from collectors.base import LimitWindow, ProviderSnapshot
from server.scheduler import Scheduler


PRIORITY = ["opencode_go", "glm_pro", "claude_pro"]


def _snap(
    provider_id: str,
    usage_pct: float,
    remaining: float | None = None,
    reset_at: datetime | None = None,
    status: str = "active",
) -> ProviderSnapshot:
    if remaining is None:
        remaining = 100.0 - usage_pct
    return ProviderSnapshot(
        provider_id=provider_id,
        plan_name=provider_id,
        status=status,
        limits=[
            LimitWindow(
                window_type="rolling_5h",
                usage_value=usage_pct,
                limit_value=100.0,
                remaining_value=remaining,
                usage_percent=usage_pct,
                reset_at=reset_at,
                unit="percent",
            ),
        ],
    )


class TestSchedulerRecommend:
    def make_scheduler(self, **overrides) -> Scheduler:
        config = {
            "scheduler": {
                "wait_threshold_percent": 85,
                "wait_max_minutes": 30,
                "delegate_threshold_percent": 85,
                "consolidate_threshold_percent": 70,
            }
        }
        config["scheduler"].update(overrides)
        return Scheduler(config)

    def test_primary_below_50_returns_use(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 25.0, reset_at=datetime.now() + timedelta(hours=3)),
            _snap("glm_pro", 10.0, reset_at=datetime.now() + timedelta(hours=6)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "use"
        assert rec.provider == "opencode_go"

    def test_primary_above_85_with_reset_under_30min_returns_wait(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 90.0, reset_at=datetime.now() + timedelta(minutes=15)),
            _snap("glm_pro", 10.0, reset_at=datetime.now() + timedelta(hours=6)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "wait"
        assert rec.provider == "opencode_go"
        assert rec.minutes_to_reset is not None and rec.minutes_to_reset <= 30

    def test_primary_above_85_with_reset_over_30min_and_alternative_returns_delegate(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 90.0, reset_at=datetime.now() + timedelta(hours=2)),
            _snap("glm_pro", 30.0, reset_at=datetime.now() + timedelta(hours=6)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "delegate"
        assert rec.provider == "opencode_go"
        assert rec.target_provider == "glm_pro"

    def test_primary_above_85_with_reset_over_30min_no_alternative_returns_wait(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 90.0, reset_at=datetime.now() + timedelta(hours=2)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "wait"
        assert rec.provider == "opencode_go"

    def test_all_providers_above_70_returns_consolidate(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 80.0, reset_at=datetime.now() + timedelta(hours=1)),
            _snap("glm_pro", 75.0, reset_at=datetime.now() + timedelta(hours=2)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "consolidate"
        assert rec.provider == "opencode_go"

    def test_no_active_providers_returns_default_use(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 0.0, status="error"),
            _snap("glm_pro", 0.0, status="error"),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "use"
        assert "unknown" in rec.provider or rec.provider == PRIORITY[0]

    def test_single_provider_above_85_no_alternative_returns_wait(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 95.0, reset_at=datetime.now() + timedelta(hours=5)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "wait"
        assert rec.provider == "opencode_go"

    def test_consolidate_not_triggered_when_only_one_provider(self):
        sched = self.make_scheduler()
        snaps = [
            _snap("opencode_go", 85.0, reset_at=datetime.now() + timedelta(minutes=10)),
        ]
        rec = sched.recommend(snaps, PRIORITY)
        assert rec.action == "wait"
