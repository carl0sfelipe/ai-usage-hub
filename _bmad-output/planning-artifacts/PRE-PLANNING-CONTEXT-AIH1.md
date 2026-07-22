# PRE-PLANNING-CONTEXT — EPIC-AIH1: AI Usage Hub MVP Finalization

> **Fonte de verdade anti-alucinação.** Projeto `~/ai-usage-hub`. Tudo verificado em 2026-07-22.

## 1. ESTADO ATUAL (verificado)

**Repo:** `/Users/mini/ai-usage-hub` (Python 3.12+, uv, 1 commit `1d82466`)

### 1.1 O que JÁ existe (NÃO recriar)

**Collectors (3/5 ativos):**
- `collectors/base.py` (65 linhas) — `LimitWindow`, `ProviderSnapshot` dataclasses + `BaseCollector` Protocol
- `collectors/opencode_go.py` (98 linhas) — HTTP GET /usage, 3 windows (5h/semanal/mensal), usa Agent Vault
- `collectors/glm_pro.py` (105 linhas) — HTTP api.z.ai
- `collectors/claude_pro.py` (112 linhas) — Keychain (sem OAuth flow)
- `collectors/vault.py` (17 linhas) — `get_vault_credential()` via `agent-vault` CLI
- `collectors/__init__.py` (13 linhas) — exports
- ❌ `collectors/kimi.py` — não existe (PRD diz optional, `enabled: false`)
- ❌ `collectors/gemini.py` — não existe (optional)

**Engine:**
- `server/cache.py` (134 linhas) — SQLite em `~/.ai-usage-hub/cache.db`, TTL 5min, stale-while-revalidate, tabela `usage_history` pra burn rate
- `server/scheduler.py` (135 linhas) — `Recommendation` dataclass + lógica use/wait/delegate/consolidate
- `server/env_loader.py` (22 linhas) — carrega .env
- ❌ `server/forecast.py` — **NÃO existe** (mencionado na architecture mas não implementado)
- `server/main.py` (19 linhas) — entry CLI

**Interfaces:**
- `server/mcp_server.py` (191 linhas) — MCP stdio com Server + 6 tools (`get_all_usage`, `get_provider_usage`, `get_recommendation`, `get_reset_schedule`, `should_consolidate`, `get_spend_today`)
- `server/http_api.py` (99 linhas) — aiohttp `:6737` GET /status
- `server/dashboard.py` (114 linhas) — TUI com rich

**Config:**
- `config.yaml` — 5 providers (3 enabled), cache TTL 300s, scheduler thresholds
- `pyproject.toml` — httpx, mcp>=1.0, rich, aiohttp, pyyaml

### 1.2 O que FALTA (escopo do EPIC-AIH1)

1. **Zero testes** — `tests/` vazio. Cobertura 0%.
2. **`server/forecast.py` ausente** — burn rate e ETA até exaustão (mencionado na arch)
3. **Sem README** — projeto não tem documentação de uso
4. **Sem .gitignore** — `.venv/`, `__pycache__/`, `cache.db` não ignorados
5. **Sem validação real** — rodar contra APIs reais e ver se funciona
6. **Sem integração MCP configurada** — não tá registrada no opencode/hermes/zcode
7. **`claude_pro.py` sem OAuth Keychain real** — provavelmente placeholder
8. **Sem LaunchAgent** — não inicia no boot

### 1.3 Ferramentas disponíveis

- `uv` em PATH
- Python 3.12+
- `agent-vault` CLI em `/Users/mini/.agent-vault/server` (LaunchAgent `com.agent-vault.server`)
- Agent Vault credenciais acessíveis via `agent-vault vault credential get <KEY> --vault orbe-main`

## 2. ESCOPO DO EPIC-AIH1 (8 stories)

| ID | Título | Modelo ideal | Est. |
|----|--------|--------------|------|
| AIH1-01 | Testes unitários (collectors com mocks + scheduler) | flash (junior) | M |
| AIH1-02 | `server/forecast.py` (burn rate + ETA) | pro (pleno) | M |
| AIH1-03 | README + .gitignore + docs de uso | flash (junior) | S |
| AIH1-04 | Validar collectors reais (rodar contra APIs, fix bugs) | pro (pleno) | M |
| AIH1-05 | Integrar MCP no opencode + hermes + zcode config | flash (junior) | S |
| AIH1-06 | LaunchAgent para daemon | flash (junior) | XS |
| AIH1-07 | Dashboard TUI polish + teste visual | pro (pleno) | S |
| AIH1-08 | E2E smoke (rodar hub + chamar MCP tool) | qwen (senior) | M |

## 3. REGRAS ANTI-ALUCINAÇÃO

1. **NUNCA** inventar assinaturas — tudo tá em `collectors/base.py`, `server/cache.py`, etc.
2. **NUNCA** comitar `cache.db` ou `.env`
3. **NUNCA** expor API keys (Agent Vault resolve)
4. **NUNCA** quebrar o MCP server (testar com `uv run python -m server.mcp_server` antes de commit)
5. **SEMPRE** rodar `uv run pytest` (quando existir) e manter 0 failures
6. **SEMPRE** commit Conventional: `feat(aih): ...` ou `test(aih): ...` ou `docs(aih): ...`
7. **SEMPRE** validar em ambiente real antes de declarar sucesso

## 4. FORMA DE EXECUÇÃO

- **Branch:** `feat/aih1-mvp` (criar do `main` no repo `~/ai-usage-hub`)
- **Workflow:** opencode `--auto` disparado por mim (ZCode Tech Lead)
- **Modelos:**
  - flash = dev junior (tarefas repetitivas: testes, docs, configs)
  - pro = dev pleno (lógica complexa: forecast, debug API real)
  - qwen-3.8-preview = senior (orquestração E2E, decisions)
- **Eu (ZCode)**: Tech Lead (poucos tokens — só planejamento e review)

## 5. AMBIENTE

- Mac Mini M4 16GB
- Python 3.12+ via uv
- Agent Vault rodando (LaunchAgent `com.agent-vault.server`)
- Credenciais via `agent-vault vault credential get <KEY> --vault orbe-main`
- Porta 6737 livre (HTTP API)

## 6. VALIDAÇÃO POR STORY

Cada story termina com:
```bash
cd /Users/mini/ai-usage-hub
uv run pytest 2>&1 | tail -5  # quando existir
uv run python -c "from server.mcp_server import build_collectors; print('OK')"  # import check
git add -A && git commit -m "..."
```

## 7. Escape hatch (todas as stories)

```
ESCAPE HATCH: Se travar 3x ou 5min: PARE → BLOCKED.md → pule → continue.
```
