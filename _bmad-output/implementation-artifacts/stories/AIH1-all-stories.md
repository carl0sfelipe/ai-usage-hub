# EPIC-AIH1 Stories — AI Usage Hub MVP

> 8 stories para fechar o MVP do ai-usage-hub. Branch `feat/aih1-mvp` em `~/ai-usage-hub`.
> Models: flash=junior, pro=pleno, qwen-3.8-preview=senior.

---

# [AIH1-01] Testes unitários (collectors + scheduler)

**Est:** M | **Model:** flash (junior) | **Branch:** feat/aih1-mvp

## User Story
Como dev, quero cobertura de testes pros collectors (com mocks HTTP) e scheduler, pra evitar regressões.

## Tarefas
1. Criar `tests/__init__.py`, `tests/conftest.py` (fixtures de snapshots mockados)
2. `tests/test_base.py` — testa `LimitWindow.to_dict`, `ProviderSnapshot.most_restrictive`, `ProviderSnapshot.to_dict`
3. `tests/test_scheduler.py` — testa `Scheduler.recommend()` em 5 cenários:
   - primary < 50% → action="use"
   - primary >= 85% e reset <= 30min → action="wait"
   - primary >= 85% e reset > 30min → action="delegate"
   - todos > 70% → action="consolidate"
   - sem providers ativos → fallback default
4. `tests/test_cache.py` — testa `SnapshotCache` get/set/expiração (mock sqlite temp file)
5. `tests/test_collectors.py` — testa parsing de resposta mockada (httpx MockTransport)
   - opencode_go: response JSON com 3 windows → 3 LimitWindow corretos
   - glm_pro: response JSON → snapshot correto
   - claude_pro: sem keychain → status="error"
6. Adicionar `pytest` + `pytest-asyncio` em `pyproject.toml` dev dependencies
7. Criar `pytest.ini` ou config no pyproject: `asyncio_mode = auto`
8. Rodar `uv run pytest` → 0 failures
9. Commit: `test(aih): add unit tests for collectors scheduler cache`

## Critérios
- [ ] ≥ 20 testes
- [ ] `uv run pytest` → 0 failures
- [ ] Coverage ≥ 60% (era 0%)
- [ ] Commit: `test(aih): add unit tests for collectors scheduler cache`

---

# [AIH1-02] server/forecast.py (burn rate + ETA)

**Est:** M | **Model:** pro (pleno) | **Branch:** feat/aih1-mvp

## User Story
Como agent, quero saber quantos minutos até meu provider esgotar (baseado em burn rate), pra decidir consolidar contexto.

## Contexto
`server/cache.py` já grava `usage_history` (provider_id, window_type, usage_percent, recorded_at) a cada fetch. Falta ler esse histórico e calcular burn rate.

## Tarefas
1. Criar `server/forecast.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from collectors.base import LimitWindow, ProviderSnapshot

@dataclass
class Forecast:
    provider_id: str
    window_type: str
    burn_rate_per_min: float  # % por minuto
    minutes_to_exhaustion: int | None  # None se não dá pra calcular
    will_exhaust_before_reset: bool

class Forecaster:
    def __init__(self, db_path: str, window_minutes: int = 15):
        self._db_path = db_path
        self._window = window_minutes

    def forecast(self, snapshot: ProviderSnapshot) -> list[Forecast]:
        """Para cada limit window, calcula burn rate baseado em usage_history."""
        # SELECT usage_percent, recorded_at FROM usage_history
        # WHERE provider_id = ? AND window_type = ?
        # AND recorded_at >= datetime('now', '-15 minutes')
        # ORDER BY recorded_at ASC
        # burn_rate = (last - first) / minutes_elapsed
        # minutes_to_exhaustion = (100 - current) / burn_rate
        ...

    def _query_history(self, provider_id: str, window_type: str) -> list[tuple[float, datetime]]:
        ...
```

2. Integrar no `mcp_server.py`: adicionar tool `get_forecast` que retorna forecasts de todos providers
3. Testes: `tests/test_forecast.py` — 5+ casos (sem histórico → None, histórico estável → 0 burn, histórico subindo → forecast correto, histórico descendo → minutes_to_exhaustion alto)
4. Commit: `feat(aih): add burn rate forecaster with usage_history analysis`

## Critérios
- [ ] `server/forecast.py` com `Forecaster` + `Forecast`
- [ ] Tool MCP `get_forecast` exposta
- [ ] Testes cobrem casos edge
- [ ] Commit: `feat(aih): add burn rate forecaster with usage_history analysis`

---

# [AIH1-03] README + .gitignore + docs

**Est:** S | **Model:** flash (junior) | **Branch:** feat/aih1-mvp

## Tarefas
1. Criar `.gitignore`:
```
.venv/
__pycache__/
*.pyc
*.db
.env
.ai-usage-hub/
.pytest_cache/
.ruff_cache/
```

2. Criar `README.md` com:
   - O que é (1 parágrafo do PRD)
   - Pré-requisitos (Python 3.12+, uv, agent-vault)
   - Setup: `uv sync`
   - Configurar credenciais: `agent-vault vault credential set OPENCODE_GO_API_KEY ... --vault orbe-main`
   - Rodar MCP: `uv run python -m server.mcp_server`
   - Rodar dashboard: `uv run ai-usage-dashboard`
   - Rodar HTTP API: `uv run python -m server.http_api`
   - Integrar com OpenCode (config JSON mcpServers)
   - Integrar com Hermes (config.yaml mcp_servers)
   - Integrar com ZCode
   - Testar: `uv run pytest`
   - Estrutura de arquivos (linkar architecture.md)

3. Criar `docs/CONFIG.md` — detalha cada chave de `config.yaml` com exemplo
4. Commit: `docs(aih): add README gitignore and config docs`

## Critérios
- [ ] README com setup completo + integração 3 clients
- [ ] `.gitignore` cobre `.venv/`, `*.db`, `.env`
- [ ] `docs/CONFIG.md` documenta config.yaml
- [ ] Commit: `docs(aih): add README gitignore and config docs`

---

# [AIH1-04] Validar collectors reais (rodar contra APIs, fix bugs)

**Est:** M | **Model:** pro (pleno) | **Branch:** feat/aih1-mvp

## User Story
Como dev, quero confirmar que os 3 collectors ativos (opencode_go, glm_pro, claude_pro) funcionam contra APIs reais e corrigir o que estiver quebrado.

## Tarefas
1. Rodar cada collector isoladamente contra API real:

```python
# tests/manual_validate.py (NÃO commitar, só pra debug)
import asyncio
from collectors.opencode_go import OpenCodeGoCollector
from collectors.glm_pro import GLMProCollector
from collectors.claude_pro import ClaudeProCollector

async def main():
    for cls, cfg in [
        (OpenCodeGoCollector, {"base_url": "https://api.opencode.ai/zen/go/v1"}),
        (GLMProCollector, {"base_url": "https://api.z.ai"}),
        (ClaudeProCollector, {}),
    ]:
        c = cls(cfg)
        snap = await c.fetch()
        print(f"\n=== {c.provider_id} ===")
        print(snap.to_dict() if snap else "None")

asyncio.run(main())
```

Rodar: `cd ~/ai-usage-hub && uv run python tests/manual_validate.py`

2. Para cada collector, validar:
   - Status 200 da API real
   - Parsing do JSON → LimitWindow corretos
   - Cálculo de usage_percent
   - reset_at preenchido (ISO format)

3. Se quebrar (provável):
   - URL errada → corrigir no collector
   - Schema mudou → ajustar parsing
   - Auth falha → validar Agent Vault credential
   - Rate limit → documentar

4. Atualizar `collectors/__init__.py` se preciso

5. Commit: `fix(aih): validate and fix collectors against real APIs`

## Critérios
- [ ] opencode_go: snapshot retornado com 3 windows (5h/semanal/mensal)
- [ ] glm_pro: snapshot retornado com 2 windows (5h/7d)
- [ ] claude_pro: snapshot retornado (ou status="error" documentado se OAuth não disponível)
- [ ] Bugs encontrados corrigidos
- [ ] Commit: `fix(aih): validate and fix collectors against real APIs`

---

# [AIH1-05] Integrar MCP no opencode + hermes + zcode

**Est:** S | **Model:** flash (junior) | **Branch:** feat/aih1-mvp

## Tarefas
1. Identificar paths de config:
   - OpenCode: `~/.config/opencode/opencode.json` ou `~/.opencode/config.json`
   - Hermes: `~/.hermes/config.yaml` (seção `mcp_servers`)
   - ZCode: `~/.zcode/config.json` ou equivalente

2. Adicionar config MCP (exemplo):
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

3. Para Hermes (YAML):
```yaml
mcp_servers:
  ai-usage-hub:
    command: uv
    args: ["run", "--directory", "/Users/mini/ai-usage-hub", "python", "-m", "server.mcp_server"]
```

4. **NÃO modificar configs de MCP que já existem** — só adicionar a nova entrada

5. Validar (se possível): reiniciar um client e ver se carrega a tool

6. Documentar no README (linkar da AIH1-03)

7. Commit: `feat(aih): register mcp server in opencode hermes zcode configs`

## Critérios
- [ ] OpenCode config tem `ai-usage-hub` em mcpServers
- [ ] Hermes config tem `ai-usage-hub` em mcp_servers
- [ ] ZCode config tem (se aplicável)
- [ ] Path `--directory /Users/mini/ai-usage-hub` correto
- [ ] Commit: `feat(aih): register mcp server in opencode hermes zcode configs`

---

# [AIH1-06] LaunchAgent para daemon

**Est:** XS | **Model:** flash (junior) | **Branch:** feat/aih1-mvp

## Tarefas
1. Criar `scripts/install-launchagent.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
PLIST="$HOME/Library/LaunchAgents/com.ai-usage-hub.http.plist"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.ai-usage-hub.http</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/mini/.local/bin/uv</string>
    <string>run</string>
    <string>--directory</string>
    <string>/Users/mini/ai-usage-hub</string>
    <string>python</string>
    <string>-m</string>
    <string>server.http_api</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/ai-usage-hub.log</string>
  <key>StandardErrorPath</key><string>/tmp/ai-usage-hub.err</string>
</dict>
</plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "LaunchAgent installed. HTTP API will be available at http://localhost:6737/status"
```

2. `chmod +x scripts/install-launchagent.sh`
3. Rodar: `./scripts/install-launchagent.sh`
4. Validar: `curl http://localhost:6737/status`
5. Commit: `feat(aih): add launchagent for http api daemon`

## Critérios
- [ ] `scripts/install-launchagent.sh` executável
- [ ] Rodou sem erro
- [ ] `curl http://localhost:6737/status` retorna JSON
- [ ] LaunchAgent recarrega no boot
- [ ] Commit: `feat(aih): add launchagent for http api daemon`

---

# [AIH1-07] Dashboard TUI polish

**Est:** S | **Model:** pro (pleno) | **Branch:** feat/aih1-mvp

## User Story
Como usuário, quero um dashboard TUI bonito que mostra quotas em tempo real com cores e barras de progresso.

## Tarefas
1. Ler `server/dashboard.py` (114 linhas) e validar se funciona
2. Rodar: `uv run ai-usage-dashboard` — ver se renderiza
3. Melhorias (se necessário):
   - Barras de progresso coloridas (green < 70%, yellow 70-85%, red > 85%)
   - Tabela com provider/usage%/reset em colunas alinhadas
   - Footer com recommendation atual ("USE opencode_go" / "WAIT 15min" / "DELEGATE to glm_pro")
   - Refresh automático a cada 30s
   - Ctrl+C pra sair limpo
4. Testar com dados mockados (snapshot fake)
5. Commit: `feat(aih): polish dashboard tui with colored bars and recommendations`

## Critérios
- [ ] Dashboard renderiza sem erro
- [ ] Barras coloridas por threshold
- [ ] Recomendação no footer
- [ ] Ctrl+C sai limpo
- [ ] Commit: `feat(aih): polish dashboard tui with colored bars and recommendations`

---

# [AIH1-08] E2E smoke (rodar hub + chamar MCP tool)

**Est:** M | **Model:** qwen-3.8-preview (senior) | **Branch:** feat/aih1-mvp

## User Story
Como dev senior, quero validar E2E que o MCP server responde corretamente quando chamado por um client real, pra garantir que a integração funciona.

## Tarefas
1. Garantir que stories AIH1-01 a AIH1-07 estão mergeadas na branch
2. Criar `tests/e2e/test_mcp_smoke.py`:

```python
"""E2E smoke: spawn MCP server stdio, call each tool, validate response."""
import asyncio
import json
import sys
from pathlib import Path

async def call_mcp_tool(tool_name: str, args: dict = None) -> dict:
    """Spawn mcp_server via stdio, send tools/call, return result."""
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", "/Users/mini/ai-usage-hub",
        "python", "-m", "server.mcp_server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # handshake JSON-RPC initialize → tools/list → tools/call
    # (implementar protocol MCP mínimo)
    ...
    return result

async def main():
    # 1. initialize handshake
    # 2. List tools — deve ter 6+ tools
    tools = await call_mcp_tool("tools/list")
    assert "get_all_usage" in [t["name"] for t in tools]

    # 3. Call get_all_usage — deve retornar snapshots
    result = await call_mcp_tool("tools/call", {"name": "get_all_usage"})
    assert "providers" in result or "snapshots" in result

    # 4. Call get_recommendation
    rec = await call_mcp_tool("tools/call", {"name": "get_recommendation"})
    assert "action" in rec

    # 5. Call get_reset_schedule
    schedule = await call_mcp_tool("tools/call", {"name": "get_reset_schedule"})
    assert isinstance(schedule, list)

asyncio.run(main())
```

3. Rodar: `uv run pytest tests/e2e/ -v`
4. Se quebrar, documentar causa (provável: formato JSON-RPC MCP errado no teste, ou tool retorna schema diferente)
5. Adicionar `pytest.mark.e2e` marker + config `addopts = "-m 'not e2e'"` no pyproject pra E2E ser opt-in
6. Commit: `test(aih): add e2e smoke test for mcp server stdio`

## Critérios
- [ ] `tests/e2e/test_mcp_smoke.py` implementado
- [ ] Spawn do mcp_server funciona
- [ ] Handshake JSON-RPC inicial completo
- [ ] 4 tools chamadas com sucesso
- [ ] `uv run pytest tests/e2e/ -v` → 0 failures
- [ ] Commit: `test(aih): add e2e smoke test for mcp server stdio`

---

## Ordem de execução

```
Fase 1 (paralelo, flash=junior):
  AIH1-01  Testes unitários
  AIH1-03  README + .gitignore
  AIH1-06  LaunchAgent

Fase 2 (paralelo, pro=pleno):
  AIH1-02  forecast.py
  AIH1-04  Validar collectors reais
  AIH1-07  Dashboard polish

Fase 3 (qwen=senior):
  AIH1-05  Integrar MCP configs
  AIH1-08  E2E smoke
```

## Validação final

Depois das 8 stories:
```bash
cd ~/ai-usage-hub
uv run pytest 2>&1 | tail -5
uv run python -m server.mcp_server  # deve iniciar sem erro
curl http://localhost:6737/status  # deve retornar JSON
git log --oneline main..feat/aih1-mvp  # 8 commits
```

Reportar:
- Testes: total + passing
- Coverage
- Commits
- BLOCKEDs
- Quais collectors funcionaram contra API real
