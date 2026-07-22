from __future__ import annotations

import asyncio
from datetime import datetime

import yaml
from pathlib import Path
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from server.cache import SnapshotCache
from server.scheduler import Scheduler
from server.mcp_server import load_config, build_collectors, fetch_all


REFRESH_SECONDS = 30


def _color_for_pct(pct: float) -> str:
    if pct >= 85:
        return "red"
    elif pct >= 70:
        return "yellow"
    else:
        return "green"


def _reset_str(reset_at: datetime | None) -> str:
    if reset_at is None:
        return "-"
    minutes = max(0, int((reset_at - datetime.now()).total_seconds() / 60))
    if minutes < 60:
        return f"{minutes}min"
    return f"{minutes // 60}h{minutes % 60}m"


def _action_color(action: str) -> str:
    return {"use": "green", "wait": "yellow", "delegate": "cyan", "consolidate": "red"}.get(action, "white")


def build_dashboard(snapshots, recommendation) -> Layout:
    layout = Layout()
    layout.split(Layout(name="header", size=3), Layout(name="body"), Layout(name="footer", size=5))

    header_text = Text("AI Usage Hub", style="bold white on blue")
    header_text.append("  │  ")
    header_text.append(f"⏱  {REFRESH_SECONDS}s refresh", style="dim")
    header_text.append("  │  ")
    header_text.append("Ctrl+C to exit", style="dim")
    layout["header"].update(Panel(header_text))

    table = Table(expand=True, box=None, padding=(0, 1), show_header=True, header_style="bold underline")
    table.add_column("Provider", style="bold", width=15)
    table.add_column("Window", width=14)
    table.add_column("Usage", width=32)
    table.add_column("Reset", width=12, style="bold")
    table.add_column("Remaining", width=14, justify="right")

    for s in snapshots:
        if s.status == "error":
            msg = s.error or "Unknown error"
            if len(msg) > 50:
                msg = msg[:47] + "..."
            table.add_row(s.provider_id, "-", f"[red]{msg}[/red]", "-", "[red]ERR[/red]")
            continue

        for l in s.limits:
            pct = l.usage_percent
            color = _color_for_pct(pct)
            pbar = ProgressBar(total=100, completed=pct, width=28, style=f"bar.back", complete_style=f"bar.{color}")
            usage_col = Group(pbar, Text(f"  {pct:.0f}%", style=color))
            reset = _reset_str(l.reset_at)
            remaining = f"{l.remaining_value:.1f} {l.unit}" if l.unit != "percent" else f"{l.remaining_value:.0f}%"

            table.add_row(
                s.provider_id,
                l.window_type,
                usage_col,
                reset,
                remaining,
            )

    layout["body"].update(table)

    rec = recommendation
    action = rec.action.upper()
    color = _action_color(rec.action)
    footer_lines = [f"[bold {color}]▶ {action}[/bold {color}]: {rec.message}"]
    if rec.target_provider:
        footer_lines.append(f"  → delegate to: [bold]{rec.target_provider}[/bold]")
    if rec.minutes_to_reset is not None:
        footer_lines.append(f"  → reset in: {rec.minutes_to_reset}min")
    footer_lines.append(f"[dim]Last update: {datetime.now().strftime('%H:%M:%S')}[/dim]")
    layout["footer"].update(Panel("\n".join(footer_lines), title="Recommendation", border_style=color))

    return layout


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

    snapshots = await fetch_all(collectors, cache)
    rec = scheduler.recommend(snapshots, priority)
    dashboard = build_dashboard(snapshots, rec)

    with Live(dashboard, refresh_per_second=4, screen=True) as live:
        while True:
            try:
                snapshots = await fetch_all(collectors, cache)
                rec = scheduler.recommend(snapshots, priority)
                live.update(build_dashboard(snapshots, rec))
            except Exception as e:
                live.update(Panel(f"[red]Error fetching data: {e}[/red]", title="AI Usage Hub"))
            await asyncio.sleep(REFRESH_SECONDS)


def main():
    try:
        asyncio.run(run_dashboard())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
