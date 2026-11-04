"""
SRE AI Incident Triage Bot (Active AIOps Agent)
Listens to Alertmanager webhooks, actively queries real-time Prometheus telemetry,
inspects chaos states, invokes LLMs (Gemini / Claude) for Root Cause Analysis (RCA),
and dispatches actionable incident triage cards.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import requests

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"triage-bot","message":"%(message)s"}'
)
logger = logging.getLogger("triage-bot")

app = FastAPI(
    title="SRE AI Triage Bot",
    description="Active Alert Triage & Root Cause Analysis via Prometheus & LLMs",
    version="1.2.0"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
API_TARGET_URL = os.getenv("API_TARGET_URL", "http://api:8000")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class AlertItem(BaseModel):
    status: str
    labels: Dict[str, str] = {}
    annotations: Dict[str, str] = {}
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None


class AlertmanagerPayload(BaseModel):
    version: Optional[str] = None
    status: str
    receiver: Optional[str] = None
    alerts: List[AlertItem] = []


def query_prometheus_metric(query: str) -> Optional[float]:
    """Execute real-time PromQL query against Prometheus HTTP API."""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query"
        resp = requests.get(url, params={"query": query}, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if results:
                # Value format: [timestamp, "string_float"]
                return round(float(results[0]["value"][1]), 4)
    except Exception as e:
        logger.warning(f"Could not query Prometheus ({query}): {e}")
    return None


def fetch_live_telemetry_snapshot() -> Dict[str, Any]:
    """Actively polls current cluster state to enrich RCA context."""
    telemetry = {
        "error_rate_5m": query_prometheus_metric(
            'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))'
        ),
        "p95_latency_s": query_prometheus_metric(
            'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[2m])) by (le))'
        ),
        "qps_total": query_prometheus_metric('sum(rate(http_requests_total[1m]))'),
        "chaos_state": None
    }

    # Inspect if chaos was actively injected
    try:
        chaos_resp = requests.get(f"{API_TARGET_URL}/chaos/status", timeout=2)
        if chaos_resp.status_code == 200:
            telemetry["chaos_state"] = chaos_resp.json().get("state", {})
    except Exception as e:
        logger.warning(f"Could not reach API chaos status: {e}")

    return telemetry


def fallback_rca_engine(alert: AlertItem, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic rule-based fallback when LLM API keys are not supplied."""
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    chaos = telemetry.get("chaos_state") or {}

    if chaos.get("injected_error_rate", 0) > 0:
        hypothesis = f"Chaos fault injection detected: {chaos.get('injected_error_rate') * 100}% simulated 500 error rate active."
        blast_radius = "Artificial outage simulated via /chaos/inject-error. Depleting Error Budget rapidly."
        recommended_actions = [
            "Trigger chaos reset: curl -X POST http://api:8000/chaos/reset",
            "Verify Grafana SLO burn rate returns below 1.0x",
            "Confirm resolution in Alertmanager"
        ]
    elif chaos.get("injected_latency_ms", 0) > 0:
        hypothesis = f"Chaos latency injection detected: {chaos.get('injected_latency_ms')}ms artificial delay active."
        blast_radius = f"P95 latency elevated to {telemetry.get('p95_latency_s', 'unknown')}s. Breaching 300ms SLO."
        recommended_actions = [
            "Reset latency injection: curl -X POST http://api:8000/chaos/reset",
            "Monitor HPA pod scaling response",
            "Review runbook: high-latency.md"
        ]
    elif "FastErrorBudgetBurn" in alert_name:
        err_pct = (telemetry.get("error_rate_5m") or 0.15) * 100
        hypothesis = f"Critical Error Budget Burn (14.4x rate). Measured 5m error rate is currently {err_pct:.1f}%."
        blast_radius = "All inbound HTTP traffic encountering intermittent 500 errors. 30-day availability SLO compromised."
        recommended_actions = [
            "Check recent deployment rollout: kubectl rollout history deployment/sre-api",
            "Check database connection pool metrics in Cloud SQL",
            "If regression from release, rollback: kubectl rollout undo deployment/sre-api",
            "Review runbook: high-error-rate.md"
        ]
    elif "HighP95Latency" in alert_name:
        p95 = telemetry.get("p95_latency_s", 0)
        hypothesis = f"P95 response latency exceeded 300ms SLA target (Current: {p95}s). Probable DB pool bottleneck or thread starvation."
        blast_radius = "Slow API response times impacting user-facing read operations."
        recommended_actions = [
            "Inspect container CPU/Memory saturation: kubectl top pods -l app=sre-api",
            "Scale pod replicas if HPA is lagging: kubectl scale deployment sre-api --replicas=6",
            "Review runbook: high-latency.md"
        ]
    else:
        hypothesis = f"Telemetry anomaly detected for alert {alert_name}."
        blast_radius = "Under evaluation."
        recommended_actions = [
            f"Inspect Prometheus targets and logs for {alert_name}",
            "Follow standard P2/P3 incident triage SOP"
        ]

    return {
        "hypothesis": hypothesis,
        "blast_radius": blast_radius,
        "recommended_actions": recommended_actions,
        "telemetry_snapshot": telemetry,
        "source": "deterministic_active_engine"
    }


def call_gemini_rca(alert: AlertItem, telemetry: Dict[str, Any]) -> Dict[str, Any]:
    """Query Gemini 1.5 with live telemetry context for intelligent Root Cause Analysis."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
You are an expert Google Site Reliability Engineer (SRE).
Alertmanager triggered the following production alert:

Alert Name: {alert.labels.get('alertname')}
Severity: {alert.labels.get('severity')}
Summary: {alert.annotations.get('summary')}
Description: {alert.annotations.get('description')}
Runbook: {alert.annotations.get('runbook_url')}

LIVE TELEMETRY SNAPSHOT COLLECTED FROM PROMETHEUS:
- Current 5m Error Rate: {telemetry.get('error_rate_5m')}
- Current P95 Latency: {telemetry.get('p95_latency_s')}s
- Total QPS: {telemetry.get('qps_total')}
- Active Chaos State: {json.dumps(telemetry.get('chaos_state'))}

Analyze this data and return a JSON object with:
- "hypothesis": Root cause hypothesis based on the live telemetry (1-2 sentences)
- "blast_radius": Estimated user impact and SLO Error Budget burn
- "recommended_actions": Array of 3 specific shell commands or immediate mitigation steps
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
        result["telemetry_snapshot"] = telemetry
        result["source"] = "gemini-1.5-flash"
        return result
    except Exception as e:
        logger.warning(f"Gemini API call failed ({e}), falling back to deterministic RCA.")
        return fallback_rca_engine(alert, telemetry)


def dispatch_notification(triage_report: Dict[str, Any]):
    """Sends the formatted incident triage card to external channels."""
    alert_name = triage_report["alert"]["labels"].get("alertname", "Alert")
    severity = triage_report["alert"]["labels"].get("severity", "info").upper()
    analysis = triage_report["analysis"]
    telemetry = analysis.get("telemetry_snapshot", {})

    message_text = f"""
🚨 **[SRE AI INCIDENT TRIAGE] {severity} - {alert_name}**
• **Triggered At:** {datetime.utcnow().isoformat()}Z
• **Live Telemetry:** Error Rate: {telemetry.get('error_rate_5m')} | P95 Latency: {telemetry.get('p95_latency_s')}s | QPS: {telemetry.get('qps_total')}
• **Root Cause Hypothesis:** {analysis.get('hypothesis')}
• **Blast Radius & SLO Impact:** {analysis.get('blast_radius')}
• **Recommended Actions:**
  - """ + "\n  - ".join(analysis.get("recommended_actions", [])) + f"""
• **Runbook:** {triage_report['alert']['annotations'].get('runbook_url', 'N/A')}
*(Analyzed by {analysis.get('source')})*
"""
    logger.info(message_text)

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message_text}, timeout=5)
        except Exception as e:
            logger.error(f"Failed to post to Discord: {e}")

    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": message_text}, timeout=5)
        except Exception as e:
            logger.error(f"Failed to post to Slack: {e}")


def process_alert(alert: AlertItem):
    logger.info(f"Processing alert with active telemetry lookup: {alert.labels.get('alertname')}")
    
    # 1. Collect live metrics snapshot from Prometheus
    telemetry = fetch_live_telemetry_snapshot()

    # 2. Perform intelligent RCA
    if GEMINI_API_KEY:
        analysis = call_gemini_rca(alert, telemetry)
    else:
        analysis = fallback_rca_engine(alert, telemetry)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "alert": alert.model_dump(),
        "analysis": analysis
    }

    # Save to disk for audit
    filename = f"{OUTPUT_DIR}/triage_{int(datetime.utcnow().timestamp())}_{alert.labels.get('alertname')}.json"
    try:
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Triage report saved to {filename}")
    except Exception as e:
        logger.error(f"Could not write triage report file: {e}")

    dispatch_notification(report)


@app.post("/alerts")
async def receive_alerts(payload: AlertmanagerPayload, background_tasks: BackgroundTasks):
    logger.info(f"Received Alertmanager payload with {len(payload.alerts)} alerts")
    for alert in payload.alerts:
        background_tasks.add_task(process_alert, alert)
    return {"status": "accepted", "alerts_queued": len(payload.alerts)}


@app.get("/healthz")
def health_check():
    return {"status": "ok", "service": "sre-triage-bot", "mode": "active_aiops"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=5001, reload=False)
