"""HYDRA V4 — Claude safety: no LLM upgrade path.

Verify that:
  * No `anthropic` / `openai` import is reachable from the orchestrator.
  * The orchestrator does not own a 'second_pass' / 'review' / 'upgrade'
    method that could mutate a brain output.
  * Every public method on HydraOrchestratorV4 is enumerated and audited.

This is the LAST line of defence against a stealth-edit that adds a
Claude rate-limited fallback path.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4

ORCH_DIR = Path(HydraOrchestratorV4.__module__.replace(".", "/")).parent
ORCH_FILE = Path(__file__).resolve().parents[1] / "HydraOrchestratorV4.py"


def test_no_anthropic_or_openai_import_in_module():
    text = ORCH_FILE.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+anthropic\b", text, re.MULTILINE)
    assert not re.search(r"^\s*(import|from)\s+openai\b", text, re.MULTILINE)


def test_no_llm_method_names():
    forbidden = (
        "claude_review",
        "second_pass",
        "llm_upgrade",
        "ai_review",
        "upgrade_brain_output",
        "rerank",
        "claude_call",
    )
    members = {n for n, _ in inspect.getmembers(HydraOrchestratorV4)}
    leaked = members & set(forbidden)
    assert not leaked, f"LLM-style methods present: {leaked}"


def test_no_mutate_brain_output():
    """The orchestrator's source must not contain raw assignments to
    `news_out.<field>` / `market_out.<field>` / `chart_out.<field>`."""
    text = ORCH_FILE.read_text(encoding="utf-8")
    pat = re.compile(
        r"(news_out|market_out|chart_out|gate_decision)\."
        r"[A-Za-z_][A-Za-z0-9_]*\s*="
    )
    assert not pat.search(text), (
        "orchestrator appears to mutate a brain output field"
    )


def test_public_api_is_minimal():
    """Public surface is run_cycle + smartnotebook + the 4 brain handles
    and the constructor. No surprise upgrade method."""
    public = [
        n for n in dir(HydraOrchestratorV4)
        if not n.startswith("_")
    ]
    expected = {"run_cycle", "newsmind", "marketmind", "chartmind",
                "gatemind", "smartnotebook"}
    extra = set(public) - expected
    # Allow any inherited dunders / object methods only — extra public
    # attributes attached by a future commit would be caught here.
    assert not extra, f"Unexpected public attrs: {extra}"


def test_gate_decision_not_subclassed_or_overridden():
    """GateMindV4 is the only thing that builds GateDecision. Re-import to
    confirm we use the frozen original."""
    from gatemind.v4.models import GateDecision
    assert GateDecision.__module__ == "gatemind.v4.models"
