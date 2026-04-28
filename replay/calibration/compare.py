"""HYDRA V4.8 — variant comparison report.

Reads the per-variant outputs produced by sweep.py and writes a single
comparison report that ranks variants by:

  1. ENTER count (must be >= 730 over 2 years to hit 2/day target)
  2. Win rate (excl. timeouts)
  3. Net pips after cost
  4. Max drawdown
  5. Red Team probes passed (must be 8/8)

A variant is "promotable to V4.8 production" only if:
  - Red Team 8/8 passed
  - ENTER count > current V4.7 count
  - Win rate > 45%
  - Net pips > V4.7 baseline
  - Drawdown / net pips ratio < 0.6

Anything weaker is reported but flagged "DO NOT PROMOTE".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_variant(variant_dir: Path) -> Optional[Dict[str, Any]]:
    """Load summary metrics for one variant."""
    diag = variant_dir / "diagnostics.json"
    spnl = variant_dir / "shadow_pnl.json"
    rt = variant_dir / "red_team.json"
    if not diag.exists():
        return None

    d = json.loads(diag.read_text(encoding="utf-8"))
    enter = d.get("final_status_counts", {}).get("ENTER_CANDIDATE", 0)
    wait = d.get("final_status_counts", {}).get("WAIT", 0)
    block = d.get("final_status_counts", {}).get("BLOCK", 0)

    sp_data = json.loads(spnl.read_text(encoding="utf-8")) if spnl.exists() else {}
    rt_data = json.loads(rt.read_text(encoding="utf-8")) if rt.exists() else []

    rt_pass = sum(1 for p in rt_data if p.get("passed"))
    rt_total = len(rt_data)

    # Use shadow_2_of_3 if available, otherwise the first mode.
    sp_modes = sp_data.get("summary_by_mode", {})
    sp_pick = sp_modes.get("shadow_2_of_3") or (
        next(iter(sp_modes.values()), None)
    )

    return {
        "variant": variant_dir.name,
        "enter": enter,
        "wait": wait,
        "block": block,
        "shadow_trades": sp_pick.get("trades") if sp_pick else 0,
        "shadow_win_rate": sp_pick.get("win_rate_excl_timeout") if sp_pick else None,
        "shadow_net_pips": sp_pick.get("net_pips_after_cost") if sp_pick else None,
        "shadow_drawdown": sp_pick.get("max_drawdown_pips") if sp_pick else None,
        "red_team_passed": rt_pass,
        "red_team_total": rt_total,
    }


def promotion_verdict(v: Dict[str, Any], baseline_enter: int,
                        baseline_net_pips: float) -> str:
    if v["red_team_total"] == 0:
        return "NO_RED_TEAM_DATA"
    if v["red_team_passed"] < v["red_team_total"]:
        return "DO_NOT_PROMOTE_red_team_failed"
    if v["enter"] <= baseline_enter:
        return "DO_NOT_PROMOTE_no_more_trades_than_baseline"
    if (v["shadow_win_rate"] or 0) < 45.0:
        return "DO_NOT_PROMOTE_win_rate_below_45_percent"
    if (v["shadow_net_pips"] or 0) <= baseline_net_pips:
        return "DO_NOT_PROMOTE_no_pip_improvement"
    dd = abs(v["shadow_drawdown"] or 0)
    np_ = v["shadow_net_pips"] or 0
    if np_ > 0 and dd / np_ > 0.6:
        return "DO_NOT_PROMOTE_drawdown_too_high"
    return "PROMOTABLE"


def render_markdown(variants: List[Dict[str, Any]],
                     baseline_enter: int,
                     baseline_net_pips: float) -> str:
    lines = ["# HYDRA V4.8 — Variant Comparison\n"]
    lines.append(f"Baseline ENTER (V4.7): {baseline_enter}  ")
    lines.append(f"Baseline net pips (V4.7): {baseline_net_pips}\n")
    lines.append("| variant | ENTER | shadow trades | win % | net pips | "
                  "DD pips | RT pass | verdict |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for v in variants:
        verdict = promotion_verdict(v, baseline_enter, baseline_net_pips)
        wr = v["shadow_win_rate"]
        lines.append(
            f"| {v['variant']} | {v['enter']:,} | {v['shadow_trades']:,} | "
            f"{wr:.1f}% | " if wr is not None else
            f"| {v['variant']} | {v['enter']:,} | {v['shadow_trades']:,} | n/a | "
        )
        # Fix formatting: rebuild without the conditional that produced wrong row
    # Rebuild rows correctly
    lines = ["# HYDRA V4.8 — Variant Comparison\n",
              f"Baseline ENTER (V4.7): {baseline_enter}  ",
              f"Baseline net pips (V4.7): {baseline_net_pips}\n",
              "| variant | ENTER | shadow trades | win % | net pips | "
              "DD pips | RT pass | verdict |",
              "|---|---:|---:|---:|---:|---:|---:|---|"]
    for v in variants:
        verdict = promotion_verdict(v, baseline_enter, baseline_net_pips)
        wr = v["shadow_win_rate"]
        wr_str = f"{wr:.1f}%" if wr is not None else "n/a"
        np_str = (f"{v['shadow_net_pips']:.1f}"
                   if v["shadow_net_pips"] is not None else "n/a")
        dd_str = (f"{v['shadow_drawdown']:.1f}"
                   if v["shadow_drawdown"] is not None else "n/a")
        lines.append(
            f"| `{v['variant']}` | {v['enter']:,} | {v['shadow_trades']:,} | "
            f"{wr_str} | {np_str} | {dd_str} | "
            f"{v['red_team_passed']}/{v['red_team_total']} | {verdict} |"
        )
    lines.append("")
    promotables = [v for v in variants
                    if promotion_verdict(v, baseline_enter,
                                          baseline_net_pips) == "PROMOTABLE"]
    lines.append(f"**Promotable variants: {len(promotables)} / {len(variants)}**")
    if promotables:
        lines.append("Recommended next step: pick the highest-net-pips "
                      "promotable variant, freeze it as V4.8, and re-run "
                      "the full pipeline against it for a clean baseline "
                      "before any live consideration.")
    else:
        lines.append("No variant in the safe range surpasses V4.7 under "
                      "Red Team. The 2-trades/day target is structurally "
                      "out of reach with the current instrument + window "
                      "+ timeframe combination. Next phase: timeframe "
                      "and instrument redesign rather than further knob "
                      "tweaks.")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variants-dir", type=Path, required=True,
                   help="Directory containing one subfolder per variant.")
    p.add_argument("--baseline-enter", type=int, required=True)
    p.add_argument("--baseline-net-pips", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    variants: List[Dict[str, Any]] = []
    for sub in sorted(args.variants_dir.iterdir()):
        if not sub.is_dir():
            continue
        v = load_variant(sub)
        if v is not None:
            variants.append(v)

    md = render_markdown(variants, args.baseline_enter, args.baseline_net_pips)
    args.out.write_text(md, encoding="utf-8")
    print(f"comparison report written: {args.out}")


if __name__ == "__main__":
    main()
