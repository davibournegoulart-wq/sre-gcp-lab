# Production SRE & Observability Lab on Google Cloud (GCP)

[![CI/CD Pipeline](https://github.com/davibournegoulart-wq/sre-gcp-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/davibournegoulart-wq/sre-gcp-lab/actions)
[![Terraform](https://img.shields.io/badge/IaC-Terraform_1.6+-7B42BC?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![GCP GKE Autopilot](https://img.shields.io/badge/Orchestration-GKE_Autopilot-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/kubernetes-engine)
[![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Observability-Grafana_10-F46800?logo=grafana&logoColor=white)](https://grafana.com/)
[![Python](https://img.shields.io/badge/Backend-FastAPI_3.11-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **End-to-End Site Reliability Engineering (SRE) implementation** demonstrating production-grade reliability practices: Infrastructure as Code (Terraform), SLO/Error Budget multi-window alerting, automated chaos engineering injection, and an **AI Incident Triage Bot (Gemini / Claude)** for rapid Root Cause Analysis (RCA).

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client_Traffic [Traffic & Chaos Simulation]
        Users[User Traffic / k6 Load Generator]
        Chaos[Chaos Injection API /chaos/*]
    end

    subgraph Kubernetes_Cluster [GCP GKE Autopilot]
        Ingress[Service / Ingress Router]
        API1[Pod: FastAPI Replicas]
        API2[Pod: FastAPI Replicas]
        HPA[Horizontal Pod Autoscaler]
    end

    subgraph Persistence [Google Cloud Managed Services]
        CloudSQL[(Cloud SQL PostgreSQL)]
        GCS[(Cloud Storage Assets)]
    end

    subgraph Observability_Stack [SRE Telemetry & Alerting]
        Prom[Prometheus Metrics Scraper]
        Grafana[Grafana SLO Dashboard]
        Alertmgr[Alertmanager Multi-window Burn Rate]
    end

    subgraph AI_AIOps [Intelligent Incident Response]
        TriageBot[SRE AI Triage Bot]
        LLM[Google Gemini / Claude API]
        Slack[Slack / Discord War Room Alert Card]
    end

    Users --> Ingress
    Chaos --> Ingress
    Ingress --> API1
    Ingress --> API2
    API1 -.-> HPA
    API1 --> CloudSQL
    API1 --> GCS

    API1 -- /metrics --> Prom
    Prom --> Grafana
    Prom -- Fast Burn / Latency Breach --> Alertmgr
    Alertmgr -- Webhook --> TriageBot
    TriageBot -- Context Logs & Alert Payload --> LLM
    LLM -- Structured RCA & Runbook Recommendation --> TriageBot
    TriageBot --> Slack
```

---

## Core SRE Principles Implemented

### 1. Service Level Objectives (SLOs) & Error Budgets
Based on the **Google SRE Workbook (Chapter 5: Alerting on SLOs)**, standard threshold alerting (like arbitrary CPU spikes) leads to alert fatigue. This lab implements **Multi-Window Multi-Burn-Rate Alerts**:

| Metric | Target | Monthly Budget | Fast Burn (Page - 14.4x) | Medium Burn (Ticket - 6x) |
| :--- | :--- | :--- | :--- | :--- |
| **Availability SLI** | 99.5% | 0.5% (0.005) | Consumes 2% in 1 hour (1h + 5m window) | Consumes 5% in 6 hours (6h + 30m window) |
| **Latency SLI** | 95% < 300 ms | 5.0% | P95 latency > 300ms for > 3 minutes | Continuous degradation tracker |

### 2. Built-in Chaos Engineering & Fault Injection
The FastAPI application features live chaos endpoints to simulate real outages without altering application code. They are enabled only when `CHAOS_ENABLED=true` (local Compose; the k8s manifest keeps them off) and every call needs the `X-Chaos-Token` header from `.env` — the `make chaos-*` targets send it for you:
- `POST /chaos/inject-latency?ms=1500` — Injects artificial latency (0–5000 ms) to trigger `HighP95Latency`.
- `POST /chaos/inject-error?rate=0.25` — Returns HTTP 500 on 25% of requests to burn the Error Budget and trip `FastErrorBudgetBurn`.
- `POST /chaos/reset` — Instantly restores healthy baseline behavior.

### 3. AI Incident Triage Bot (AIOps)
When Alertmanager fires, it dispatches an asynchronous webhook to the Python triage bot (`triage-bot/`):
1. Ingests Alertmanager JSON payload and container log traces.
2. Prompts Gemini 1.5 Flash / Claude to synthesize:
   - **Root Cause Hypothesis**
   - **Blast Radius & SLO Impact**
   - **Recommended Mitigation Steps** (with precise `kubectl` / rollback commands)
   - Links the designated **Runbook URL**.
3. Posts an actionable triage card into the War Room (Slack/Discord) and logs the event to disk for post-mortem auditing.

---

## Repository Structure

```
sre-gcp-lab/
├── app/                      # Production FastAPI backend with Prometheus instrumentation & chaos APIs
│   ├── Dockerfile            # Multi-stage secure Docker build (non-root user)
│   ├── requirements.txt      # Python dependencies
│   └── main.py               # Application logic, health checks & telemetry
├── infra/terraform/          # Reusable Terraform IaC for Google Cloud
│   ├── main.tf               # VPC, GKE Autopilot, Cloud SQL (db-f1-micro), GCS, Artifact Registry
│   ├── variables.tf          # Parameterized inputs (region, project_id, environment)
│   └── outputs.tf            # Cluster endpoints, bucket URLs, connection strings
├── k8s/                      # Kubernetes production manifests
│   ├── deployment.yaml       # RollingUpdate, resource requests/limits, probes, scrape annotations
│   ├── service.yaml          # ClusterIP service
│   └── hpa.yaml              # Horizontal Pod Autoscaler targeting 75% CPU
├── observability/            # Monitoring & Alerting configuration
│   ├── prometheus/           # Prometheus scraping & Multi-window SLO burn rate alert rules
│   ├── alertmanager/         # Alert routing to AI Triage Bot
│   └── grafana/              # Pre-provisioned SLO and Golden Signals dashboard
├── triage-bot/               # AI-powered alert triage microservice (FastAPI + LLMs)
├── runbooks/                 # Standard Operating Procedures (SOPs) for on-call responders
│   ├── high-error-rate.md
│   ├── high-latency.md
│   └── api-down.md
├── postmortems/              # Real blameless incident reports (Bilingual: English & Portuguese)
│   └── INC-2026-11-04-database-timeout.md
├── .github/workflows/        # GitHub Actions CI/CD (lint, terraform validation, Trivy vulnerability scan)
├── docker-compose.yml        # 1-Click local reproduction stack
└── Makefile                  # Operational command automation
```

---

## 1-Minute Quickstart (Run Entire Stack Locally)

You can spin up the full production observability environment locally using Docker Compose without needing active GCP credentials:

```bash
# Clone the repository
git clone https://github.com/davibournegoulart-wq/sre-gcp-lab.git
cd sre-gcp-lab

# Generates .env and secrets/ (random tokens, gitignored), then starts the stack
make up
```

### Access Services:
- **FastAPI API & Docs:** `http://localhost:8090/docs`
- **Prometheus UI:** `http://localhost:9090`
- **Alertmanager:** `http://localhost:9093`
- **Grafana Dashboard (SLO + Loki):** `http://localhost:3030` (User: `admin` | Password: `GRAFANA_ADMIN_PASSWORD` in `.env`)
- **AI Triage Bot:** `http://localhost:5001/healthz`
- **Loki Log Engine:** `http://localhost:3105`

---

## Live Incident Simulation & Verification

Follow this script to verify the end-to-end incident lifecycle:

```bash
# 1. Start continuous background traffic
make load &

# 2. Inject Chaos: trip 25% HTTP 500 error rate
make chaos-error

# 3. Watch Grafana:
# - Error rate spikes to 25%
# - Availability drops below 99.5%
# - Burn Rate exceeds 14.4x

# 4. Check Alertmanager (http://localhost:9093):
# - Alert 'FastErrorBudgetBurn' transitions from PENDING to FIRING

# 5. Check AI Triage Bot output:
docker compose logs -f triage-bot
# Notice the automated RCA diagnostic card and remediation actions generated

# 6. Resolve Incident:
make chaos-reset

# 7. Observe metrics return to normal in Grafana and alert marks RESOLVED
```

### Security Posture
- Every port is bound to `127.0.0.1`; nothing is reachable from the LAN.
- Mission Control ships a strict CSP (`script-src 'self'`), self-hosted fonts and no third-party scripts; API data reaches the page only through `textContent`.
- Alertmanager authenticates to the triage bot with a Bearer token (`secrets/alert_webhook_token`); the bot caps payload size and LLM calls per day.
- Promtail reads container logs through a read-only Docker socket proxy, never the raw socket.
- `make sec-scan` checks the tree **and git history** for leaked credentials plus these settings; `make unit` runs the security regression tests.

---

## Cloud Deployment (Google Cloud Platform)

### Prerequisites
- Google Cloud SDK (`gcloud` CLI) installed and authenticated
- Terraform `>= 1.6.0`

### Provisioning Infrastructure
```bash
cd infra/terraform
terraform init
# Control plane is private by default: list the CIDRs allowed to reach it.
terraform plan -var="project_id=YOUR_GCP_PROJECT_ID" -var='master_authorized_cidrs=[{cidr="203.0.113.10/32",name="home"}]'
terraform apply -var="project_id=YOUR_GCP_PROJECT_ID" -var='master_authorized_cidrs=[{cidr="203.0.113.10/32",name="home"}]'
```

---

## Incident Management & Post-Mortems
- Check our [Bilingual Post-Mortem INC-2026-11-04](postmortems/INC-2026-11-04-database-timeout.md) for a real example of root-cause analysis, 5-Whys methodology, and preventative action tracking.
- Follow operational SOPs in [`runbooks/`](runbooks/).

---

## License
Distributed under the MIT License. See `LICENSE` for more information.

