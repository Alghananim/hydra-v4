"""HYDRA 4.7 War Room — Step 2: bottleneck attribution.

Question the brief asks: which mind blocks how often, and at which gate.

We attribute each non-ENTER cycle to the **first** stop along the gate
ladder, in this order (matches the actual orchestrator flow):

  1. session_outside_window      -> "session"
  2. data_stale / data_missing   -> attributed to whichever mind reported
                                    data_quality != "good"
  3. should_block (any mind)     -> attributed to that mind ("brain_block")
  4. grade < A                   -> attributed to whichever mind has the
                                    lowest grade (or "tie" if multiple)
  5. consensus rejection
       directional_conflict      -> "news_or_market_opposition"
       incomplete_agreement      -> "chart_unsure"
       any_block                 -> "brain_block_in_consensus"
  6. unanimous_wait              -> "all_three_wait"
  7. anything else               -> "other"

The output is a counter and a percentage breakdown per attribution
category, separated by pair and by session window.

This does NOT change the orchestrator. It only labels what already
happened in cycles.jsonl. The labels are conservative: if we cannot tell,
we say "other" rather than guess.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional


GRADE_ORDER = {"A+": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5, "BLOCK": 99}


def _iter_cycles(cycles_path: Path) -> Iterator[Dict[str, Any]]:
    with cycles_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "cycle_id" in rec:
                yield rec


def _grade_rank(g: Optional[str]) -> int:
    if g is None:
        return 100
    return GRADE_ORDER.get(g, 50)


def _attribute(rec: Dict[str, Any]) -> str:
    fs = rec.get("final_status")
    fr = rec.get("final_reason") or ""
    ss = rec.get("session_status")

    if fs == "ENTER_CANDIDATE":
        return "ENTER_CANDIDATE"

    if ss == "outside_window":
        return "session_outside_window"

    minds = {
        "NewsMind": rec.get("news") or {},
        "MarketMind": rec.get("market") or {},
        "ChartMind": rec.get("chart") or {},
    }

    # Data quality
    bad_dq = [m for m, mind in minds.items()
              if mind.get("data_quality") not in (None, "good")]
    if bad_dq and "data" in fr.lower():
        return f"data_quality:{','.join(bad_dq)}"

    # Should-block
    blocked_minds = [m for m, mind in minds.items()
                     if mind.get("should_block") is True
                     or mind.get("decision") == "BLOCK"]
    if blocked_minds:
        return f"brain_block:{','.join(blocked_minds)}"

    # Grade
    if "grade" in fr.lower() or fr in ("grade_below_threshold", ):
        ranks = {m: _grade_rank(mind.get("grade")) for m, mind in minds.items()
                 if mind}
        if ranks:
            worst = max(ranks.values())
            offenders = [m for m, r in ranks.items() if r == worst]
            return f"grade_below_A:{','.join(offenders)}"
        return "grade_below_A:unknown"

    # Consensus
    if fr == "directional_conflict":
        return "consensus:directional_conflict"
    if fr == "incomplete_agreement":
        return "consensus:incomplete_agreement"
    if fr == "brain_block":
        return "consensus:brain_block"
    if fr == "unanimous_wait" or fs == "WAIT":
        return "consensus:unanimous_wait"

    return f"other:{fr or 'no_reason'}"


def compute(cycles_path: Path) -> Dict[str, Any]:
    counts = Counter()
    counts_by_pair = defaultdict(Counter)
    counts_by_window = defaultdict(Counter)

    total = 0
    in_window = 0
    for rec in _iter_cycles(cycles_path):
        total += 1
        label = _attribute(rec)
        counts[label] += 1
        counts_by_pair[rec.get("symbol") or "UNKNOWN"][label] += 1
        ss = rec.get("session_status") or "unknown"
        counts_by_window[ss][label] += 1
        if ss != "outside_window":
            in_window += 1

    def to_pct(c: Counter, denom: int) -> Dict[str, Dict[str, float]]:
        return {
            k: {
                "count": v,
                "pct_of_total": (v / denom * 100.0) if denom else 0.0,
            }
            for k, v in c.most_common()
        }

    return {
        "total_records": total,
        "in_window_records": in_window,
        "attribution": to_pct(counts, total),
        "attribution_by_pair": {
            p: to_pct(c, sum(c.values())) for p, c in counts_by_pair.items()
        },
        "attribution_by_window": {
            w: to_pct(c, sum(c.values())) for w, c in counts_by_window.items()
        },
    }


def render_markdown(d: Dict[str, Any]) -> str:
    lines = ["# HYDRA 4.7 — Step 2 Bottleneck Attribution\n"]
    lines.append(f"Total records: {d['total_records']:,}  ")
    lines.append(f"In-window records: {d['in_window_records']:,}\n")

    lines.append("## Attribution (whole population)")
    lines.append("| label | count | % |")
    lines.append("|---|---:|---:|")
    for label, info in d["attribution"].items():
        lines.append(f"| {label} | {info['count']:,} | {info['pct_of_total']:.2f}% |")
    lines.append("")

    for window in ("in_window_pre_open", "in_window_morning"):
        if window in d["attribution_by_window"]:
            lines.append(f"## Attribution — {window}")
            lines.append("| label | count | % |")
            lines.append("|---|---:|---:|")
            for label, info in d["attribution_by_window"][window].items():
                lines.append(
                    f"| {label} | {info['count']:,} | {info['pct_of_total']:.2f}% |"
                )
            lines.append("")

    for pair, breakdown in d["attribution_by_pair"].items():
        lines.append(f"## Attribution — {pair}")
        lines.append("| label | count | % |")
        lines.append("|---|---:|---:|")
        for label, info in breakdown.items():
            lines.append(
                f"| {label} | {info['count']:,} | {info['pct_of_total']:.2f}% |"
            )
        lines.append("")

    return "\n".join(lines)


def run(cycles_path: Path, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = compute(cycles_path)
    (out_dir / "bottleneck_attribution.json").write_text(
        json.dumps(d, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "bottleneck_attribution.md").write_text(
        render_markdown(d), encoding="utf-8"
    )
    return d


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.cycles, args.out_dir)
    print(f"bottleneck attribution written to {args.out_dir}")
