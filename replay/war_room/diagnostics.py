"""HYDRA 4.7 War Room — Step 1: cycle-data forensics.

Consumes the cycles.jsonl produced by run_v47_backtest.py and emits the
raw evidence required by the investigation brief:

  * total decisions
  * total WAIT / BLOCK / ENTER_CANDIDATE / ORCHESTRATOR_ERROR / errors
  * top-N rejection reasons (final_reason)
  * grade distribution per mind (NewsMind / MarketMind / ChartMind)
  * decision distribution per mind
  * data-quality distribution per mind
  * agreement distribution (which decision triples appear and how often)
  * session distribution (outside_window / pre_open / morning)
  * pair distribution (EUR_USD / USD_JPY)
  * top-N (decision-triple, final_reason) combinations

No fixes, no opinions — just numbers. Saves a JSON file `diagnostics.json`
and a human-readable `diagnostics.md` next to cycles.jsonl.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Tuple


def _iter_cycles(cycles_path: Path) -> Iterator[Dict[str, Any]]:
    # Fail-safe: if the file is missing (e.g. backtest never produced
    # any output), yield nothing rather than crashing. The downstream
    # report will then show empty counts and the runner will continue
    # to write the report skeleton with placeholders.
    if not cycles_path.exists():
        return
    with cycles_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Skip plain error lines that have no cycle structure.
            if "error" in rec and "cycle_id" not in rec:
                continue
            yield rec


def _safe_get(rec: Dict[str, Any], path: Tuple[str, ...]) -> Any:
    cur: Any = rec
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def compute(cycles_path: Path) -> Dict[str, Any]:
    """Walk cycles.jsonl once and accumulate every counter we need."""
    final_status = Counter()
    final_reason = Counter()
    session_status = Counter()
    pair = Counter()
    triples = Counter()                  # (news_dec, market_dec, chart_dec)
    triple_reason = Counter()             # ((triple), final_reason) -> count

    grade_by_mind: Dict[str, Counter] = {
        "NewsMind": Counter(), "MarketMind": Counter(), "ChartMind": Counter()
    }
    decision_by_mind: Dict[str, Counter] = {
        "NewsMind": Counter(), "MarketMind": Counter(), "ChartMind": Counter()
    }
    dq_by_mind: Dict[str, Counter] = {
        "NewsMind": Counter(), "MarketMind": Counter(), "ChartMind": Counter()
    }

    in_window_total = 0
    in_window_block = 0
    in_window_wait = 0
    in_window_enter = 0
    total = 0

    for rec in _iter_cycles(cycles_path):
        total += 1
        fs = rec.get("final_status") or "UNKNOWN"
        fr = rec.get("final_reason") or ""
        ss = rec.get("session_status") or "UNKNOWN"
        sym = rec.get("symbol") or "UNKNOWN"

        final_status[fs] += 1
        final_reason[fr] += 1
        session_status[ss] += 1
        pair[sym] += 1

        if ss != "outside_window":
            in_window_total += 1
            if fs == "BLOCK":
                in_window_block += 1
            elif fs == "WAIT":
                in_window_wait += 1
            elif fs == "ENTER_CANDIDATE":
                in_window_enter += 1

        # Per-mind tallies
        for key, mind in (("news", "NewsMind"), ("market", "MarketMind"),
                           ("chart", "ChartMind")):
            mind_obj = rec.get(key)
            if not isinstance(mind_obj, dict):
                continue
            grade_by_mind[mind][mind_obj.get("grade") or "UNKNOWN"] += 1
            decision_by_mind[mind][mind_obj.get("decision") or "UNKNOWN"] += 1
            dq_by_mind[mind][mind_obj.get("data_quality") or "UNKNOWN"] += 1

        triple = (
            (_safe_get(rec, ("news", "decision")) or "?"),
            (_safe_get(rec, ("market", "decision")) or "?"),
            (_safe_get(rec, ("chart", "decision")) or "?"),
        )
        triples[triple] += 1
        triple_reason[(triple, fr)] += 1

    return {
        "input_file": str(cycles_path),
        "total_records": total,
        "final_status_counts": dict(final_status),
        "final_reason_counts": final_reason.most_common(),
        "session_status_counts": dict(session_status),
        "pair_counts": dict(pair),
        "in_window_breakdown": {
            "total": in_window_total,
            "BLOCK": in_window_block,
            "WAIT": in_window_wait,
            "ENTER_CANDIDATE": in_window_enter,
        },
        "grade_distribution_by_mind": {
            mind: dict(c) for mind, c in grade_by_mind.items()
        },
        "decision_distribution_by_mind": {
            mind: dict(c) for mind, c in decision_by_mind.items()
        },
        "data_quality_distribution_by_mind": {
            mind: dict(c) for mind, c in dq_by_mind.items()
        },
        "top_decision_triples": triples.most_common(20),
        "top_triple_reason_combos": [
            {"triple": list(t), "final_reason": r, "count": n}
            for ((t, r), n) in triple_reason.most_common(30)
        ],
    }


def render_markdown(d: Dict[str, Any]) -> str:
    """Pretty-print the diagnostics dict to a stable markdown layout."""
    lines = []
    lines.append("# HYDRA 4.7 — Step 1 Diagnostics\n")
    lines.append(f"Input: `{d['input_file']}`  ")
    lines.append(f"Total records analysed: **{d['total_records']:,}**\n")

    lines.append("## final_status counts")
    for k, v in d["final_status_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## In-trading-window breakdown")
    iw = d["in_window_breakdown"]
    lines.append(f"- Cycles inside NY pre-open or morning: **{iw['total']:,}**")
    lines.append(f"  - BLOCK: {iw['BLOCK']:,}")
    lines.append(f"  - WAIT:  {iw['WAIT']:,}")
    lines.append(f"  - ENTER_CANDIDATE: {iw['ENTER_CANDIDATE']:,}")
    lines.append("")

    lines.append("## Top final_reason counts")
    for r, c in d["final_reason_counts"][:20]:
        lines.append(f"- `{r or '(blank)'}`: {c:,}")
    lines.append("")

    lines.append("## Session distribution")
    for k, v in d["session_status_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## Pair distribution")
    for k, v in d["pair_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    for label, key in (
        ("Grade distribution by mind", "grade_distribution_by_mind"),
        ("Decision distribution by mind", "decision_distribution_by_mind"),
        ("Data-quality distribution by mind", "data_quality_distribution_by_mind"),
    ):
        lines.append(f"## {label}")
        for mind, sub in d[key].items():
            inner = ", ".join(f"{k}={v:,}" for k, v in sub.items())
            lines.append(f"- {mind}: {inner}")
        lines.append("")

    lines.append("## Top 20 decision triples (news, market, chart)")
    for triple, n in d["top_decision_triples"]:
        lines.append(f"- {tuple(triple)}: {n:,}")
    lines.append("")

    lines.append("## Top 30 (triple, final_reason) combos")
    for row in d["top_triple_reason_combos"]:
        lines.append(
            f"- {tuple(row['triple'])} -> `{row['final_reason'] or '(blank)'}`: "
            f"{row['count']:,}"
        )
    lines.append("")
    return "\n".join(lines)


def run(cycles_path: Path, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = compute(cycles_path)
    (out_dir / "diagnostics.json").write_text(
        json.dumps(d, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "diagnostics.md").write_text(render_markdown(d), encoding="utf-8")
    return d


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=Path, required=True,
                   help="Path to cycles.jsonl from run_v47_backtest.py")
    p.add_argument("--out-dir", type=Path, required=True,
                   help="Directory for diagnostics.json + diagnostics.md")
    args = p.parse_args()
    run(args.cycles, args.out_dir)
    print(f"diagnostics written to {args.out_dir}")
