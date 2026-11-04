.PHONY: help up down test load k6-load chaos-latency chaos-error chaos-reset tf-plan sec-scan

help:
	@echo "SRE GCP Lab - Production SRE & Observability Commands"
	@echo "  make up            - Launch entire stack (FastAPI, Prometheus, Alertmgr, Loki, Promtail, Grafana, Triage Bot)"
	@echo "  make down          - Stop and remove all containers"
	@echo "  make test          - Run API health checks and metrics probes"
	@echo "  make load          - Run lightweight continuous traffic curl generator"
	@echo "  make k6-load       - Run declarative k6 performance test with SLO assertion thresholds"
	@echo "  make chaos-latency - Inject artificial latency (1500ms) to trigger HighP95Latency alert"
	@echo "  make chaos-error   - Inject 25% HTTP 500 error rate to trigger FastErrorBudgetBurn alert"
	@echo "  make chaos-reset   - Reset chaos flags back to healthy zero baseline"
	@echo "  make sec-scan      - Run security audit on containers and secrets"
	@echo "  make tf-plan       - Run Terraform formatting, validation and plan"

up:
	docker compose up -d
	@echo "\nAll services launched successfully:"
	@echo "  - FastAPI App:       http://localhost:8090 (docs at /docs)"
	@echo "  - Prometheus:        http://localhost:9090"
	@echo "  - Alertmanager:      http://localhost:9093"
	@echo "  - Grafana (Loki+Prom): http://localhost:3030 (admin / admin)"
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
	@curl -X POST "http://localhost:8090/chaos/inject-latency?ms=1500"
	@echo "\n Latency injected. Monitor Grafana Latency Percentiles panel."

chaos-error:
	@echo "Injecting 25% 500 internal server error rate..."
	@curl -X POST "http://localhost:8090/chaos/inject-error?rate=0.25"
	@echo "\n Errors injected. Monitor Alertmanager FastErrorBudgetBurn & AI Triage Bot output."

chaos-reset:
	@echo "Resetting chaos injections..."
	@curl -X POST http://localhost:8090/chaos/reset
	@echo "\n All systems returned to normal operational baseline."

sec-scan:
	@echo "Auditing repository for secrets, credentials and security standards..."
	@python3 scripts/security-check.py

tf-plan:
	cd infra/terraform && terraform init -backend=false && terraform validate && terraform fmt -check
