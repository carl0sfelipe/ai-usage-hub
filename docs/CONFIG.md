# Configuration Reference

All settings in `config.yaml`.

## providers

```yaml
providers:
  opencode_go:
    enabled: true           # Enable/disable collector
    base_url: "https://api.opencode.ai/zen/go/v1"
    priority: 1             # Lower = higher priority in recommendation
  glm_pro:
    enabled: true
    base_url: "https://api.z.ai"
    priority: 2
  claude_pro:
    enabled: true
    priority: 3
  kimi:
    enabled: false          # Optional, not implemented
    cli_path: "kimi"
    priority: 4
  gemini_pro:
    enabled: false          # Optional, not implemented
    priority: 5
```

### Provider fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Whether the collector runs on fetch |
| `base_url` | string | (varies) | API base URL for the provider |
| `priority` | int | `99` | Order in recommendation priority list (lower = first) |
| `cli_path` | string | — | CLI binary path (for CLI-based collectors) |

## cache

```yaml
cache:
  ttl_seconds: 300     # How long snapshots stay fresh (seconds)
  db_path: "~/.ai-usage-hub/cache.db"
```

### Cache fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `ttl_seconds` | int | `300` | Snapshot TTL; stale-while-revalidate returns old data after expiry |
| `db_path` | string | `~/.ai-usage-hub/cache.db` | SQLite database path |

## server

```yaml
server:
  http_port: 6737      # Port for the HTTP API
```

### Server fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `http_port` | int | `6737` | Port for the aiohttp `/status` endpoint |

## scheduler

```yaml
scheduler:
  wait_threshold_percent: 85       # Usage % above which recommend "wait"
  wait_max_minutes: 30             # Max minutes to wait before suggesting delegate
  delegate_threshold_percent: 85   # Usage % threshold for alternative providers
  consolidate_threshold_percent: 70  # All providers above this → "consolidate"
  burn_rate_window_minutes: 15     # Window for burn rate calculation
```

### Scheduler fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `wait_threshold_percent` | float | `85` | Primary provider usage above this triggers "wait" or "delegate" |
| `wait_max_minutes` | int | `30` | If reset is within this many minutes, recommend "wait" instead of "delegate" |
| `delegate_threshold_percent` | float | `85` | Alternative providers must be below this to be suggested for delegation |
| `consolidate_threshold_percent` | float | `70` | If all active providers are above this, recommend "consolidate" |
| `burn_rate_window_minutes` | int | `15` | Lookback window for usage_history burn rate calculation |
