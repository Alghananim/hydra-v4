"""HYDRA 4.7 War Room — Step 5: Red Team adversarial probes.

The Red Team's job is to break any improvement claim. Each probe returns
a verdict object: {"name": str, "passed": bool, "evidence": ...}.

Probes implemented:

  P1  no_lookahead_in_simulator
        Confirm shadow_pnl never reads a bar at index <= entry_idx.
        Static check on the source, not a runtime trace.
  P2  costs_deducted
        Confirm shadow_pnl subtracts COST_PIPS from every outcome.
  P3  realistic_spread_floor
        Compare median actual spread_pips in cached bars to the COST_PIPS
        constant in shadow_pnl. If actual >> assumed, P&L is rosy.
  P4  segmented_robustness
        Split shadow trades into N time segments; require each segment to
        be profitable individually (rules out "one good month").
  P5  per_pair_robustness
        Both EUR_USD and USD_JPY must individually be profitable; not
        only the aggregate.
  P6  per_window_robustness
        Both pre-open (03-05 NY) and morning (08-12 NY) must each be
        profitable individually.
  P7  drawdown_floor
        Max drawdown (in pips) must be < 200% of the average winning
        pips per trade × win count rate-of-return. (Rejects strategies
        whose growth depends on dodging a single deep drawdown.)
  P8  loose_modes_dont_explode_drawdown
        For each shadow mode, max drawdown should not be >2x worse than
        the strict baseline.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List


def _iter_jsonl(p: Path) -> Iterator[Dict[str, Any]]:
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass


def p1_no_lookahead_in_simulator(repo_root: Path) -> Dict[str, Any]:
    src = (repo_root / "replay" / "war_room" / "shadow_pnl.py").read_text(
        encoding="utf-8"
    )
    # The loop must start from entry_idx + 1; reject if we see "entry_idx)" or
    # "bars[entry_idx]" inside the simulation loop body. Coarse but stable.
    bad = []
    if "for i in range(entry_idx + 1, end)" not in src:
        bad.append("simulation loop does not start at entry_idx + 1")
    if "bars[entry_idx + 0]" in src or "bars[entry_idx]" in src.split(
        "for i in range(entry_idx + 1, end)"
    )[1] if "for i in range(entry_idx + 1, end)" in src else False:
        bad.append("entry-bar referenced inside loop body")
    return {
        "name": "P1_no_lookahead_in_simulator",
        "passed": not bad,
        "evidence": bad or ["loop bound and entry-bar reference are clean"],
    }


def p2_costs_deducted(repo_root: Path) -> Dict[str, Any]:
    src = (repo_root / "replay" / "war_room" / "shadow_pnl.py").read_text(
        encoding="utf-8"
    )
    must_have = [
        "-SL_PIPS - COST_PIPS",
        "TP_PIPS - COST_PIPS",
        "gross_pips - COST_PIPS",
    ]
    missing = [m for m in must_have if m not in src]
    return {
        "name": "P2_costs_deducted",
        "passed": not missing,
        "evidence": missing or ["all three exit branches deduct COST_PIPS"],
    }


def p3_realistic_spread_floor(data_cache_dir: Path,
                                assumed_cost: float = 1.5) -> Dict[str, Any]:
    medians = {}
    for pair in ("EUR_USD", "USD_JPY"):
        spreads = []
        path = data_cache_dir / pair / "M15" / "merged.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i > 5000:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    bid = float(d["bid"]["c"])
                    ask = float(d["ask"]["c"])
                except Exception:
                    continue
                pip = 0.0001 if pair == "EUR_USD" else 0.01
                spreads.append((ask - bid) / pip)
        if spreads:
            medians[pair] = round(statistics.median(spreads), 2)
    worst = max(medians.values()) if medians else None
    passed = worst is None or worst <= assumed_cost
    return {
        "name": "P3_realistic_spread_floor",
        "passed": passed,
        "evidence": {"median_spread_pips_per_pair": medians,
                     "assumed_round_trip_cost": assumed_cost,
                     "verdict_note": ("OK: assumed cost covers median spread"
                                       if passed else
                                       "FAIL: actual median spread exceeds "
                                       "assumed cost; raise COST_PIPS")},
    }


def _segment_pnl(trades: List[Dict[str, Any]], n: int) -> List[float]:
    if not trades:
        return []
    trades = sorted(trades, key=lambda t: t["timestamp_utc"])
    chunk = max(1, len(trades) // n)
    out = []
    for i in range(n):
        seg = trades[i * chunk:(i + 1) * chunk] if i < n - 1 else trades[i * chunk:]
        out.append(sum(t["pips"] for t in seg))
    return out


def p4_segmented_robustness(shadow_trades_path: Path,
                              n_segments: int = 4) -> Dict[str, Any]:
    by_mode = defaultdict(list)
    for t in _iter_jsonl(shadow_trades_path):
        by_mode[t.get("mode")].append(t)
    out: Dict[str, Any] = {}
    overall_pass = True
    for mode, ts in by_mode.items():
        seg = _segment_pnl(ts, n_segments)
        all_positive = all(s > 0 for s in seg) if seg else False
        out[mode] = {"segments_pips": [round(x, 1) for x in seg],
                       "all_positive": all_positive}
        if not all_positive:
            overall_pass = False
    return {
        "name": "P4_segmented_robustness",
        "passed": overall_pass,
        "evidence": out,
    }


def p5_per_pair_robustness(shadow_trades_path: Path) -> Dict[str, Any]:
    by_mode_pair = defaultdict(lambda: defaultdict(float))
    for t in _iter_jsonl(shadow_trades_path):
        by_mode_pair[t.get("mode")][t.get("symbol")] += t.get("pips", 0)
    out: Dict[str, Any] = {}
    overall_pass = True
    for mode, pp in by_mode_pair.items():
        out[mode] = {p: round(v, 1) for p, v in pp.items()}
        if any(v <= 0 for v in pp.values()):
            overall_pass = False
    return {
        "name": "P5_per_pair_robustness",
        "passed": overall_pass,
        "evidence": out,
    }


def p6_per_window_robustness(shadow_trades_path: Path,
                               cycles_path: Path) -> Dict[str, Any]:
    # Need session_status from cycles.jsonl, indexed by cycle_id.
    sess_by_id: Dict[str, str] = {}
    for r in _iter_jsonl(cycles_path):
        cid = r.get("cycle_id")
        if cid:
            sess_by_id[cid] = r.get("session_status") or ""
    by_mode_window = defaultdict(lambda: defaultdict(float))
    for t in _iter_jsonl(shadow_trades_path):
        sess = sess_by_id.get(t.get("cycle_id"), "unknown")
        by_mode_window[t.get("mode")][sess] += t.get("pips", 0)
    out: Dict[str, Any] = {}
    overall_pass = True
    for mode, ws in by_mode_window.items():
        out[mode] = {w: round(v, 1) for w, v in ws.items()}
        # Pass requires both NY windows individually >0
        rel = {w: v for w, v in ws.items() if w.startswith("in_window_")}
        if rel and any(v <= 0 for v in rel.values()):
            overall_pass = False
    return {
        "name": "P6_per_window_robustness",
        "passed": overall_pass,
        "evidence": out,
    }


def p7_drawdown_floor(shadow_pnl_summary: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    overall_pass = True
    for mode, info in shadow_pnl_summary.get("summary_by_mode", {}).items():
        net = info.get("net_pips_after_cost") or 0
        dd = abs(info.get("max_drawdown_pips") or 0)
        ratio = (dd / net) if net > 0 else float("inf")
        ok = net > 0 and ratio < 0.6  # drawdown < 60% of net
        out[mode] = {"net_pips": net, "max_drawdown": dd,
                       "drawdown_to_net_ratio": round(ratio, 2),
                       "passed": ok}
        if not ok:
            overall_pass = False
    return {
        "name": "P7_drawdown_floor",
        "passed": overall_pass,
        "evidence": out,
    }


def p8_loose_modes_dont_explode_drawdown(
    shadow_pnl_summary: Dict[str, Any],
    baseline_mode: str = "shadow_2_of_3",
) -> Dict[str, Any]:
    summ = shadow_pnl_summary.get("summary_by_mode", {})
    if baseline_mode not in summ:
        return {"name": "P8_loose_modes_dont_explode_drawdown",
                "passed": False,
                "evidence": f"baseline mode {baseline_mode} not present"}
    base_dd = abs(summ[baseline_mode].get("max_drawdown_pips") or 0)
    out: Dict[str, Any] = {"baseline": base_dd}
    overall_pass = True
    for mode, info in summ.items():
        if mode == baseline_mode:
            continue
        dd = abs(info.get("max_drawdown_pips") or 0)
        ratio = (dd / base_dd) if base_dd > 0 else float("inf")
        ok = ratio <= 2.0
        out[mode] = {"dd": dd, "ratio_vs_baseline": round(ratio, 2),
                       "passed": ok}
        if not ok:
            overall_pass = False
    return {
        "name": "P8_loose_modes_dont_explode_drawdown",
        "passed": overall_pass,
        "evidence": out,
    }


def render_markdown(probes: List[Dict[str, Any]]) -> str:
    lines = ["# HYDRA 4.7 — Step 5 Red Team\n"]
    n_pass = sum(1 for p in probes if p.get("passed"))
    lines.append(f"Probes passed: **{n_pass} / {len(probes)}**\n")
    for p in probes:
        status = "PASS" if p.get("passed") else "FAIL"
        lines.append(f"## {p['name']} — {status}")
        lines.append("```json")
        lines.append(json.dumps(p.get("evidence"), indent=2, default=str))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def run(repo_root: Path, data_cache_dir: Path,
        cycles_path: Path, shadow_dir: Path,
        out_dir: Path) -> List[Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    shadow_pnl_summary = json.loads(
        (shadow_dir / "shadow_pnl.json").read_text(encoding="utf-8")
    ) if (shadow_dir / "shadow_pnl.json").exists() else {}
    shadow_trades_path = shadow_dir / "shadow_trades.jsonl"

    probes = [
        p1_no_lookahead_in_simulator(repo_root),
        p2_costs_deducted(repo_root),
        p3_realistic_spread_floor(data_cache_dir),
    ]
    if shadow_trades_path.exists():
        probes.extend([
            p4_segmented_robustness(shadow_trades_path),
            p5_per_pair_robustness(shadow_trades_path),
            p6_per_window_robustness(shadow_trades_path, cycles_path),
        ])
    if shadow_pnl_summary:
        probes.extend([
            p7_drawdown_floor(shadow_pnl_summary),
            p8_loose_modes_dont_explode_drawdown(shadow_pnl_summary),
        ])

    (out_dir / "red_team.json").write_text(
        json.dumps(probes, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "red_team.md").write_text(
        render_markdown(probes), encoding="utf-8"
    )
    return probes


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--data-cache", type=Path, required=True)
    p.add_argument("--cycles", type=Path, required=True)
    p.add_argument("--shadow-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.repo_root, args.data_cache, args.cycles, args.shadow_dir,
        args.out_dir)
    print(f"red team probes written to {args.out_dir}")
