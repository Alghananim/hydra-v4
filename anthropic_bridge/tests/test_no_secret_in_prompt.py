"""Test that secrets cannot be smuggled into a Claude prompt."""

from __future__ import annotations

import pytest

from anthropic_bridge import bridge as _bridge
from anthropic_bridge import prompt_templates as _tpl
from anthropic_bridge.bridge import AnthropicBridge, AnthropicBridgeError


def _ok_payload(extra=None):
    base = {
        "symbol": "EUR_USD",
        "session_window": "MORNING",
        "final_status": "BLOCK",
        "grades": "A,B,C",
        "decisions": "WAIT,BLOCK,BLOCK",
        "risk_flags": "HIGH_VOL",
        "evidence_summary": "no momentum",
        "blocking_reason": "consensus failed",
    }
    if extra:
        base.update(extra)
    return base


def test_render_rejects_api_key_in_payload():
    with pytest.raises(ValueError):
        _tpl.render("gate_review", _ok_payload({"api_key": "sk-ant-xxxx"}))


def test_render_rejects_account_id_key():
    with pytest.raises(ValueError):
        _tpl.render("gate_review", _ok_payload({"account_id": "001-002-12345678-001"}))


def test_render_rejects_token_key():
    with pytest.raises(ValueError):
        _tpl.render("gate_review", _ok_payload({"token": "abc"}))


def test_account_id_pattern_in_value_is_caught_by_redactor():
    """Even if the KEY is innocuous, an account-id-shaped VALUE must trip the redactor."""
    # Render is OK because the key isn't banned, but the bridge's
    # assert_clean step refuses to send.
    payload = _ok_payload({"evidence_summary": "user account 001-002-12345678-001 had issues"})
    bridge = AnthropicBridge(api_key="x" * 32)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", payload)


def test_sk_ant_pattern_in_value_caught():
    payload = _ok_payload({"evidence_summary": "leaked sk-ant-abcdefghijklmnop1234567890"})
    bridge = AnthropicBridge(api_key="x" * 32)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", payload)


def test_bearer_in_value_caught():
    payload = _ok_payload({"evidence_summary": "Bearer ABCDEFGH12345678"})
    bridge = AnthropicBridge(api_key="x" * 32)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("gate_review", payload)


def test_unknown_template():
    bridge = AnthropicBridge(api_key="x" * 32)
    with pytest.raises(AnthropicBridgeError):
        bridge.request("does_not_exist", _ok_payload())


def test_render_missing_required_field():
    payload = {"symbol": "EUR_USD"}  # missing many fields
    with pytest.raises(ValueError):
        _tpl.render("gate_review", payload)
