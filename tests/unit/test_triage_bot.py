"""Triage bot auth, limits and filename safety (run: make unit)."""
import importlib
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "triage-bot"))
TOKEN = "w" * 40
os.environ["ALERT_WEBHOOK_TOKEN_FILE"] = "/nonexistent"
os.environ["ALERT_WEBHOOK_TOKEN"] = TOKEN
os.environ["OUTPUT_DIR"] = "/tmp/triage-test"
bot = importlib.import_module("bot")
client = TestClient(bot.app)
PAYLOAD = {"status": "firing", "alerts": []}


def test_alerts_require_bearer_token():
    assert client.post("/alerts", json=PAYLOAD).status_code == 401
    assert client.post("/alerts", json=PAYLOAD, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/alerts", json=PAYLOAD, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_oversized_payload_rejected():
    big = {"status": "firing", "alerts": [{"status": "firing"}] * 51}
    assert client.post("/alerts", json=big, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 422


def test_filename_is_sanitized():
    assert bot.safe_filename_part("../../etc/passwd") == "_.._etc_passwd"
    assert "/" not in bot.safe_filename_part("a/b\\c")


def test_llm_quota_and_cooldown():
    bot._llm_calls.clear(); bot._llm_last_by_alert.clear()
    assert bot.llm_call_allowed("A", now=1000)
    assert not bot.llm_call_allowed("A", now=1010)  # cooldown
    for i in range(bot.LLM_DAILY_LIMIT - 1):
        assert bot.llm_call_allowed(f"B{i}", now=2000)
    assert not bot.llm_call_allowed("C", now=2000)  # daily cap
