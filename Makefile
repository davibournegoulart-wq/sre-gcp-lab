.PHONY: help secrets up down unit e2e test load k6-load chaos-latency chaos-error chaos-reset tf-plan sec-scan

help:
	@echo "SRE GCP Lab - Production SRE & Observability Commands"
	@echo "  make secrets       - Generate .env (CHAOS_TOKEN, GRAFANA_ADMIN_PASSWORD) and secrets/ once"
	@echo "  make up            - Launch entire stack (FastAPI, Prometheus, Alertmgr, Loki, Promtail, Grafana, Triage Bot)"
	@echo "  make down          - Stop and remove all containers"
	@echo "  make test          - Run API health checks and metrics probes"
	@echo "  make load          - Run lightweight continuous traffic curl generator"
	@echo "  make k6-load       - Run declarative k6 performance test with SLO assertion thresholds"
	@echo "  make chaos-latency - Inject artificial latency (1500ms) to trigger HighP95Latency alert"
	@echo "  make chaos-error   - Inject 25% HTTP 500 error rate to trigger FastErrorBudgetBurn alert"
	@echo "  make chaos-reset   - Reset chaos flags back to healthy zero baseline"
	@echo "  make unit          - Run security regression unit tests (API + triage bot)"
	@echo "  make e2e           - Run browser tests (CSP, XSS, token, mobile layout) against the stack"
	@echo "  make sec-scan      - Run security audit on containers and secrets"
	@echo "  make tf-plan       - Run Terraform formatting, validation and plan"

# Chaos calls need the token from .env; never hardcode it here.
CHAOS_TOKEN = $(shell sed -n 's/^CHAOS_TOKEN=//p' .env 2>/dev/null)
CHAOS_CURL = curl -s -X POST -H "X-Chaos-Token: $(CHAOS_TOKEN)"

secrets:
	@mkdir -p secrets
	@[ -f .env ] || { printf 'CHAOS_TOKEN=%s\nGRAFANA_ADMIN_PASSWORD=%s\nGEMINI_API_KEY=\nSLACK_WEBHOOK_URL=\nDISCORD_WEBHOOK_URL=\n' \
		"$$(openssl rand -hex 24)" "$$(openssl rand -base64 24 | tr -d '/+=')" > .env && chmod 600 .env && echo "Created .env"; }
	@[ -f secrets/alert_webhook_token ] || { openssl rand -hex 32 > secrets/alert_webhook_token && chmod 644 secrets/alert_webhook_token && echo "Created secrets/alert_webhook_token"; }
	@echo "Secrets ready. Grafana admin password is in .env (GRAFANA_ADMIN_PASSWORD)."

up: secrets
	docker compose up -d
	@echo "\nAll services launched successfully:"
	@echo "  - FastAPI App:       http://localhost:8090 (docs at /docs)"
	@echo "  - Prometheus:        http://localhost:9090"
	@echo "  - Alertmanager:      http://localhost:9093"
	@echo "  - Grafana (Loki+Prom): http://localhost:3030 (admin / password in .env)"
	@echo "  - AI Triage Bot:     http://localhost:5001"
	@echo "  - Loki Log Engine:   http://localhost:3105"

down:
	docker compose down -v

test:
	@echo "Testing API health..."
	@curl -s http://localhost:8090/healthz | grep "healthy" && echo " API Health OK"
	@echo "Testing Prometheus metrics endpoint..."
	@curl -s http://localhost:8090/metrics | grep "http_requests_total" && echo " Prometheus Metrics OK"
	@echo "Testing AI Triage Bot health..."
	@curl -s http://localhost:5001/healthz | grep "ok" && echo " AI Triage Bot OK"

load:
	@echo "Generating traffic on API (Ctrl+C to stop)..."
	@while true; do \
		curl -s http://localhost:8090/api/v1/items > /dev/null; \
		curl -s http://localhost:8090/api/v1/items/7 > /dev/null; \
		sleep 0.2; \
	done

k6-load:
	@echo "Running k6 SLO verification test container..."
	docker run --rm -i --network sre-gcp-lab_sre-network -e API_URL=http://api:8000 grafana/k6 run - < tests/k6-load.js

chaos-latency:
	@echo "Injecting 1500ms artificial latency..."
	@$(CHAOS_CURL) "http://localhost:8090/chaos/inject-latency?ms=1500"
	@echo "\n Latency injected. Monitor Grafana Latency Percentiles panel."

chaos-error:
	@echo "Injecting 25% 500 internal server error rate..."
	@$(CHAOS_CURL) "http://localhost:8090/chaos/inject-error?rate=0.25"
	@echo "\n Errors injected. Monitor Alertmanager FastErrorBudgetBurn & AI Triage Bot output."

chaos-reset:
	@echo "Resetting chaos injections..."
	@$(CHAOS_CURL) http://localhost:8090/chaos/reset
	@echo "\n All systems returned to normal operational baseline."

unit:
	docker run --rm -v "$$PWD:/w" -w /w python:3.11-slim sh -c "pip install -q -r app/requirements.txt -r triage-bot/requirements.txt pytest httpx && python -m pytest -q tests/unit"

# Browser tests against the running stack (joins its network, no host ports needed).
e2e:
	docker run --rm --network sre-gcp-lab_sre-network -v "$$PWD:/w" -w /w mcr.microsoft.com/playwright/python:v1.49.0-noble \
		sh -c "pip install -q --break-system-packages pytest playwright==1.49.0 && python -m pytest -q tests/e2e"

sec-scan:
	@echo "Auditing repository for secrets, credentials and security standards..."
	@python3 scripts/security-check.py

tf-plan:
	cd infra/terraform && terraform init -backend=false && terraform validate && terraform fmt -check
