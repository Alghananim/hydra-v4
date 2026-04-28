"""SmartNoteBook V4 — diagnostics (descriptive stats only).

REBRANDED from V3's `pattern_detector.py`. The V3 version implied causal
"pattern" discovery; this V4 version is honest — it only computes
DESCRIPTIVE statistics from the raw ledger and labels them as such.

No predictions. No causal claims. Just counts and aggregates that the
operator can use to build hypotheses.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List

from smartnotebook.v4.notebook_constants import (
    FINAL_BLOCK,
    FINAL_ENTER,
    FINAL_WAIT,
)
from smartnotebook.v4.record_types import RecordType


def descriptive_decision_stats(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts of decision-cycle outcomes.

    This is descriptive ONLY — it does not predict anything.
    """
    n_total = 0
    n_enter = 0
    n_block = 0
    n_wait = 0
    block_reasons: Counter = Counter()
    symbols: Counter = Counter()
    sessions: Counter = Counter()
    for r in records:
        if r.get("record_type") != RecordType.DECISION_CYCLE.value:
            continue
        n_total += 1
        status = r.get("final_status", "")
        if status == FINAL_ENTER:
            n_enter += 1
        elif status == FINAL_BLOCK:
            n_block += 1
            br = r.get("blocking_reason", "")
            if br:
                block_reasons[br] += 1
        elif status == FINAL_WAIT:
            n_wait += 1
        sym = r.get("symbol", "")
        if sym:
            symbols[sym] += 1
        sw = r.get("session_window", "")
        if sw:
            sessions[sw] += 1
    return {
        "label": "DESCRIPTIVE_STATS_NOT_PREDICTIVE",
        "n_total_decision_cycles": n_total,
        "n_enter": n_enter,
        "n_block": n_block,
        "n_wait": n_wait,
        "top_block_reasons": block_reasons.most_common(10),
        "by_symbol": dict(symbols),
        "by_session": dict(sessions),
    }


def descriptive_rejection_stats(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Counts of rejection reasons across REJECTED_TRADE records."""
    reasons: Counter = Counter()
    rejecting: Counter = Counter()
    n = 0
    for r in records:
        if r.get("record_type") != RecordType.REJECTED_TRADE.value:
            continue
        n += 1
        reasons[r.get("rejection_reason", "")] += 1
        rejecting[r.get("rejecting_mind", "")] += 1
    return {
        "label": "DESCRIPTIVE_STATS_NOT_PREDICTIVE",
        "n_rejections": n,
        "by_reason": dict(reasons),
        "by_rejecting_mind": dict(rejecting),
    }


def descriptive_outcome_stats(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate PnL across TRADE_OUTCOME records."""
    n = 0
    n_win = 0
    n_loss = 0
    n_be = 0
    pnl_sum = 0.0
    pnl_max = float("-inf")
    pnl_min = float("inf")
    for r in records:
        if r.get("record_type") != RecordType.TRADE_OUTCOME.value:
            continue
        n += 1
        oc = r.get("outcome_class", "")
        pnl = float(r.get("pnl", 0.0))
        pnl_sum += pnl
        if pnl > pnl_max:
            pnl_max = pnl
        if pnl < pnl_min:
            pnl_min = pnl
        if oc == "WIN":
            n_win += 1
        elif oc == "LOSS":
            n_loss += 1
        else:
            n_be += 1
    if n == 0:
        return {
            "label": "DESCRIPTIVE_STATS_NOT_PREDICTIVE",
            "n_outcomes": 0,
            "pnl_total": 0.0,
            "pnl_avg": 0.0,
            "pnl_max": 0.0,
            "pnl_min": 0.0,
            "win_rate": 0.0,
        }
    return {
        "label": "DESCRIPTIVE_STATS_NOT_PREDICTIVE",
        "n_outcomes": n,
        "n_win": n_win,
        "n_loss": n_loss,
        "n_breakeven": n_be,
        "pnl_total": pnl_sum,
        "pnl_avg": pnl_sum / n,
        "pnl_max": pnl_max,
        "pnl_min": pnl_min,
        "win_rate": n_win / n,
    }
