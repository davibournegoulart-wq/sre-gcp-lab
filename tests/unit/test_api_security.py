"""Security regressions from the 2026-11-04 audit (run: make unit)."""
import importlib
import json
import logging
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))
TOKEN = "t" * 32


def load_app(enabled: bool):
    os.environ["CHAOS_ENABLED"] = "true" if enabled else "false"
    os.environ["CHAOS_TOKEN"] = TOKEN
    import main
    return importlib.reload(main)


@pytest.fixture
def api():
    main = load_app(True)
    yield main, TestClient(main.app)
    main.FAULT_STATE.update(injected_latency_ms=0, injected_error_rate=0.0, circuit_broken=False)


def test_chaos_requires_token(api):
    _, client = api
    assert client.post("/chaos/inject-error?rate=0.5").status_code == 401
    assert client.post("/chaos/inject-error?rate=0.5", headers={"X-Chaos-Token": "wrong"}).status_code == 401
    assert client.post("/chaos/inject-error?rate=0.5", headers={"X-Chaos-Token": TOKEN}).status_code == 200


def test_chaos_disabled_is_404():
    client = TestClient(load_app(False).app)
    assert client.post("/chaos/reset", headers={"X-Chaos-Token": TOKEN}).status_code == 404


def test_latency_is_bounded(api):
    _, client = api
    assert client.post("/chaos/inject-latency?ms=999999999", headers={"X-Chaos-Token": TOKEN}).status_code == 422


def test_untrusted_trace_id_is_replaced(api):
    _, client = api
    r = client.get("/healthz", headers={"X-Trace-ID": 'x" ,"level":"FORGED'})
    assert r.headers["X-Trace-ID"] != 'x" ,"level":"FORGED'
    assert client.get("/healthz", headers={"X-Trace-ID": "trc-abc123"}).headers["X-Trace-ID"] == "trc-abc123"


def test_log_lines_stay_valid_json(api):
    main, _ = api
    record = logging.LogRecord("sre-api", logging.INFO, "", 0, 'GET /"},{"level":"ERROR -> 404', None, None)
    record.trace_id = "abc"
    parsed = json.loads(main.JsonLogFormatter().format(record))
    assert parsed["level"] == "INFO" and parsed["message"].startswith('GET /"}')


def test_security_headers(api):
    _, client = api
    r = client.get("/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
