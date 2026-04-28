"""End-to-end mock test of the bridge."""

from __future__ import annotations

import json

import pytest

from anthropic_bridge.bridge import AnthropicBridge, AnthropicBridgeError
from anthropic_bridge.secret_loader import (
    SecretNotConfiguredError,
    have_anthropic,
    load_anthropic_key,
)


class _FakeOpener:
    def __init__(self, body):
        self._body = body
        self.last_request = None

    def open(self, req, timeout=None):
        self.last_request = req
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


def _payload():
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


def test_audit_hash_present_and_stable():
    body = {
        "content": [
            {"type": "tool_use", "name": "structured_response",
             "input": {"suggestion": "agree", "reason": "ok"}}
        ]
    }
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=_FakeOpener(body))
    out1 = bridge.request("gate_review", _payload())
    out2 = bridge.request("gate_review", _payload())
    # Same prompt + same response → same audit hash.
    assert out1["audit_hash"] == out2["audit_hash"]
    assert len(out1["audit_hash"]) == 64  # sha256 hex


def test_audit_hash_changes_with_response():
    body1 = {
        "content": [
            {"type": "tool_use", "name": "structured_response",
             "input": {"suggestion": "agree", "reason": "ok"}}
        ]
    }
    body2 = {
        "content": [
            {"type": "tool_use", "name": "structured_response",
             "input": {"suggestion": "block", "reason": "no good"}}
        ]
    }
    b1 = AnthropicBridge(api_key="x" * 32, url_opener=_FakeOpener(body1))
    b2 = AnthropicBridge(api_key="x" * 32, url_opener=_FakeOpener(body2))
    out1 = b1.request("gate_review", _payload())
    out2 = b2.request("gate_review", _payload())
    assert out1["audit_hash"] != out2["audit_hash"]


def test_outgoing_request_has_xapikey_header():
    body = {
        "content": [
            {"type": "tool_use", "name": "structured_response",
             "input": {"suggestion": "agree", "reason": "ok"}}
        ]
    }
    fake = _FakeOpener(body)
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    bridge.request("gate_review", _payload())
    headers = dict(fake.last_request.headers)
    # Headers in urllib normalize the key to title-case.
    assert any(k.lower() == "x-api-key" for k in headers)


def test_outgoing_request_uses_tool_choice_force():
    body = {
        "content": [
            {"type": "tool_use", "name": "structured_response",
             "input": {"suggestion": "agree", "reason": "ok"}}
        ]
    }
    fake = _FakeOpener(body)
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    bridge.request("gate_review", _payload())
    sent = json.loads(fake.last_request.data.decode("utf-8"))
    assert sent["tool_choice"]["type"] == "tool"
    assert sent["tool_choice"]["name"] == "structured_response"
    assert len(sent["tools"]) == 1


def test_secret_loader_missing_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert have_anthropic() is False
    with pytest.raises(SecretNotConfiguredError):
        load_anthropic_key()


def test_secret_loader_present_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-real")
    assert have_anthropic() is True
    assert load_anthropic_key() == "sk-ant-real-real"


def test_redactor_scrubs_oanda_account():
    from anthropic_bridge import secret_redactor as r
    s = "the user is account 001-002-12345678-001 with issues"
    out = r.redact(s)
    assert "001-002-12345678-001" not in out


def test_redactor_scrubs_sk_ant():
    from anthropic_bridge import secret_redactor as r
    s = "key sk-ant-abcdefghijklmnopqrstuvwxyz1234567890"
    out = r.redact(s)
    assert "abcdefghijklmnop" not in out


def test_redactor_scrubs_bearer():
    from anthropic_bridge import secret_redactor as r
    s = "header is Bearer ABCDEFGH12345678"
    out = r.redact(s)
    assert "ABCDEFGH12345678" not in out


def test_constructor_rejects_short_key():
    with pytest.raises(ValueError):
        AnthropicBridge(api_key="short")


def test_repr_does_not_leak_key():
    bridge = AnthropicBridge(api_key="sk-ant-LEAKABLE-xxxxxxxxxxxxxxxxxxxx")
    assert "LEAKABLE" not in repr(bridge)


def test_unknown_template_raises():
    bridge = AnthropicBridge(api_key="x" * 32)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("nope", {})


def test_response_validator_supports_subset():
    from anthropic_bridge import response_validator as rv
    rv.validate({"a": 1}, {"type": "object", "properties": {"a": {"type": "integer"}}})
    with pytest.raises(rv.ValidationError):
        rv.validate({"a": True}, {"type": "object", "properties": {"a": {"type": "integer"}}})
