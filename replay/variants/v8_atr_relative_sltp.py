"""V8 — ATR-relative SL/TP in shadow simulator.

V5.0 shadow simulator used SL=20p / TP=40p / max-hold=24 bars. On the 13
real V5.0 ENTER cycles, 7 of 13 were TIMEOUTS — i.e. neither SL nor TP
was hit within 6 hours. That points to TP being too far given the
volatility regime.

Hypothesis: a TP that scales with ATR (e.g. 1.5 * ATR) and SL that
scales with ATR (e.g. 0.75 * ATR) — keeping R:R 2:1 but adapting to
volatility — should:
- Convert most timeouts into wins (TP closer)
- Slightly lower win rate (SL closer too) but raise the WIN/timeout ratio
- Keep the simulator's risk/reward intact

This is NOT a brain change. It's a shadow simulator parameter change
that re-evaluates the SAME 13 V5.0 ENTER cycles with different
SL/TP geometry. If the win rate jumps from 16.7% to >40%, the V5.0
trades aren't bad — they were measured with a wrong yardstick.

The V8 variant therefore changes only `replay/war_room/shadow_pnl.py`
parameters, not the orchestrator or the brains.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v8_atr_relative_sltp"


def apply() -> Tuple[str, Callable[[], None]]:
    from replay.war_room import shadow_pnl as sp

    original_sl = sp.SL_PIPS
    original_tp = sp.TP_PIPS
    original_hold = sp.MAX_HOLD_BARS
    # ATR on EUR/USD M15 averages ~7 pips, on USD/JPY ~10 pips.
    # We use 0.75x and 1.5x of mid-pair median to stay conservative.
    sp.SL_PIPS = 12.0   # ~0.75 * mid-pair ATR
    sp.TP_PIPS = 18.0   # ~1.5  * mid-pair ATR (so R:R 1.5)
    sp.MAX_HOLD_BARS = 16   # 4 hours rather than 6 — shorter hold

    def revert() -> None:
        sp.SL_PIPS = original_sl
        sp.TP_PIPS = original_tp
        sp.MAX_HOLD_BARS = original_hold

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "V5.0's 7-of-13 TIMEOUT rate is symptomatic of TP being too "
            "far given M15 volatility. Tightening SL/TP to ATR-scaled "
            "values should convert most timeouts to wins while keeping "
            "the risk/reward ratio reasonable."
        ),
        "expected_enter_direction": "flat (same setups)",
        "expected_winrate_direction": "up",
        "risk_if_wrong": (
            "Tighter SL gets hit by noise; net pips falls. If timeout "
            "rate is unchanged, the issue is direction, not levels."
        ),
        "promotion_criteria": [
            "Win rate (excl timeout) > 35 % AND",
            "TIMEOUT rate < 30 % AND",
            "Net pips > V5.0 baseline (-58.7) AND",
            "Red Team 8/8.",
        ],
    }
