# Runbook: API Backend Down / Unreachable

## 1. Metadata
- **Alert Name:** `APIDown`
- **Severity:** P1 (Critical Outage)
- **Target:** `sre-api` instance unreachable via Prometheus scraper for >1 minute.

---

## 2. Fast Recovery SOP
1. **Check Pod Lifecycle:**
   ```bash
   kubectl get pods -l app=sre-api
   ```
2. **Inspect Crashing Pods:**
   ```bash
   kubectl describe pod -l app=sre-api | grep -E "State:|Reason:|Exit Code:|Last State:"
   ```
   - **Exit Code 137:** OOMKilled (Out of Memory). Solution: increase memory request/limit in `k8s/deployment.yaml`.
   - **Exit Code 1 / 2:** Application startup failure. Check configuration env vars.
3. **Check Service Endpoints:**
   ```bash
   kubectl get endpoints sre-api-service
   ```
4. **Emergency Pod Restart:**
   ```bash
   kubectl rollout restart deployment/sre-api
   ```

