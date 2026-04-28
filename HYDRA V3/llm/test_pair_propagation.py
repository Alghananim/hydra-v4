# -*- coding: utf-8 -*-
"""FIX #1 — pair propagation test.

Verifies that when EngineV3 review path passes ``pair=USD/JPY`` in the
brain_outputs dict, the user-prompt sent to OpenAI says ``USD/JPY`` and
NOT the previously hardcoded ``EUR/USD``.

Uses the dependency-injected ``_http_call`` hook to capture the payload
without making real network calls.
"""
from __future__ import annotations
import sys, pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from llm.openai_brain import review_brain_outputs, _build_user_prompt


def _capturing_http(captured: dict):
    """Return a fake _http_call that stores (system, user) and replies OK."""
    def _call(system: str, user: str):
        captured["system"] = system
        captured["user"] = user
        return ('{"severity":"low","suggestion":"agree","confidence":0.8,'
                '"concerns":[],"reasoning":"ok"}', "")
    return _call


def test_usdjpy_pair_appears_in_prompt():
    captured: dict = {}
    review = review_brain_outputs(
        brain_outputs={
            "pair": "USD/JPY",
            "news_grade": "A", "market_grade": "A+", "chart_grade": "A",
            "news_perm": "allow", "market_perm": "allow", "chart_perm": "allow",
            "news_bias": "bullish", "market_direction": "long",
            "chart_structure": "uptrend", "chart_entry_quality": "good",
            "chart_rr": 2.0, "market_regime": "trend",
            "news_reason": "n", "market_reason": "m", "chart_reason": "c",
        },
        gate_decision={"final_decision": "enter", "reason": "ok"},
        _http_call=_capturing_http(captured),
    )
    assert review.success is True, f"review failed: {review.error}"
    user_prompt = captured.get("user", "")
    assert "USD/JPY" in user_prompt, (
        f"USD/JPY not in user prompt: {user_prompt[:200]}")
    # First line should reference the actual pair
    first_line = user_prompt.splitlines()[0]
    assert "EUR/USD" not in first_line, (
        f"first line still hardcoded EUR/USD: {first_line!r}")
    assert "USD/JPY" in first_line, (
        f"first line missing USD/JPY: {first_line!r}")


def test_eurusd_pair_appears_in_prompt():
    captured: dict = {}
    review = review_brain_outputs(
        brain_outputs={
            "pair": "EUR/USD",
            "news_grade": "A+", "market_grade": "A", "chart_grade": "A",
        },
        gate_decision={"final_decision": "enter", "reason": "ok"},
        _http_call=_capturing_http(captured),
    )
    assert review.success is True
    first_line = captured["user"].splitlines()[0]
    assert "EUR/USD" in first_line


def test_default_falls_back_safely_when_pair_missing():
    """Backwards-compat: callers that omit pair shouldn't crash."""
    captured: dict = {}
    review = review_brain_outputs(
        brain_outputs={"news_grade": "A"},
        gate_decision={"final_decision": "enter", "reason": "x"},
        _http_call=_capturing_http(captured),
    )
    assert review.success is True
    # Default fallback is EUR/USD by mandate (safe default)
    assert "EUR/USD" in captured["user"].splitlines()[0]


def test_build_user_prompt_unit():
    """Direct unit test of the prompt builder — no http."""
    p = _build_user_prompt({"pair": "USD/JPY"},
                            {"final_decision": "enter", "reason": "x"})
    assert p.splitlines()[0] == "Review this trading decision for USD/JPY."

    p2 = _build_user_prompt({}, {"final_decision": "enter", "reason": "x"})
    # missing pair => safe default
    assert p2.splitlines()[0] == "Review this trading decision for EUR/USD."


if __name__ == "__main__":
    for fn in (test_usdjpy_pair_appears_in_prompt,
               test_eurusd_pair_appears_in_prompt,
               test_default_falls_back_safely_when_pair_missing,
               test_build_user_prompt_unit):
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}"); sys.exit(1)
    print("ALL PASS")
