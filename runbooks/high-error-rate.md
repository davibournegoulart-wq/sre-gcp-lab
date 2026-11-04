# Runbook: High Error Rate (5xx) & Error Budget Burn

## 1. Metadata
- **Alert Name:** `FastErrorBudgetBurn` / `MediumErrorBudgetBurn`
- **Severity:** P1 (Critical) if Fast Burn (14.4x); P2 (Major) if Medium Burn (6x)
- **SLO Impact:** Target 99.5% availability. Fast burn consumes 2% of monthly budget within 1 hour.
- **Service Affected:** `sre-api` (FastAPI backend)

---

## 2. Initial Triage (0 - 5 Minutes)
1. **Acknowledge Alert:** Post in `#incident-warroom` on Slack/Discord:
   > "Acknowledged `FastErrorBudgetBurn`. Incident commander: Davi Martins. Investigating API 5xx spikes."
2. **Check Dashboard:**
   - Open Grafana: `http://localhost:3000` or Cloud Monitoring console.
   - Look at **Error Budget Remaining** and **QPS by Route**.
3. **Verify App Health:**
   ```bash
   curl -i http://localhost:8000/healthz
   curl -i http://localhost:8000/ready
   ```

---

## 3. Diagnostic Steps (Root Cause Identification)
1. **Check Pod Logs for 500 Exceptions:**
   ```bash
   kubectl logs -l app=sre-api --tail=100 | grep -E "ERROR|CRITICAL|Traceback"
   ```
2. **Inspect Chaos Injection State:**
   - Check if an intentional chaos simulation is active:
   ```bash
   curl -s http://localhost:8000/chaos/status
   ```
   - If `error_rate > 0`, reset immediately:
   ```bash
   curl -X POST http://localhost:8000/chaos/reset
   ```
3. **Check Cloud SQL / Database Connectivity:**
   ```bash
   kubectl exec -it deploy/sre-api -- pg_isready -h $DB_HOST -p 5432
   ```
4. **Check Recent Deployments:**
   ```bash
   kubectl rollout history deployment/sre-api
   ```

---

## 4. Mitigation & Resolution
### Scenario A: Bad Code Deployment
If errors started right after a new image release:
```bash
# Instant rollback to previous stable revision
kubectl rollout undo deployment/sre-api
# Verify rollout status
kubectl rollout status deployment/sre-api
```

### Scenario B: Database Connection Exhaustion
If logs indicate `pool timeout` or `too many clients`:
```bash
# Restart pods sequentially to release leaked pool handles
kubectl rollout restart deployment/sre-api
```

---

## 5. Post-Incident Actions
1. Confirm error rate has dropped back below 0.1% for at least 10 minutes.
2. Calculate total Error Budget consumed during the incident window.
3. Initiate a blameless post-mortem using `postmortems/template.md`.
