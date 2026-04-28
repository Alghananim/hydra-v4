"""Response must be a tool_use JSON block, not free text."""

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


def test_response_with_only_text_block_rejected():
    fake = _FakeOpener({"content": [{"type": "text", "text": "agree, looks ok"}]})
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())


def test_response_no_content_rejected():
    fake = _FakeOpener({"content": []})
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())


def test_response_wrong_schema_rejected():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "agree"},  # missing 'reason'
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())


def test_response_with_extra_fields_rejected():
    fake = _FakeOpener({
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {
                    "suggestion": "agree",
                    "reason": "ok",
                    "extra_field_attack": "haha",
                },
            }
        ]
    })
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=fake)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", _payload())
