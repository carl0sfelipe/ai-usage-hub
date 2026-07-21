# Architecture — AI Usage Hub

> **Architect:** Winston (BMAD)
> **Data:** 2026-07-20
> **Stack:** Python 3.12, uv, MCP SDK, httpx, rich (TUI)

---

## 1. Visão Geral

```
┌─────────────────────────────────────────────────────────────┐
│                      ai-usage-hub                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Collectors  │  │   Engine    │  │    Interfaces        │ │
│  │             │  │             │  │                      │ │
│  │ opencode.py │→ │ scheduler.py│→ │ mcp_server.py (stdio)│ │
│  │ glm.py      │  │ forecast.py │  │ dashboard.py (TUI)   │ │
│  │ claude.py   │  │ cache.py    │  │ http_api.py (:6737)  │ │
│  │ kimi.py     │  │             │  │                      │ │
│  │ gemini.py   │  │             │  │                      │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              config.yaml (keys, intervals)              ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 2. Componentes

### 2.1 Collectors (`collectors/`)

Cada collector implementa protocolo `BaseCollector`:

```python
class BaseCollector(Protocol):
    provider_id: str
    async def fetch(self) -> ProviderSnapshot | None: ...
    async def health_check(self) -> bool: ...
```

`ProviderSnapshot` é o schema unificado (dataclass):

```python
@dataclass
class LimitWindow:
    window_type: str          # "rolling_5h" | "weekly" | "monthly"
    usage_value: float
    limit_value: float
    remaining_value: float
    usage_percent: float
    reset_at: datetime | None
    unit: str                 # "percent" | "usd" | "messages"

@dataclass
class ProviderSnapshot:
    provider_id: str
    plan_name: str
    collected_at: datetime
    status: str               # "active" | "error" | "no_data"
    limits: list[LimitWindow]
    spend_today_usd: float | None
    error: str | None
```

### 2.2 Engine (`server/`)

- **cache.py**: SQLite em `~/.ai-usage-hub/cache.db`. TTL 5 min por provider. Stale-while-revalidate.
- **scheduler.py**: Lógica de recomendação (wait/delegate/consolidate/use).
- **forecast.py**: Cálculo de burn rate e tempo até exaustão.

### 2.3 Interfaces

- **mcp_server.py**: MCP via stdio (usando `mcp` SDK Python). Tools: `get_all_usage`, `get_provider_usage`, `get_recommendation`, `get_reset_schedule`, `should_consolidate`, `get_spend_today`.
- **dashboard.py**: TUI com `rich` (barras, cores, tabela). Refresh 5 min.
- **http_api.py**: `aiohttp` em `:6737`, `GET /status` → JSON completo.

### 2.4 Config (`config.yaml`)

```yaml
providers:
  opencode_go:
    enabled: true
    api_key_env: OPENCODE_API_KEY
    base_url: "https://zen.opencode.ai"
    priority: 1
  glm_pro:
    enabled: true
    api_key_path: "~/.config/zai/key.json"
    base_url: "https://api.z.ai"
    priority: 2
  claude_pro:
    enabled: true
    keychain_service: "Claude Code-credentials"
    priority: 3
  kimi:
    enabled: false
    cli_path: "kimi"
    priority: 4
  gemini_pro:
    enabled: false
    priority: 5

cache:
  ttl_seconds: 300
  db_path: "~/.ai-usage-hub/cache.db"

server:
  http_port: 6737

scheduler:
  wait_threshold_percent: 85
  wait_max_minutes: 30
  delegate_threshold_percent: 85
  consolidate_threshold_percent: 70
  burn_rate_window_minutes: 15
```

## 3. MCP Integration

Registro nos clients:

```json
// ~/.config/opencode/opencode.json → mcpServers
{
  "ai-usage-hub": {
    "command": "uv",
    "args": ["run", "--directory", "/Users/mini/ai-usage-hub", "python", "-m", "server.mcp_server"],
    "env": {}
  }
}
```

Hermes: `~/.hermes/config.yaml` → mcp_servers section.

## 4. Decisões

| # | Decisão | Racional |
|---|---------|----------|
| 1 | Python (não Swift) | MCP SDK Python é maduro; collectors são HTTP simples; TUI com rich |
| 2 | SQLite cache (não memória) | Sobrevive restart; histórico básico pra burn rate |
| 3 | stdio MCP (não HTTP) | Compatível com todos os clients (Hermes, Claude Code, OpenCode) |
| 4 | Porta 6737 (não 6736) | 6736 é do OpenUsage; evitar conflito |
| 5 | Collectors async (httpx) | Paralelismo nas chamadas; timeout individual por provider |
| 6 | config.yaml (não .env) | Estrutura hierárquica; suporta disable/enable por provider |

## 5. Estrutura de ficheiros

```
~/ai-usage-hub/
├── pyproject.toml
├── config.yaml
├── collectors/
│   ├── __init__.py
│   ├── base.py          # Protocol + dataclasses
│   ├── opencode_go.py
│   ├── glm_pro.py
│   ├── claude_pro.py
│   ├── kimi.py
│   └── gemini_pro.py
├── server/
│   ├── __init__.py
│   ├── cache.py
│   ├── scheduler.py
│   ├── forecast.py
│   ├── mcp_server.py    # MCP stdio
│   ├── http_api.py      # HTTP :6737
│   └── dashboard.py     # TUI (rich)
├── _bmad-output/
│   └── planning-artifacts/
│       ├── PRD.md
│       └── architecture.md
└── tests/
    ├── test_collectors.py
    └── test_scheduler.py
```
