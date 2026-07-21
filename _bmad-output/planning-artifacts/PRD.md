# PRD — AI Usage Hub

> **Status:** Accepted
> **Data:** 2026-07-20
> **PM:** John (BMAD)
> **Projeto:** ~/ai-usage-hub

---

## 1. Visão

Hub local que monitora limites, quotas e resets de subscrições IA (Claude Pro, GLM Pro, OpenCode Go, Kimi, Gemini Pro), expondo dados via **MCP server** para qualquer IA decidir qual provider usar, quando esperar reset, e quando consolidar contexto em memória.

**Dashboard:** terminal (TUI) + endpoint HTTP JSON.
**MCP:** tools que qualquer agent (Hermes, Claude Code, OpenCode, zcode) pode chamar.

---

## 2. Problema

- GLM Pro estoura limite no meio de tarefas complexas → trabalho perdido
- Sem visibilidade unificada de quotas → IA não sabe quando delegar ou esperar
- Sem signal de "fim de sessão" → contexto não é consolidado em memória
- Cada provider tem janela de reset diferente (5h, semanal, mensal) → impossível trackear mentalmente

---

## 3. Solução

### 3.1 Collectors (1 por provider)

| Provider | Fonte de dados | Janelas |
|----------|---------------|---------|
| OpenCode Go | GET /zen/go/v1/usage (API key) | 5h ($12), semanal ($30), mensal ($60) |
| GLM Pro | GET api.z.ai/api/monitor/usage/quota/limit (API key) | 5h, 7d |
| Claude Pro | GET api.anthropic.com/api/oauth/usage (OAuth Keychain) | 5h, semanal |
| Kimi | CLI `kimi /usage` + GET api.moonshot.ai/v1/users/me/balance | semanal, 5h |
| Gemini Pro | gRPC local Antigravity Language Server | 5h, semanal |

### 3.2 MCP Server (tools expostas)

| Tool | Descrição |
|------|-----------|
| `get_all_usage` | Snapshot de todos os providers (usage%, remaining, reset_at) |
| `get_provider_usage` | Detalhe de 1 provider |
| `get_recommendation` | Qual provider usar agora (lógica de delegação) |
| `get_reset_schedule` | Próximos resets ordenados por tempo |
| `should_consolidate` | Se sessão atual deve consolidar contexto em memória |
| `get_spend_today` | Gasto acumulado hoje (USD) |

### 3.3 Dashboard

- TUI (rich/textual) com barras de progresso por provider
- HTTP endpoint `GET /status` retornando JSON (para scripts/cron)
- Atualização a cada 5 min (stale-while-revalidate)

### 3.4 Lógica de Recomendação

```
SE provider_principal.usage >= 85% E reset <= 30min → "ESPERAR reset"
SE provider_principal.usage >= 85% E reset > 30min → "DELEGAR para {alternativa}"
SE todos providers > 70% → "CONSOLIDAR contexto em memória e pausar"
SE provider_principal.usage < 50% → "USAR provider_principal"
```

---

## 4. Requisitos Não-Funcionais

- 100% local (Mac mini M4, 16GB) — zero cloud
- Python 3.12+ (uv)
- MCP via stdio (compatível com Hermes, Claude Code, OpenCode)
- Latência < 2s para get_all_usage (cache local)
- Sem dependência de Docker
- Launchd para rodar como daemon

---

## 5. Out of Scope (MVP)

- ❌ UI web (React/Next.js) — TUI + JSON basta
- ❌ Histórico de longo prazo (gráficos semanais)
- ❌ Multi-máquina / sync
- ❌ Alertas push (WhatsApp/Telegram) — fase 2
- ❌ Auto-switching de provider (só recomendação)

---

## 6. KPIs

- Zero interrupções de fluxo por limite estourado (vs ~3/semana atualmente)
- 100% das sessões longas (>2h) terminam com consolidação de memória
- Tempo médio de consulta MCP < 500ms
