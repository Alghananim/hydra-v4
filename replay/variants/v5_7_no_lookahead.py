"""V5.7 — negative-control variant for the lookahead question (F-018).

V5.0's runner passes `visible = bars[lo:idx+1]` to the orchestrator,
where `idx` is the index of the bar AT `now_utc`. OANDA bar timestamps
are OPEN times — so the bar at `now_utc` represents the period
[now_utc, now_utc + 15min). Its close, high, low are determined by
events AFTER now_utc. Including it in the visible window gives the
brains 15 minutes of future visibility.

V5.7 fixes this by passing `visible = bars[lo:idx]` (excluding the bar
at now_utc). The brains then make decisions based only on bars whose
data is fully known at now_utc.

If V5.7's results are NOT significantly different from V5.0:
  - The convention was actually correct (now_utc represents the close
    time of bar idx), and the original slice is fine.
  - OR the lookahead exists but doesn't help, because ChartMind's
    setup logic is conservative.

If V5.7's results are significantly different:
  - Confirmed: V5.0 was using lookahead.
  - V5.7 is the honest baseline going forward; all V5.x and V6+
    results must be re-evaluated against V5.7.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_7_no_lookahead"


def apply() -> Tuple[str, Callable[[], None]]:
    # The variant runner reads visible from the runner's main loop.
    # We monkey-patch the slicing logic by replacing the runner's helper
    # (the slicing happens inline in the main loop). For minimal diff,
    # we patch a marker in run_variant_backtest.py that adjusts the
    # +1 / 0 offset.
    #
    # Implementation strategy: insert a flag into run_variant_backtest's
    # global namespace. The runner's main() reads this flag and adjusts
    # `idx + 1` to `idx` if the flag is set.
    import replay.run_variant_backtest as runner

    if not hasattr(runner, "_VARIANT_NO_LOOKAHEAD_OFFSET"):
        runner._VARIANT_NO_LOOKAHEAD_OFFSET = 1  # default
    original = runner._VARIANT_NO_LOOKAHEAD_OFFSET
    runner._VARIANT_NO_LOOKAHEAD_OFFSET = 0  # exclude bar idx

    def revert() -> None:
        runner._VARIANT_NO_LOOKAHEAD_OFFSET = original

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Excluding the bar at now_utc removes any potential lookahead "
            "from the runner's slicing. If V5.0 was secretly benefiting "
            "from lookahead, V5.7 ENTER count and win rate will diverge."
        ),
        "expected_enter_direction": "down (fewer 'lucky' setups) OR flat",
        "expected_winrate_direction": "down (lookahead was helping) OR flat",
        "risk_if_wrong": "If results are unchanged, no harm. The variant "
                          "is the honest no-lookahead baseline.",
        "promotion_criteria": [
            "ENTER count and win rate honest (no lookahead).",
            "If results differ from V5.0 → V5.7 is the new baseline.",
        ],
        "audit_finding": "F-018",
    }
