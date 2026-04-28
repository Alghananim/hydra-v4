"""Logging must NEVER contain a real secret value."""

from __future__ import annotations

import io
import json
import logging

import pytest

from anthropic_bridge.bridge import AnthropicBridge


class _FakeOpener:
    def __init__(self, body):
        self._body = body

    def open(self, req, timeout=None):
        class _R:
            def __init__(self, b):
                self._b = b

            def read(self):
                return json.dumps(self._b).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _R(self._body)


def _ok_payload():
    return {
        "symbol": "EUR_USD",
        "session_window": "MORNING",
        "final_status": "BLOCK",
        "grades": "A,B,C",
        "decisions": "WAIT,BLOCK,BLOCK",
        "risk_flags": "HIGH_VOL",
        "evidence_summary": "no momentum",
        "blocking_reason": "consensus failed",
    }


def test_anthropic_key_not_in_logs():
    secret_key = "sk-ant-LIVE_KEY_VALUE_THAT_MUST_NEVER_LEAK_xxxxxxxxxx"
    fake_response = {
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "agree", "reason": "looks fine"},
            }
        ]
    }

    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("anthropic_bridge")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    bridge = AnthropicBridge(
        api_key=secret_key,
        url_opener=_FakeOpener(fake_response),
    )
    bridge.request("gate_review", _ok_payload())

    logger.removeHandler(handler)
    log_text = log_buf.getvalue()
    assert secret_key not in log_text, (
        f"the api key leaked into logs: {log_text!r}"
    )


def test_audit_hash_logged_not_secret():
    fake_response = {
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "block", "reason": "danger"},
            }
        ]
    }
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    logger = logging.getLogger("anthropic_bridge")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    bridge = AnthropicBridge(api_key="x" * 32, url_opener=_FakeOpener(fake_response))
    bridge.request("gate_review", _ok_payload())
    logger.removeHandler(handler)

    text = log_buf.getvalue()
    assert "audit_hash=" in text


def test_account_id_not_in_logs():
    """If a payload contains an account-id-shaped value, the bridge must
    refuse before logging — not log it then redact."""
    payload = _ok_payload()
    payload["evidence_summary"] = "see account 001-002-12345678-001 history"
    log_buf = io.StringIO()
    handler = logging.StreamHandler(log_buf)
    logger = logging.getLogger("anthropic_bridge")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    bridge = AnthropicBridge(api_key="x" * 32, url_opener=_FakeOpener({}))
    with pytest.raises(Exception):
        bridge.request("gate_review", payload)
    logger.removeHandler(handler)
    text = log_buf.getvalue()
    assert "001-002-12345678-001" not in text
