"""HYDRA V4 — adversarial test: NO live order surface.

Verify that the orchestrator never imports / depends on:
  * oanda / oandapyV20
  * requests / urllib / urllib3 / httpx
  * socket / http.client
  * anthropic / openai (no LLM upgrade path)

Static-string-scan over the orchestrator package files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.v4.orchestrator_constants import FORBIDDEN_IMPORTS

ORCH_DIR = Path(__file__).resolve().parents[1]


def _orchestrator_python_files():
    out = []
    for p in ORCH_DIR.glob("*.py"):
        out.append(p)
    return out


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_IMPORTS))
def test_orchestrator_does_not_import(forbidden):
    """Match `import foo` and `from foo` at line start."""
    pat = re.compile(
        rf"^\s*(?:import|from)\s+{re.escape(forbidden)}(?:\.|\s|$)", re.MULTILINE
    )
    offenders = []
    for p in _orchestrator_python_files():
        text = p.read_text(encoding="utf-8")
        if pat.search(text):
            offenders.append(p.name)
    assert not offenders, (
        f"FORBIDDEN import {forbidden!r} found in orchestrator files: {offenders}"
    )


def test_no_oanda_string_in_runtime_files():
    """The runtime files (Hydra, cycle_id, decision_cycle_record, errors)
    must not mention oanda. orchestrator_constants.py legitimately lists
    'oanda' inside FORBIDDEN_IMPORTS — that's allowed."""
    runtime = ("HydraOrchestratorV4.py", "cycle_id.py",
               "decision_cycle_record.py", "orchestrator_errors.py",
               "__init__.py")
    for p in _orchestrator_python_files():
        if p.name not in runtime:
            continue
        text = p.read_text(encoding="utf-8").lower()
        assert "oanda" not in text, f"'oanda' string found in {p.name}"


def test_no_broker_class_names():
    forbidden_names = (
        "OANDA",
        "BrokerClient",
        "send_order",
        "place_order",
        "submit_order",
        "execute_order",
        "buy_market",
        "sell_market",
    )
    offenders: list = []
    for p in _orchestrator_python_files():
        text = p.read_text(encoding="utf-8")
        for name in forbidden_names:
            if name in text:
                offenders.append(f"{p.name}:{name}")
    assert not offenders, f"Broker-style names found: {offenders}"


def test_decision_cycle_result_has_no_order_fields():
    """DecisionCycleResult must NOT carry order_id / fill / size / side."""
    from dataclasses import fields

    from orchestrator.v4.decision_cycle_record import DecisionCycleResult

    field_names = {f.name for f in fields(DecisionCycleResult)}
    forbidden = {
        "order_id",
        "broker_order_id",
        "fill_price",
        "size",
        "lots",
        "side",
        "submitted_to_broker",
    }
    assert not (field_names & forbidden), (
        f"DecisionCycleResult contains forbidden order field: "
        f"{field_names & forbidden}"
    )
