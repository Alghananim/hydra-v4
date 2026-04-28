"""Claude has NO authority to upgrade a decision to ENTER."""

from __future__ import annotations

import json

import pytest

from anthropic_bridge.bridge import AnthropicBridge, AnthropicBridgeError


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


def test_suggestion_upgrade_rejected():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "upgrade", "reason": "I think it's fine"},
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())


def test_suggestion_force_enter_rejected():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "force_enter", "reason": "buy buy buy"},
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())


def test_suggestion_agree_accepted():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "agree", "reason": "looks reasonable"},
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    out = bridge.request("gate_review", _payload())
    assert out["parsed"]["suggestion"] == "agree"


def test_suggestion_downgrade_accepted():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "downgrade", "reason": "more risk than worth it"},
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    out = bridge.request("gate_review", _payload())
    assert out["parsed"]["suggestion"] == "downgrade"


def test_suggestion_block_accepted():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "block", "reason": "definitely not"},
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    out = bridge.request("gate_review", _payload())
    assert out["parsed"]["suggestion"] == "block"
