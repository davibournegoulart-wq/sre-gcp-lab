# Post-Mortem: Incident INC-2026-11-04-01 (Bilingual / Bilíngue)

---

## English Version

### Incident Overview
- **Incident ID:** INC-2026-11-04-01
- **Date:** 2026-11-04
- **Incident Commander:** Davi Goulart Martins (SRE)
- **Severity Level:** P1 - Critical
- **Impacted Services:** `sre-api` (FastAPI Production Backend), Cloud SQL (PostgreSQL)
- **Duration:** 18 minutes (Detection to Mitigation)
- **SLO Impact:** 
  - Monthly Availability Error Budget Consumed: **3.8%**
  - Total HTTP 5xx errors served: 1,420 requests (4.1% of window traffic)
  - P95 Latency Peak: 1,450 ms (SLO target: <300 ms)

---

### Executive Summary
At 14:12 UTC, Prometheus triggered `FastErrorBudgetBurn` alert indicating a 14.4x burn rate on the `sre-api` service. The AI Incident Triage Bot ingested the alert payload, performed root cause correlation against container logs, and pinpointed connection pool starvation on Cloud SQL due to unindexed sequential scans in `/api/v1/items`. SRE intervened, executed the high-error-rate runbook, applied transient connection shedding, and restarted the deployment with tuned pool parameters. Availability returned to 100% at 14:30 UTC.

---

### Incident Timeline (UTC)
- **14:10:00** — Background batch job triggered multiple concurrent reads on `/api/v1/items` without query limits.
- **14:11:30** — Cloud SQL connection pool exhausted (max_connections=100 reached). Incoming web requests began queuing.
- **14:12:05** — Request timeout threshold reached (5s). FastAPI returned HTTP 500/504 errors.
- **14:12:45** — Prometheus detected 5m error rate > 7.2%. Alert `FastErrorBudgetBurn` fired.
- **14:13:00** — Alertmanager dispatched webhook to `sre-triage-bot`.
- **14:13:10** — AI Triage Bot generated RCA report in Slack `#sre-warroom` identifying database pool starvation and linking runbook `high-error-rate.md`.
- **14:14:30** — SRE acknowledged alert, followed runbook, and terminated hanging connection locks on PostgreSQL.
- **14:18:00** — SRE scaled deployment to 4 replicas and updated connection pool recycling timeout to 30s.
- **14:26:00** — Error rate dropped to 0.02%. P95 latency normalized to 110 ms.
- **14:30:00** — Alert marked RESOLVED in Alertmanager. Incident closed.

---

### Root Cause Analysis (5 Whys)
1. **Why did users receive HTTP 500 errors?**
   Because API requests to `/api/v1/items` timed out waiting for an available PostgreSQL connection.
2. **Why were no connections available?**
   The connection pool of 20 connections per pod was fully saturated with long-running transactions.
3. **Why were transactions running so long?**
   A scheduled analytics query executed an unindexed full table scan during peak web traffic.
4. **Why was the query unindexed?**
   The recent schema migration in release `v1.2.4` omitted the composite index on `(created_at, status)`.
5. **Why was this not caught in staging?**
   The staging database seed data was small (<100 rows), masking sequential table scan latency.

---

### What Went Well
- Multi-window burn rate alerts caught the error budget depletion within 1 minute of customer impact.
- AI Triage Bot accurately correlated the Alertmanager alert with database pool exhaustion, reducing MTTA/MTTD to under 2 minutes.
- Rolling update and runbook procedures were executed smoothly without requiring cluster downtime.

### What Went Poorly
- Staging test suite lacked synthetic large dataset performance tests.
- Connection timeout on database client was set too high (10s instead of 2s fast-fail).

### Preventative Action Items
| Action Item | Type | Owner | Priority | Status |
| :--- | :--- | :--- | :--- | :--- |
| Add composite index on `(created_at, status)` via Terraform/Liquibase | Prevent | Davi Martins | P0 | Done |
| Set strict database statement timeout to 2500ms | Mitigate | Davi Martins | P1 | Done |
| Add synthetic load testing with k6 in GitHub Actions CI | Detect | Davi Martins | P1 | In Progress |

---
---

## Versão em Português

### Resumo Executivo
Às 14:12 UTC, o Prometheus disparou o alerta crítico `FastErrorBudgetBurn` (taxa de consumo do error budget de 14.4x). O Bot de Triagem IA correlacionou o alerta com os logs da aplicação e identificou esgotamento do pool de conexões do Cloud SQL devido a varreduras sequenciais sem índice na rota `/api/v1/items`. A equipe de SRE seguiu o runbook de alta taxa de erro, cancelou conexões presas e ajustou os parâmetros de pool e timeout. O serviço foi normalizado às 14:30 UTC consumindo 3.8% do Error Budget mensal.

### Linha do Tempo
- **14:10** — Carga concorrente na rota `/api/v1/items` sem índice provocou saturação das conexões do banco.
- **14:12** — Requisições atingiram timeout e geraram erros HTTP 500.
- **14:12** — Prometheus disparou alerta de queima rápida de error budget.
- **14:13** — Bot de IA postou hipótese de causa raiz no Slack com o link do runbook correspondente.
- **14:18** — SRE aplicou mitigação, liberou conexões e reiniciou pods com novos limites de timeout.
- **14:30** — Métricas normalizadas e incidente encerrado sem perda de dados.

