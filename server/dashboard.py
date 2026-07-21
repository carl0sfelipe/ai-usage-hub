from __future__ import annotations

import asyncio
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
import yaml
from pathlib import Path

from collectors.opencode_go import OpenCodeGoCollector
from collectors.glm_pro import GLMProCollector
from collectors.claude_pro import ClaudeProCollector
from server.cache import SnapshotCache
from server.scheduler import Scheduler
from server.mcp_server import load_config, build_collectors, fetch_all


def build_dashboard(snapshots, recommendation) -> Table:
    table = Table(title="AI Usage Hub", expand=True, show_lines=True)
    table.add_column("Provider", style="bold", width=16)
    table.add_column("Plan", width=20)
    table.add_column("Usage", width=30)
    table.add_column("Reset", width=14)
    table.add_column("Status", width=10)

    for s in snapshots:
        if s.status == "error":
            table.add_row(s.provider_id, s.plan_name, f"[red]{s.error}[/red]", "-", "[red]ERROR[/red]")
            continue

        for l in s.limits:
            pct = l.usage_percent
            if pct >= 85:
                color = "red"
            elif pct >= 60:
                color = "yellow"
            else:
                color = "green"

            bar_len = 20
            filled = int(bar_len * pct / 100)
            bar = f"[{color}]{'█' * filled}{'░' * (bar_len - filled)}[/] {pct:.0f}%"

            reset_str = "-"
            if l.reset_at:
                minutes = max(0, int((l.reset_at - datetime.now()).total_seconds() / 60))
                if minutes < 60:
                    reset_str = f"{minutes}min"
                else:
                    reset_str = f"{minutes // 60}h{minutes % 60}m"

            table.add_row(
                s.provider_id,
                f"{s.plan_name}\n[dim]{l.window_type}[/dim]",
                bar,
                reset_str,
                f"[{color}]{l.remaining_value:.1f} left[/]",
            )

    return table


async def run_dashboard():
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

    console = Console()
    console.print("[bold]AI Usage Hub[/bold] — refreshing every 5min (Ctrl+C to exit)\n")

    while True:
        snapshots = await fetch_all(collectors, cache)
        rec = scheduler.recommend(snapshots, priority)

        table = build_dashboard(snapshots, rec)
        console.print(table)

        rec_color = {"use": "green", "wait": "yellow", "delegate": "cyan", "consolidate": "red"}.get(rec.action, "white")
        console.print(f"\n[{rec_color}]▶ {rec.action.upper()}:[/] {rec.message}")
        if rec.target_provider:
            console.print(f"  → delegate to: [bold]{rec.target_provider}[/bold]")
        console.print(f"\n[dim]Last update: {datetime.now().strftime('%H:%M:%S')}[/dim]\n")

        await asyncio.sleep(300)


def main():
    try:
        asyncio.run(run_dashboard())
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
