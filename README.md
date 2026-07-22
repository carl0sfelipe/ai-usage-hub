# AI Usage Hub

Monitors your AI subscription quotas across multiple providers (OpenCode Go, GLM Pro, Claude Pro) via MCP tools, HTTP API, or a TUI dashboard.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- [agent-vault](https://github.com/anomalyco/agent-vault) CLI with `orbe-main` vault

## Setup

```bash
git clone ~/ai-usage-hub
cd ai-usage-hub
uv sync
```

## Configure credentials

```bash
agent-vault vault credential set OPENCODE_GO_API_KEY <your-key> --vault orbe-main
agent-vault vault credential set GLM_API_KEY <your-key> --vault orbe-main
agent-vault vault credential set CLAUDE_OAUTH_TOKEN <your-token> --vault orbe-main
```

## Usage

### MCP server (stdio)

```bash
uv run python -m server.mcp_server
```

### HTTP API

```bash
uv run python -m server.http_api
# Listening on http://localhost:6737
curl http://localhost:6737/status
```

### Dashboard

```bash
uv run ai-usage-dashboard
```

## Integrate with clients

### OpenCode

Add to `~/.config/opencode/opencode.json`:
```json
{
  "mcpServers": {
    "ai-usage-hub": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/mini/ai-usage-hub", "python", "-m", "server.mcp_server"],
      "env": {}
    }
  }
}
```

### Hermes

Add to `~/.hermes/config.yaml`:
```yaml
mcp_servers:
  ai-usage-hub:
    command: uv
    args: ["run", "--directory", "/Users/mini/ai-usage-hub", "python", "-m", "server.mcp_server"]
```

## Tests

```bash
uv run pytest
```

## Project structure

```
ai-usage-hub/
├── collectors/       # Per-provider API clients
│   ├── base.py       # LimitWindow, ProviderSnapshot, BaseCollector
│   ├── opencode_go.py
│   ├── glm_pro.py
│   └── claude_pro.py
├── server/           # Core logic
│   ├── cache.py      # SQLite cache with TTL and usage_history
│   ├── scheduler.py  # Recommendation engine (use/wait/delegate/consolidate)
│   ├── forecast.py   # Burn rate and ETA calculations
│   ├── mcp_server.py # MCP stdio server (6 tools)
│   ├── http_api.py   # aiohttp API on :6737
│   └── dashboard.py  # Rich TUI
├── config.yaml       # Providers, cache, scheduler config
├── docs/CONFIG.md    # Configuration reference
└── tests/            # Unit and E2E tests
```
