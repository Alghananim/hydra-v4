"""SmartNoteBook V4 — reports.

Daily / weekly / per-mind / gate / rejection reports. ALL are
RECOMPUTABLE FROM RAW (R8 enforced) — they take a list of raw records
and return a dict. They never persist anything by themselves; the
orchestrator persists summary records via Storage.append_record.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from smartnotebook.v4 import diagnostics
from smartnotebook.v4.classifier import OutcomeClass
from smartnotebook.v4.notebook_constants import FINAL_ENTER, FINAL_BLOCK, FINAL_WAIT
from smartnotebook.v4.record_types import RecordType


def daily_report(records: Iterable[Dict[str, Any]], date_utc: str) -> Dict[str, Any]:
    """Daily roll-up. `date_utc` is YYYY-MM-DD."""
    day_records = [r for r in records if r.get("timestamp_utc", "").startswith(date_utc)]
    decision_stats = diagnostics.descriptive_decision_stats(day_records)
    outcome_stats = diagnostics.descriptive_outcome_stats(day_records)
    rejection_stats = diagnostics.descriptive_rejection_stats(day_records)

    n_executed = sum(
        1 for r in day_records if r.get("record_type") == RecordType.EXECUTED_TRADE.value
    )

    return {
        "report_type": "DAILY",
        "date_utc": date_utc,
        "n_records": len(day_records),
        "decisions": decision_stats,
        "outcomes": outcome_stats,
        "rejections": rejection_stats,
        "n_executed_trades": n_executed,
    }


def weekly_report(records: Iterable[Dict[str, Any]], iso_year: int, iso_week: int) -> Dict[str, Any]:
    """ISO-week roll-up."""
    target = []
    for r in records:
        ts = r.get("timestamp_utc", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        iy, iw, _ = dt.isocalendar()
        if iy == iso_year and iw == iso_week:
            target.append(r)
    decision_stats = diagnostics.descriptive_decision_stats(target)
    outcome_stats = diagnostics.descriptive_outcome_stats(target)
    return {
        "report_type": "WEEKLY",
        "iso_year": iso_year,
        "iso_week": iso_week,
        "n_records": len(target),
        "decisions": decision_stats,
        "outcomes": outcome_stats,
    }


def mind_report(records: Iterable[Dict[str, Any]], mind_name: str) -> Dict[str, Any]:
    """Per-mind attribution roll-up.

    Reads MIND_PERFORMANCE records produced by the attribution pipeline.
    """
    perf = [
        r for r in records
        if r.get("record_type") == RecordType.MIND_PERFORMANCE.value
        and r.get("mind_name") == mind_name
    ]
    if not perf:
        return {
            "report_type": "MIND",
            "mind_name": mind_name,
            "n_decisions": 0,
            "earned_pnl": 0.0,
            "lucky_pnl": 0.0,
            "n_earned_wins": 0,
            "n_lucky_wins": 0,
            "n_unforced_losses": 0,
        }
    return {
        "report_type": "MIND",
        "mind_name": mind_name,
        "n_decisions": sum(int(r.get("n_decisions", 0)) for r in perf),
        "n_earned_wins": sum(int(r.get("n_earned_wins", 0)) for r in perf),
        "n_lucky_wins": sum(int(r.get("n_lucky_wins", 0)) for r in perf),
        "n_unforced_losses": sum(int(r.get("n_unforced_losses", 0)) for r in perf),
        "earned_pnl": sum(float(r.get("earned_pnl", 0.0)) for r in perf),
        "lucky_pnl": sum(float(r.get("lucky_pnl", 0.0)) for r in perf),
    }


def gate_report(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll-up of GATE_AUDIT records."""
    gate = [
        r for r in records
        if r.get("record_type") == RecordType.GATE_AUDIT.value
    ]
    by_outcome: Dict[str, int] = {}
    by_block_reason: Dict[str, int] = {}
    for r in gate:
        oc = r.get("gate_decision", "")
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        if oc == "BLOCK":
            br = r.get("blocking_reason", "")
            by_block_reason[br] = by_block_reason.get(br, 0) + 1
    return {
        "report_type": "GATE",
        "n_audits": len(gate),
        "by_outcome": by_outcome,
        "by_block_reason": by_block_reason,
    }


def rejection_report(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll-up of REJECTED_TRADE records and their SHADOW_OUTCOME children."""
    rejected = [
        r for r in records
        if r.get("record_type") == RecordType.REJECTED_TRADE.value
    ]
    shadows = [
        r for r in records
        if r.get("record_type") == RecordType.SHADOW_OUTCOME.value
    ]
    n_correct = sum(1 for s in shadows if s.get("was_rejection_correct"))
    n_incorrect = len(shadows) - n_correct
    return {
        "report_type": "REJECTION",
        "n_rejected": len(rejected),
        "n_with_shadow": len(shadows),
        "n_correct_rejections": n_correct,
        "n_incorrect_rejections": n_incorrect,
    }
