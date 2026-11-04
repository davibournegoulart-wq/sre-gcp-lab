import os
import time
import random
import logging
from typing import Optional
from fastapi import FastAPI, Response, status, Query
from prometheus_fastapi_instrumentator import Instrumentator

# Configure JSON-compatible structured logging for Google Cloud Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s", "level":"%(levelname)s", "message":"%(message)s", "service":"sre-api"}'
)
logger = logging.getLogger("sre-api")

app = FastAPI(
    title="SRE GCP Core Service",
    description="Production-grade FastAPI service instrumented for Prometheus and Cloud Logging",
    version="1.0.0"
)

# Initialize Prometheus metrics instrumentation
# Exposes /metrics with default latency, error rate and request count histograms
instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/healthz", "/ready", "/metrics"]
)
instrumentator.instrument(app).expose(app)

# Chaos & Fault Injection State
FAULT_STATE = {
    "injected_latency_ms": 0,
    "injected_error_rate": 0.0,
    "memory_hog": []
}

@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health"])
def health_check():
    """Kubernetes Liveness Probe."""
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/ready", status_code=status.HTTP_200_OK, tags=["Health"])
def readiness_check(response: Response):
    """Kubernetes Readiness Probe."""
    if FAULT_STATE["injected_error_rate"] >= 1.0:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        logger.error("Readiness check failed: Service in critical fault state")
        return {"status": "degraded", "detail": "Readiness probe failed"}
    return {"status": "ready"}

@app.get("/api/v1/items", tags=["Business API"])
def list_items():
    """Standard business logic route."""
    # Apply injected latency if configured
    if FAULT_STATE["injected_latency_ms"] > 0:
        time.sleep(FAULT_STATE["injected_latency_ms"] / 1000.0)

    # Apply injected error rate if configured
    if FAULT_STATE["injected_error_rate"] > 0:
        if random.random() < FAULT_STATE["injected_error_rate"]:
            logger.error("Internal Server Error: simulated downstream failure")
            return Response(
                content='{"error": "Simulated Downstream Database Timeout"}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json"
            )

    logger.info("Successfully fetched 15 active business items")
    return {
        "success": True,
        "count": 15,
        "items": [{"id": i, "name": f"Resource-{i}", "status": "active"} for i in range(1, 16)]
    }

# --- CHAOS & FAILURE INJECTION ENDPOINTS (FOR SRE LABS) ---

@app.post("/chaos/inject-latency", tags=["Chaos Engineering"])
def inject_latency(ms: int = Query(500, description="Latency in milliseconds")):
    """Inject artificial latency into requests to trigger SLO latency alerts."""
    FAULT_STATE["injected_latency_ms"] = ms
    logger.warning(f"CHAOS INJECTED: Latency set to {ms}ms")
    return {"message": f"Latency of {ms}ms injected into /api/v1/items"}

@app.post("/chaos/inject-error", tags=["Chaos Engineering"])
def inject_error_rate(rate: float = Query(0.3, ge=0.0, le=1.0, description="Error rate 0.0 to 1.0")):
    """Inject artificial 500 error rate to trigger SLO Error Budget burn rate."""
    FAULT_STATE["injected_error_rate"] = rate
    logger.warning(f"CHAOS INJECTED: Error rate set to {rate * 100}%")
    return {"message": f"Error rate of {rate * 100}% injected into /api/v1/items"}

@app.post("/chaos/reset", tags=["Chaos Engineering"])
def reset_chaos():
    """Reset all injected faults to normal production parameters."""
    FAULT_STATE["injected_latency_ms"] = 0
    FAULT_STATE["injected_error_rate"] = 0.0
    FAULT_STATE["memory_hog"].clear()
    logger.info("CHAOS RESET: All operational parameters restored to baseline")
    return {"message": "All faults cleared. System nominal."}
