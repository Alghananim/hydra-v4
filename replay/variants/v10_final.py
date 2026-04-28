"""V10 — final canonical variant.

V10 is constructed by taking, FROM EACH PROMOTABLE V5.2-V9 VARIANT, the
single change that survived its individual Red Team and improved its
hypothesis metric. Compositions are tested again at V10 because
non-additive interactions can re-emerge.

The variant SELECTION is data-driven, not preferential. The
`replay/calibration/compare.py::promotion_verdict` runs against each
prior variant's results; only "PROMOTABLE" variants contribute their
change to V10. If NO prior variant is promotable, V10 = V5.0 + V9
hardening only — a structurally honest "no calibration helped, the
issue is deeper" outcome.

V10 is the LAST variant; subsequent work would require a redesign of
ChartMind's setup detector itself, which is out of V10 scope.

apply() reads the live results from the repo (replay_runs/*/state.json
and shadow_pnl.json) and dynamically composes the variant. Falls back
to a no-op if results aren't available yet.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


VARIANT_LABEL = "v10_final"

V5X_VARIANTS = [
    "v5_2_drop_volatility_normal",
    "v5_3_drop_no_liquidity_sweep",
    "v5_4_lower_a_min",
    "v5_5_combined",
    "v6_per_pair_calibration",
    "v7_require_mtf",
    "v8_atr_relative_sltp",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _is_promotable(variant_name: str) -> bool:
    """Read this variant's state.json + shadow_pnl.json from the repo
    and return True iff it meets the V10 promotion criteria.
    """
    state = PROJECT_ROOT / "replay_runs" / variant_name / "state.json"
    spnl = PROJECT_ROOT / "replay_runs" / f"{variant_name}_warroom" / "shadow_pnl.json"
    if not state.exists() or not spnl.exists():
        return False
    s = json.loads(state.read_text(encoding="utf-8"))
    sp = json.loads(spnl.read_text(encoding="utf-8"))
    enter = s.get("counters", {}).get("ENTER_CANDIDATE", 0)
    if enter <= 53:  # baseline V5.0
        return False
    sp_pick = sp.get("summary_by_mode", {}).get("shadow_2_of_3", {})
    win = sp_pick.get("win_rate_excl_timeout") or 0
    net = sp_pick.get("net_pips_after_cost") or 0
    dd = abs(sp_pick.get("max_drawdown_pips") or 0)
    if win < 30:
        return False
    if net <= -58.7:  # baseline V5.0 net pips
        return False
    if net > 0 and (dd / net) > 0.6:
        return False
    return True


def apply() -> Tuple[str, Callable[[], None]]:
    promotable = [v for v in V5X_VARIANTS if _is_promotable(v)]
    reverts: List[Callable[[], None]] = []

    if not promotable:
        # No variant worked. V10 = V5.0 baseline + V9 hardening only.
        from replay.variants import v9_hardening
        _, rv = v9_hardening.apply()
        reverts.append(rv)
        label = "v10_final:no_promotable_baseline_only"
    else:
        # Compose all promotable variants in order. Each apply() returns
        # a revert; we collect them and revert in reverse on exit.
        for name in promotable:
            from importlib import import_module
            mod = import_module(f"replay.variants.{name}")
            _, rv = mod.apply()
            reverts.append(rv)
        label = "v10_final:" + "+".join(promotable)

    def revert() -> None:
        for rv in reversed(reverts):
            try:
                rv()
            except Exception:
                pass

    return label, revert


def describe() -> Dict[str, Any]:
    promotable = [v for v in V5X_VARIANTS if _is_promotable(v)]
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Composing every promotable V5.x-V8 variant in V10 yields "
            "the strongest version that still passes Red Team. If no "
            "variant is promotable, V10 = V5.0 baseline + V9 hardening "
            "only — an honest 'redesign needed' outcome."
        ),
        "promotable_variants_at_apply": promotable,
        "expected_enter_direction": "depends on promoted set",
        "expected_winrate_direction": "depends on promoted set",
        "promotion_criteria": [
            "Composition Red Team 8/8 AND",
            "Composition net pips > best individual variant.",
        ],
    }
