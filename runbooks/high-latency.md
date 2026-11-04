# Runbook: High P95 Latency (>300ms)

## 1. Metadata
- **Alert Name:** `HighP95Latency`
- **Severity:** P2 (Major)
- **SLO Impact:** Breaching the 300ms 95th percentile latency threshold.
- **Service Affected:** `sre-api`

---

## 2. Immediate Triage
1. Open Grafana **Latency Percentiles (p50 / p95 / p99)** panel.
2. Identify which specific endpoints are slow:
   ```bash
   # Filter Prometheus for request durations by handler
   histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, handler))
   ```
3. Check current chaos latency settings:
   ```bash
   curl -s http://localhost:8000/chaos/status
   ```
   If latency was injected:
   ```bash
   curl -X POST http://localhost:8000/chaos/reset
   ```

---

## 3. Investigation Checklist
- **CPU Throttling:** Check if pods are hitting CPU limits:
  ```bash
  kubectl top pods -l app=sre-api
  ```
- **HPA Status:** Verify if Horizontal Pod Autoscaler has scaled out:
  ```bash
  kubectl get hpa sre-api-hpa
  ```
- **Database Locks / Slow Queries:** Check active connections on Cloud SQL.

---

## 4. Remediation
- If traffic surged beyond HPA reaction time, manually scale deployment:
  ```bash
  kubectl scale deployment sre-api --replicas=6
  ```
- If a dependency is hanging, consider enabling circuit breaker pattern or reducing socket timeout.
