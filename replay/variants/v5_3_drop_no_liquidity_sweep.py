"""V5.3 — drop the `no_liquidity_sweep` evidence flag.

Hypothesis: `no_liquidity_sweep` excludes setups right after a stop hunt.
But stop hunts are exactly when many trapped traders' stops trigger and
real moves originate (Wyckoff shake-out / spring). Excluding these may
filter out the highest-quality setups.

Change: drop `no_liquidity_sweep` from EVIDENCE_KEYS. The
`liquidity_sweep` detector still runs (its result still appears in
risk_flags and SmartNoteBook audit), but it stops contributing to the
grade score.

Risk if hypothesis wrong: post-sweep cycles often retrace; we may
trade into noise. Mitigation in the variant report: per-bar timing
analysis after sweep events.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_3_drop_no_liquidity_sweep"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import chart_thresholds as ct
    original_keys = ct.EVIDENCE_KEYS
    ct.EVIDENCE_KEYS = tuple(k for k in original_keys if k != "no_liquidity_sweep")

    def revert() -> None:
        ct.EVIDENCE_KEYS = original_keys

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "`no_liquidity_sweep` excludes high-quality post-shakeout "
            "setups. Removing it should raise ENTER count and possibly "
            "improve win rate."
        ),
        "expected_enter_direction": "up",
        "expected_winrate_direction": "flat or up",
        "risk_if_wrong": (
            "Post-sweep cycles can keep extending; we may trade into "
            "the noise of the sweep rather than the recovery."
        ),
        "promotion_criteria": [
            "ENTER count > 53 (V5.0 baseline) AND",
            "win rate (excl timeout) >= 30 % AND",
            "Red Team 8/8 pass.",
        ],
    }
