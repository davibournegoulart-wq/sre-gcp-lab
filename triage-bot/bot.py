"""
SRE AI Incident Triage Bot
Listens to Alertmanager webhooks, analyzes real-time telemetry/logs,
invokes LLMs (Gemini / Claude) for Root Cause Analysis (RCA) hypothesis,
and dispatches actionable triage cards to Slack/Discord.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel
import requests

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"triage-bot","message":"%(message)s"}'
)
logger = logging.getLogger("triage-bot")

app = FastAPI(
    title="SRE AI Triage Bot",
    description="Automated Alert Triage & Root Cause Analysis via LLMs",
    version="1.0.0"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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


def fallback_rca_engine(alert: AlertItem) -> Dict[str, Any]:
    """
    Deterministic rule-based fallback when LLM API keys are not supplied.
    Ensures zero failure during offline recruiting/local demonstrations.
    """
    alert_name = alert.labels.get("alertname", "UnknownAlert")
    summary = alert.annotations.get("summary", "")
    description = alert.annotations.get("description", "")

    if "FastErrorBudgetBurn" in alert_name:
        hypothesis = "Elevated 5xx error rate detected across service endpoints, causing severe error budget depletion (>14.4x burn rate)."
        blast_radius = "All inbound HTTP traffic encountering intermittent 500/503 errors. Monthly availability SLO at imminent risk."
        recommended_actions = [
            "Check recent deployment revisions: kubectl rollout history deployment/sre-api",
            "Verify database connection pool & circuit breaker status",
            "If error began following release, execute instant rollback: kubectl rollout undo deployment/sre-api",
            "Review runbook: high-error-rate.md"
        ]
    elif "HighP95Latency" in alert_name:
        hypothesis = "P95 response latency exceeded 300ms SLA target. Likely downstream database bottleneck, CPU throttling, or artificial latency injection."
        blast_radius = "High response times impacting user-facing checkout/read operations."
        recommended_actions = [
            "Inspect container CPU/Memory saturation on GKE / Node pool",
            "Check Cloud SQL / Postgres slow query logs",
            "Verify if chaos injection endpoint was triggered: GET /chaos/status",
            "Review runbook: high-latency.md"
        ]
    elif "APIDown" in alert_name:
        hypothesis = "Pod target unreachable or crashed. Probable OOMKilled, failed health checks, or network partition."
        blast_radius = "Total unavailability of backend service."
        recommended_actions = [
            "Run: kubectl describe pods -l app=sre-api",
            "Inspect termination reason (Exit Code 137 = OOM, Exit Code 1 = Application Panic)",
            "Review runbook: api-down.md"
        ]
    else:
        hypothesis = f"Telemetry anomaly detected for alert {alert_name}."
        blast_radius = "Under evaluation."
        recommended_actions = [
            f"Inspect service logs and Prometheus targets for {alert_name}",
            "Follow standard P2/P3 incident triage SOP"
        ]

    return {
        "hypothesis": hypothesis,
        "blast_radius": blast_radius,
        "recommended_actions": recommended_actions,
        "source": "deterministic_fallback_engine"
    }


def call_gemini_rca(alert: AlertItem) -> Dict[str, Any]:
    """
    Query Gemini 1.5 Pro/Flash to perform automated incident triage and root cause hypothesis.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
You are an expert Google Site Reliability Engineer (SRE).
An alert was triggered by Alertmanager in our production Kubernetes cluster:

Alert Name: {alert.labels.get('alertname')}
Severity: {alert.labels.get('severity')}
Summary: {alert.annotations.get('summary')}
Description: {alert.annotations.get('description')}
Runbook: {alert.annotations.get('runbook_url')}

Generate a concise incident triage report in valid JSON format with keys:
- "hypothesis": Root cause hypothesis (1-2 sentences)
- "blast_radius": Estimated user impact and SLO burn impact
- "recommended_actions": Array of 3 specific shell commands or tactical mitigation steps
"""
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        result = json.loads(text.strip())
        result["source"] = "gemini-1.5-flash"
        return result
    except Exception as e:
        logger.warning(f"Gemini API call failed ({e}), falling back to deterministic RCA.")
        return fallback_rca_engine(alert)


def dispatch_notification(triage_report: Dict[str, Any]):
    """
    Sends the formatted incident triage card to external channels (Slack / Discord).
    """
    alert_name = triage_report["alert"]["labels"].get("alertname", "Alert")
    severity = triage_report["alert"]["labels"].get("severity", "info").upper()
    analysis = triage_report["analysis"]

    message_text = f"""
🚨 **[SRE AI INCIDENT TRIAGE] {severity} - {alert_name}**
• **Triggered At:** {datetime.utcnow().isoformat()}Z
• **Summary:** {triage_report['alert']['annotations'].get('summary', 'N/A')}
• **Root Cause Hypothesis:** {analysis.get('hypothesis')}
• **Blast Radius & SLO Impact:** {analysis.get('blast_radius')}
• **Recommended Actions:**
  - """ + "\n  - ".join(analysis.get("recommended_actions", [])) + f"""
• **Runbook:** {triage_report['alert']['annotations'].get('runbook_url', 'N/A')}
*(Analyzed by {analysis.get('source')})*
"""
    logger.info(message_text)

    # Dispatch to Discord webhook if configured
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"content": message_text}, timeout=5)
        except Exception as e:
            logger.error(f"Failed to post to Discord: {e}")

    # Dispatch to Slack webhook if configured
    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": message_text}, timeout=5)
        except Exception as e:
            logger.error(f"Failed to post to Slack: {e}")


def process_alert(alert: AlertItem):
    logger.info(f"Processing alert: {alert.labels.get('alertname')}")
    
    if GEMINI_API_KEY:
        analysis = call_gemini_rca(alert)
    else:
        analysis = fallback_rca_engine(alert)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "alert": alert.model_dump(),
        "analysis": analysis
    }

    # Save to file for post-mortem auditing
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
    return {"status": "ok", "service": "sre-triage-bot"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=5001, reload=False)
