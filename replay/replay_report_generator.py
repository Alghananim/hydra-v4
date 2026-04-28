"""HYDRA V4 — replay_report_generator.

After a replay run, scan the SmartNoteBook ledger and produce:

  replay_results/REAL_DATA_REPLAY_REPORT.md     (TEMPLATE filled with real numbers)
  replay_results/decision_cycles.csv            (every cycle as a row)
  replay_results/per_brain_accuracy.csv
  replay_results/rejected_trades_shadow.csv
  replay_results/lessons.jsonl

CSV writes use stdlib `csv`. The MD writes a deterministic template
that documents the actual replay window and counts.

We deliberately avoid pandas — stdlib only.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from replay.two_year_replay import ReplayResult

_log = logging.getLogger("replay.report")


def _to_row(rec: Any) -> Dict[str, Any]:
    if is_dataclass(rec):
        return asdict(rec)
    if isinstance(rec, dict):
        return dict(rec)
    return {"unknown_record": str(type(rec).__name__)}


def _stringify(v: Any) -> str:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    return str(v)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(keys)
        for r in rows:
            w.writerow([_stringify(r.get(k, "")) for k in keys])


def _write_md(
    path: Path,
    result: ReplayResult,
    pairs: List[str],
    notes: Optional[List[str]] = None,
) -> None:
    notes = notes or []
    lines: List[str] = []
    lines.append("# HYDRA V4 — Real Data 2-Year Replay Report")
    lines.append("")
    lines.append(f"- Replay start (UTC): {result.start_utc.isoformat() if result.start_utc else '?'}")
    lines.append(f"- Replay end (UTC):   {result.end_utc.isoformat() if result.end_utc else '?'}")
    lines.append(f"- Pairs:              {', '.join(pairs)}")
    lines.append("")
    lines.append("## Cycle counts")
    lines.append(f"- total_cycles:        {result.total_cycles}")
    lines.append(f"- accepted_candidates: {result.accepted_candidates}")
    lines.append(f"- rejected_candidates: {result.rejected_candidates}")
    lines.append(f"- blocks:              {result.blocks}")
    lines.append(f"- ny_session_blocks:   {result.ny_session_blocks}")
    lines.append(f"- errors:              {result.errors}")
    lines.append(f"- shadow_outcomes:     {result.shadow_outcomes_generated}")
    lines.append(f"- lessons_extracted:   {result.lessons_extracted}")
    lines.append("")
    if result.brain_performance:
        lines.append("## Per-brain performance")
        for k, v in sorted(result.brain_performance.items()):
            lines.append(f"- {k}: {v}")
        lines.append("")
    if notes:
        lines.append("## Notes")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_full_report(
    out_dir: Path,
    result: ReplayResult,
    decision_cycles: Iterable[Any],
    rejected_trades: Iterable[Any],
    shadow_outcomes: Iterable[Any],
    lessons: Iterable[Any],
    pairs: List[str],
    notes: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Write all four artefacts. Returns a dict of names → paths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # decision_cycles.csv
    dc_rows = [_to_row(r) for r in decision_cycles]
    dc_path = out_dir / "decision_cycles.csv"
    _write_csv(dc_path, dc_rows)

    # per_brain_accuracy.csv (rolled up from decision_cycles)
    brain_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in dc_rows:
        for brain in ("newsmind_output", "marketmind_output", "chartmind_output"):
            sub = r.get(brain) or {}
            if not isinstance(sub, dict):
                continue
            grade = sub.get("grade", "?")
            brain_counts[brain][f"grade_{grade}"] += 1
            brain_counts[brain]["total"] += 1
    pba_rows: List[Dict[str, Any]] = []
    for b, counts in brain_counts.items():
        row = {"brain": b}
        row.update(counts)
        pba_rows.append(row)
    pba_path = out_dir / "per_brain_accuracy.csv"
    _write_csv(pba_path, pba_rows)

    # rejected_trades_shadow.csv (joined view)
    shadow_rows = [_to_row(r) for r in shadow_outcomes]
    rej_rows = [_to_row(r) for r in rejected_trades]
    by_rej: Dict[str, Dict[str, Any]] = {r["record_id"]: r for r in rej_rows if "record_id" in r}
    joined: List[Dict[str, Any]] = []
    for sr in shadow_rows:
        rt_id = sr.get("rejected_trade_id", "")
        base = dict(by_rej.get(rt_id, {}))
        base.update({f"shadow_{k}": v for k, v in sr.items()})
        joined.append(base)
    rts_path = out_dir / "rejected_trades_shadow.csv"
    _write_csv(rts_path, joined)

    # lessons.jsonl
    lpath = out_dir / "lessons.jsonl"
    with lpath.open("w", encoding="utf-8") as f:
        for L in lessons:
            row = _to_row(L)
            f.write(json.dumps(row, default=str, ensure_ascii=True))
            f.write("\n")

    # md summary
    md_path = out_dir / "REAL_DATA_REPLAY_REPORT.md"
    _write_md(md_path, result, pairs, notes)

    return {
        "decision_cycles_csv": dc_path,
        "per_brain_accuracy_csv": pba_path,
        "rejected_trades_shadow_csv": rts_path,
        "lessons_jsonl": lpath,
        "report_md": md_path,
    }
