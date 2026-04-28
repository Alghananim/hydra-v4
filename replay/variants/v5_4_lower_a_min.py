"""V5.4 — lower the grade-A minimum from 5/8 to 4/8.

Hypothesis: V5.0 requires >=5 of 8 evidence flags simultaneously to
qualify as A. The diagnostics show ChartMind grade B (3-4 flags) on
6,716 cycles. If the score-vs-win-rate curve is roughly flat between
4 and 5, we sacrifice nothing by lowering the bar. If it's monotonically
increasing, we'd be admitting worse trades.

The honest test is empirical: the V5.1 chartmind_scores.csv tells us
the score distribution. Until that data lands, V5.4 is a hypothesis we
TEST rather than a proposed fix.

Change: GRADE_A_MIN_EVIDENCE 5 -> 4. Other thresholds untouched.
A+ still requires 6.

Risk: turning every score-4 cycle into A grade unlocks ~5,500 more
candidates (per V5.0 diagnostics). If even 30 % of those are profitable,
we've found a big win. If <20 %, we've added losers.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_4_lower_a_min"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import chart_thresholds as ct
    original = ct.GRADE_A_MIN_EVIDENCE
    ct.GRADE_A_MIN_EVIDENCE = 4

    def revert() -> None:
        ct.GRADE_A_MIN_EVIDENCE = original

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Lowering grade A from score>=5 to score>=4 unlocks ~5,500 "
            "additional candidates. If win rate at score=4 is comparable "
            "to score=5, this is a strict improvement."
        ),
        "expected_enter_direction": "strongly up",
        "expected_winrate_direction": "down (we admit more)",
        "risk_if_wrong": (
            "Score-4 setups have systematically worse win rate. Net pip "
            "drops despite more trades."
        ),
        "promotion_criteria": [
            "ENTER count > 200 (significant scale) AND",
            "win rate (excl timeout) >= 30 % AND",
            "net pips after cost > 0 AND",
            "drawdown / net pips < 0.6 AND",
            "Red Team 8/8.",
        ],
        "rejection_triggers": [
            "Net pips < 0 OR",
            "Per-pair regression (either pair worse than V5.0).",
        ],
    }
