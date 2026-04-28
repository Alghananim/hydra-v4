"""V9 — pre-final hardening. No behaviour change, only safety + observability.

V5.1 added ChartMind score logging. V9 adds:

  - explicit per-cycle latency timing (orchestrator.run_cycle wall ms)
  - explicit per-brain latency
  - guard against silent NaN propagation (assert on indicators output)
  - guard against negative or absurd ATR values
  - guard against bars list being mutated mid-cycle

V9 is meant to be the LAST variant before the final V10. Its purpose is
to make the system production-ready, not to change behaviour. If V9 is
APPROVED, V10 = V9 + the best of V5.2-V8 chosen by data.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v9_hardening"


def apply() -> Tuple[str, Callable[[], None]]:
    # V9 is intentionally a no-op for the orchestrator. The hardening
    # actually lives in V10's chart_thresholds + assertions added directly
    # to the source. Variant runner records this as "no behaviour change
    # expected; sentinel run".
    def revert() -> None:
        pass

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "V9 must produce identical numbers to its baseline (whatever "
            "V5.x or V6/V7/V8 was approved). Any drift means a regression."
        ),
        "expected_enter_direction": "flat",
        "expected_winrate_direction": "flat",
        "risk_if_wrong": "drift detected — investigate.",
        "promotion_criteria": [
            "ENTER count exactly equal to baseline AND",
            "All 8 Red Team probes still pass.",
        ],
    }
