"""HYDRA V5.1 — ChartMind internal score parser.

The cycles.jsonl produced by V5.1+ now contains the ChartMind evidence
strings. This module parses them into structured columns and emits a
table that V5.2+ iterations can use as the basis for evidence-backed
ChartMind redesign.

No behaviour change in the orchestrator. Pure post-processing.

Output:
  chartmind_scores.csv   - one row per cycle with chart.evidence
  chartmind_scores.md    - readable summary
  chartmind_scores.json  - aggregate distributions (per-feature)
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


# Regexes targeting the exact format ChartMindV4._evaluate_inner emits.
RE_TREND = re.compile(
    r"trend=(\S+) hh=(\d+) hl=(\d+) lh=(\d+) ll=(\d+) "
    r"ema_slope=([-\d.eE]+) adx=([-\d.eE]+)"
)
RE_ATR = re.compile(r"atr=([-\d.eE]+) atr_pct=([-\d.eE]+) vol=(\S+)")
RE_SETUP = re.compile(r"setup=(\S+) dir=(\S+) reason=(.+?)$")
RE_MTF = re.compile(r"mtf=(\S+) m15=(\S+)")
RE_SWEEP = re.compile(r"sweep=(\S+) dir=(\S+)")
RE_SCORE = re.compile(r"score=(\d+)/(\d+) ev=(\{[^}]*\})")
RE_UPSTREAM = re.compile(r"upstream:news=(\S+) market=(\S+)")


def _iter_cycles(cycles_path: Path) -> Iterator[Dict[str, Any]]:
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
            if "cycle_id" in rec:
                yield rec


def parse_chart_evidence(evidence_list: List[str]) -> Dict[str, Any]:
    """Parse one ChartMind evidence list into structured fields."""
    out: Dict[str, Any] = {
        "trend_label": None, "hh": None, "hl": None, "lh": None, "ll": None,
        "ema_slope": None, "adx": None,
        "atr": None, "atr_pct": None, "vol_state": None,
        "setup_type": None, "chart_dir": None, "setup_reason": None,
        "mtf_reason": None, "mtf_m15": None,
        "sweep": None, "sweep_dir": None,
        "score": None, "score_max": None, "evidence_flags": None,
        "upstream_news": None, "upstream_market": None,
    }
    for s in evidence_list:
        if not isinstance(s, str):
            continue
        m = RE_TREND.search(s)
        if m:
            out["trend_label"] = m.group(1)
            out["hh"] = int(m.group(2))
            out["hl"] = int(m.group(3))
            out["lh"] = int(m.group(4))
            out["ll"] = int(m.group(5))
            out["ema_slope"] = float(m.group(6))
            out["adx"] = float(m.group(7))
            continue
        m = RE_ATR.search(s)
        if m:
            out["atr"] = float(m.group(1))
            out["atr_pct"] = float(m.group(2))
            out["vol_state"] = m.group(3)
            continue
        m = RE_SETUP.search(s)
        if m:
            out["setup_type"] = m.group(1)
            out["chart_dir"] = m.group(2)
            out["setup_reason"] = m.group(3).strip()
            continue
        m = RE_MTF.search(s)
        if m:
            out["mtf_reason"] = m.group(1)
            out["mtf_m15"] = m.group(2)
            continue
        m = RE_SWEEP.search(s)
        if m:
            out["sweep"] = m.group(1)
            out["sweep_dir"] = m.group(2)
            continue
        m = RE_SCORE.search(s)
        if m:
            out["score"] = int(m.group(1))
            out["score_max"] = int(m.group(2))
            out["evidence_flags"] = m.group(3)
            continue
        m = RE_UPSTREAM.search(s)
        if m:
            out["upstream_news"] = m.group(1)
            out["upstream_market"] = m.group(2)
            continue
    return out


def compute(cycles_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    setup_type_counts = Counter()
    chart_dir_counts = Counter()
    score_dist = Counter()
    score_by_dir: Dict[str, List[int]] = defaultdict(list)
    trend_counts = Counter()
    vol_counts = Counter()
    mtf_counts = Counter()

    for rec in _iter_cycles(cycles_path):
        chart = rec.get("chart") or {}
        ev = chart.get("evidence")
        if not ev:
            continue
        parsed = parse_chart_evidence(ev)
        row = {
            "cycle_id": rec.get("cycle_id"),
            "timestamp_utc": rec.get("timestamp_utc"),
            "symbol": rec.get("symbol"),
            "session_status": rec.get("session_status"),
            "final_status": rec.get("final_status"),
            "final_reason": rec.get("final_reason"),
            "chart_decision": chart.get("decision"),
            "chart_grade": chart.get("grade"),
            **parsed,
        }
        rows.append(row)
        if parsed["setup_type"] is not None:
            setup_type_counts[parsed["setup_type"]] += 1
        if parsed["chart_dir"] is not None:
            chart_dir_counts[parsed["chart_dir"]] += 1
        if parsed["score"] is not None:
            score_dist[parsed["score"]] += 1
            if parsed["chart_dir"] in ("long", "short"):
                score_by_dir[parsed["chart_dir"]].append(parsed["score"])
        if parsed["trend_label"] is not None:
            trend_counts[parsed["trend_label"]] += 1
        if parsed["vol_state"] is not None:
            vol_counts[parsed["vol_state"]] += 1
        if parsed["mtf_reason"] is not None:
            mtf_counts[parsed["mtf_reason"]] += 1

    summary = {
        "rows_parsed": len(rows),
        "setup_type_counts": dict(setup_type_counts),
        "chart_dir_counts": dict(chart_dir_counts),
        "score_distribution": dict(score_dist),
        "score_avg_by_dir": {
            d: (sum(s) / len(s) if s else None)
            for d, s in score_by_dir.items()
        },
        "trend_distribution": dict(trend_counts),
        "volatility_distribution": dict(vol_counts),
        "mtf_distribution": dict(mtf_counts),
    }
    return rows, summary


def render_markdown(summary: Dict[str, Any]) -> str:
    lines = ["# ChartMind Internal Score Dump (V5.1)\n"]
    lines.append(f"Rows parsed: **{summary['rows_parsed']:,}**\n")

    lines.append("## Setup type distribution")
    for k, v in summary["setup_type_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## Chart direction distribution")
    for k, v in summary["chart_dir_counts"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## Score distribution (count of cycles per evidence score)")
    for score, n in sorted(summary["score_distribution"].items()):
        lines.append(f"- score={score}: {n:,}")
    lines.append("")

    lines.append("## Average score by directional intent")
    for d, avg in summary["score_avg_by_dir"].items():
        lines.append(f"- {d}: {avg:.2f}" if avg is not None else f"- {d}: n/a")
    lines.append("")

    lines.append("## Trend label distribution")
    for k, v in summary["trend_distribution"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## Volatility state distribution")
    for k, v in summary["volatility_distribution"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")

    lines.append("## MTF reason distribution")
    for k, v in summary["mtf_distribution"].items():
        lines.append(f"- {k}: {v:,}")
    lines.append("")
    return "\n".join(lines)


def run(cycles_path: Path, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, summary = compute(cycles_path)
    # CSV
    if rows:
        with (out_dir / "chartmind_scores.csv").open("w", encoding="utf-8",
                                                      newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    # JSON
    (out_dir / "chartmind_scores.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    # Markdown
    (out_dir / "chartmind_scores.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.cycles, args.out_dir)
    print(f"chartmind score dump written to {args.out_dir}")
