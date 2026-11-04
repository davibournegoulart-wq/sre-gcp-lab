import os
import time
import uuid
import random
import logging
from contextvars import ContextVar
from typing import Optional
from fastapi import FastAPI, Request, Response, status, Query
from fastapi.responses import HTMLResponse
from prometheus_fastapi_instrumentator import Instrumentator

# Context variable for distributed tracing correlation
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="system")


class StructuredLogFilter(logging.Filter):
    """Injects trace_id into all logging records for OpenTelemetry / Loki correlation."""
    def filter(self, record):
        record.trace_id = trace_id_ctx.get()
        return True


# Configure JSON-compatible structured logging for Loki and Google Cloud Logging
log_handler = logging.StreamHandler()
log_formatter = logging.Formatter(
    '{"time":"%(asctime)s", "level":"%(levelname)s", "trace_id":"%(trace_id)s", '
    '"service":"sre-api", "message":"%(message)s"}'
)
log_handler.setFormatter(log_formatter)
log_handler.addFilter(StructuredLogFilter())

logger = logging.getLogger("sre-api")
logger.setLevel(logging.INFO)
logger.handlers = [log_handler]
logger.propagate = False

app = FastAPI(
    title="SRE GCP Core Service",
    description="Production-grade FastAPI service instrumented for Prometheus, Loki and Cloud Logging",
    version="1.1.0"
)

# Request Tracing Middleware
@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    token = trace_id_ctx.set(trace_id)
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id
        if request.url.path not in ["/healthz", "/ready", "/metrics"]:
            logger.info(f"Handled {request.method} {request.url.path} -> {response.status_code} in {duration_ms}ms")
        return response
    finally:
        trace_id_ctx.reset(token)


# Initialize Prometheus metrics instrumentation
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
    "circuit_broken": False
}


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "suite.html")


@app.get("/", response_class=HTMLResponse, tags=["Mission Control Suite"])
def get_mission_control_suite():
    """Serves the Unified SRE Mission Control Suite UI."""
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>SRE Mission Control Suite</h1>"


@app.get("/api/suite/telemetry", tags=["Mission Control Suite"])
def get_suite_telemetry():
    """Real-time telemetry payload for the Mission Control dashboard."""
    return {
        "injected_error_rate": FAULT_STATE["injected_error_rate"],
        "injected_latency_ms": FAULT_STATE["injected_latency_ms"],
        "circuit_broken": FAULT_STATE["circuit_broken"],
        "timestamp": time.time()
    }


@app.get("/healthz", status_code=status.HTTP_200_OK, tags=["Health"])
def health_check():
    """Kubernetes Liveness Probe."""
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/ready", status_code=status.HTTP_200_OK, tags=["Health"])
def readiness_check(response: Response):
    """Kubernetes Readiness Probe."""
    if FAULT_STATE["injected_error_rate"] >= 1.0 or FAULT_STATE["circuit_broken"]:
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
            logger.error("Simulated downstream database timeout on /api/v1/items")
            return Response(
                content='{"error": "Simulated Downstream Database Timeout", "status": 500}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                media_type="application/json"
            )

    logger.info("Successfully fetched 15 active business items from repository")
    return {
        "success": True,
        "count": 15,
        "items": [{"id": i, "name": f"Resource-{i}", "status": "active"} for i in range(1, 16)]
    }


@app.get("/api/v1/items/{item_id}", tags=["Business API"])
def get_item(item_id: int):
    """Get item details by ID."""
    if FAULT_STATE["injected_latency_ms"] > 0:
        time.sleep(FAULT_STATE["injected_latency_ms"] / 1000.0)

    if FAULT_STATE["injected_error_rate"] > 0 and random.random() < FAULT_STATE["injected_error_rate"]:
        logger.error(f"Downstream dependency timeout while fetching item {item_id}")
        return Response(
            content=f'{{"error": "Downstream DB query failed for item {item_id}"}}',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json"
        )

    logger.info(f"Retrieved item {item_id} successfully")
    return {"id": item_id, "name": f"Resource-{item_id}", "status": "active"}


# --- CHAOS & FAILURE INJECTION ENDPOINTS ---

@app.get("/chaos/status", tags=["Chaos Engineering"])
def get_chaos_status():
    """Returns current active chaos configurations."""
    return {"status": "active_faults", "state": FAULT_STATE}


@app.post("/chaos/inject-latency", tags=["Chaos Engineering"])
def inject_latency(ms: int = Query(1500, description="Latency in milliseconds")):
    """Inject artificial latency into requests to trigger SLO latency alerts."""
    FAULT_STATE["injected_latency_ms"] = ms
    logger.warning(f"CHAOS INJECTED: Artificial latency set to {ms}ms")
    return {"message": f"Latency of {ms}ms injected into API routes"}


@app.post("/chaos/inject-error", tags=["Chaos Engineering"])
def inject_error_rate(rate: float = Query(0.25, ge=0.0, le=1.0, description="Error rate 0.0 to 1.0")):
    """Inject artificial 500 error rate to trigger SLO Error Budget burn rate."""
    FAULT_STATE["injected_error_rate"] = rate
    logger.warning(f"CHAOS INJECTED: Error rate set to {rate * 100}%")
    return {"message": f"Error rate of {rate * 100}% injected into API routes"}


@app.post("/chaos/reset", tags=["Chaos Engineering"])
def reset_chaos():
    """Reset all injected faults to normal production parameters."""
    FAULT_STATE["injected_latency_ms"] = 0
    FAULT_STATE["injected_error_rate"] = 0.0
    FAULT_STATE["circuit_broken"] = False
    logger.info("CHAOS RESET: All operational parameters restored to baseline")
    return {"message": "All faults cleared. System nominal."}
