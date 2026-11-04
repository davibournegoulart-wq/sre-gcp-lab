.PHONY: help up down test load chaos-latency chaos-error chaos-reset tf-plan tf-apply

help:
	@echo "SRE GCP Lab - Automation & Incident Simulation Targets"
	@echo "  make up            - Launch entire observability stack locally with Docker Compose"
	@echo "  make down          - Stop and clean up local containers"
	@echo "  make test          - Run basic API health and metrics checks"
	@echo "  make load          - Send continuous HTTP load to generate realistic metrics"
	@echo "  make chaos-latency - Inject artificial latency (1500ms) to trigger HighP95Latency alert"
	@echo "  make chaos-error   - Inject 25% HTTP 500 error rate to trigger FastErrorBudgetBurn alert"
	@echo "  make chaos-reset   - Reset chaos flags back to healthy zero baseline"
	@echo "  make tf-plan       - Run Terraform formatting, validation and plan"

up:
	docker compose up -d --build
	@echo "Stack is running:"
	@echo "  - FastAPI App:       http://localhost:8000 (docs at /docs)"
	@echo "  - Prometheus:        http://localhost:9090"
	@echo "  - Alertmanager:      http://localhost:9093"
	@echo "  - Grafana:           http://localhost:3000 (admin / admin)"
	@echo "  - AI Triage Bot:     http://localhost:5001"

down:
	docker compose down -v

test:
	@echo "Testing API health..."
	curl -s http://localhost:8000/healthz | grep "healthy" && echo "✅ API Health OK"
	@echo "Testing Prometheus metrics endpoint..."
	curl -s http://localhost:8000/metrics | grep "http_requests_total" && echo "✅ Metrics OK"

load:
	@echo "Generating traffic on API (Ctrl+C to stop)..."
	@while true; do \
		curl -s http://localhost:8000/api/v1/items > /dev/null; \
		curl -s http://localhost:8000/api/v1/items/42 > /dev/null; \
		sleep 0.2; \
	done

chaos-latency:
	@echo "Injecting 1500ms artificial latency..."
	curl -X POST "http://localhost:8000/chaos/inject-latency?delay_seconds=1.5"
	@echo "\nLatency injected. Check Grafana Latency Percentiles panel."

chaos-error:
	@echo "Injecting 25% 500 internal server error rate..."
	curl -X POST "http://localhost:8000/chaos/inject-error?rate=0.25"
	@echo "\nErrors injected. Monitor Prometheus alert FastErrorBudgetBurn & AI Triage Bot."

chaos-reset:
	@echo "Resetting chaos injections..."
	curl -X POST http://localhost:8000/chaos/reset
	@echo "\nAll systems returned to normal operational baseline."

tf-plan:
	cd infra/terraform && terraform init -backend=false && terraform validate && terraform fmt -check
