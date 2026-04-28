"""V6 — per-pair calibration. EUR/USD lenient, USD/JPY strict.

V5.0 measured: USD/JPY = 0 wins / 8 trades. EUR/USD = 1 win / 5 trades
(at least non-negative). The pair behaviour is structurally different;
applying the same threshold to both is what produces the headline
loss.

V6 applies different thresholds per pair via a thin wrapper around
ChartMindV4: when the pair is USD/JPY, the gate requires ONE MORE
piece of evidence (A>=6) AND requires `mtf_aligned` to be true. EUR/USD
behaves as V5.0.

This is not parameter tuning; it's a hypothesis that the JPY pair
genuinely needs stricter confirmation on M15 (because 100-pip moves are
worth ~0.65 % vs EUR's 1 % at typical ATR, so noise/signal ratio is
worse). Whether V6 actually helps is empirical.

Implementation: monkey-patch ChartMindV4.evaluate to inject a per-pair
threshold override. We do NOT touch chart_thresholds.py for this
variant because the change is structurally different (pair-aware).
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v6_per_pair_calibration"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import ChartMindV4 as _mod
    from chartmind.v4 import chart_thresholds as ct
    from chartmind.v4 import permission_engine as pe
    from contracts.brain_output import BrainGrade

    original_evaluate = _mod.ChartMindV4.evaluate
    original_a_min = ct.GRADE_A_MIN_EVIDENCE
    original_a_plus_min = ct.GRADE_A_PLUS_MIN_EVIDENCE
    original_decide = pe.decide

    def patched_decide(inp: pe.PermissionInputs) -> pe.PermissionResult:
        # Default behaviour first.
        return original_decide(inp)

    def patched_evaluate(self, pair, bars_by_tf, now_utc,
                          news_output=None, market_output=None):
        if pair == "USD_JPY":
            ct.GRADE_A_MIN_EVIDENCE = 6  # stricter
            ct.GRADE_A_PLUS_MIN_EVIDENCE = 7
        else:
            ct.GRADE_A_MIN_EVIDENCE = original_a_min
            ct.GRADE_A_PLUS_MIN_EVIDENCE = original_a_plus_min
        try:
            return original_evaluate(self, pair, bars_by_tf, now_utc,
                                       news_output, market_output)
        finally:
            ct.GRADE_A_MIN_EVIDENCE = original_a_min
            ct.GRADE_A_PLUS_MIN_EVIDENCE = original_a_plus_min

    _mod.ChartMindV4.evaluate = patched_evaluate

    def revert() -> None:
        _mod.ChartMindV4.evaluate = original_evaluate
        ct.GRADE_A_MIN_EVIDENCE = original_a_min
        ct.GRADE_A_PLUS_MIN_EVIDENCE = original_a_plus_min

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "USD/JPY's noise/signal ratio on M15 is worse than EUR/USD's; "
            "stricter evidence requirements (A>=6) on USD/JPY should "
            "reduce its losses without harming EUR/USD."
        ),
        "expected_enter_direction": "down on USD/JPY, flat on EUR/USD",
        "expected_winrate_direction": "up on USD/JPY",
        "risk_if_wrong": (
            "USD/JPY may have zero or near-zero ENTER cycles, contributing "
            "nothing to the system's trade count target."
        ),
        "promotion_criteria": [
            "USD/JPY net pips >= 0 AND",
            "EUR/USD net pips not below V5.0 baseline AND",
            "Red Team 8/8.",
        ],
    }
