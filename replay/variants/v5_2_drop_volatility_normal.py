"""V5.2 — drop the `volatility_normal` evidence flag.

Hypothesis: `volatility_normal` requires ATR percentile in (25, 80).
That structurally excludes ~45 % of M15 bars (compressed ≤25 + expanded
≥80). On EUR/USD and USD/JPY, the ATR-percentile distribution is
roughly uniform within those bins, so the flag rejects ~45 % of cycles
without strong evidence that those cycles are systematically worse.

Change: remove `volatility_normal` from EVIDENCE_KEYS, lowering the
denominator from 8 to 7. Grade thresholds stay at A+ ≥6, A ≥5, B ≥3.
This means cycles previously at score 5/8 with `volatility_normal=False`
become 5/7 and still grade A. Cycles previously at 4/8 stay at 4/7 and
still grade B.

In effect: we drop a lever that "punishes" cycles for being in
compressed/expanded volatility, reasoning that the volatility bin is
already orthogonal to setup quality.

Risk if hypothesis wrong: trades during compressed volatility (ATR
≤25) often expand suddenly and hit SL before TP. We may be admitting
worse trades. Red Team probe P3 (realistic spread) and per-pair
(P5) must continue to pass.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_2_drop_volatility_normal"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import chart_thresholds as ct
    original_keys = ct.EVIDENCE_KEYS
    ct.EVIDENCE_KEYS = tuple(k for k in original_keys if k != "volatility_normal")

    def revert() -> None:
        ct.EVIDENCE_KEYS = original_keys

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Removing the `volatility_normal` evidence flag will increase "
            "ENTER_CANDIDATE count without materially worsening win rate, "
            "because ATR-percentile is orthogonal to setup quality."
        ),
        "expected_enter_direction": "up",
        "expected_winrate_direction": "flat",
        "risk_if_wrong": (
            "More setups during compressed volatility (ATR ≤25 percentile) "
            "may hit SL before TP when volatility expands. Watch DD."
        ),
        "promotion_criteria": [
            "ENTER count > 53 (V5.0 baseline) AND",
            "win rate (excl timeout) >= 30 % AND",
            "no per-pair regression (USD/JPY net pips not worse than baseline) AND",
            "Red Team 8/8 pass.",
        ],
        "rejection_triggers": [
            "win rate (excl timeout) < 25 % OR",
            "USD/JPY net pips below baseline by > 50 pips OR",
            "drawdown / net pips ratio > 0.6.",
        ],
    }
