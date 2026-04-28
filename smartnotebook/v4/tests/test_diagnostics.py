"""test_diagnostics.py — descriptive stats labeled correctly."""

from __future__ import annotations

from smartnotebook.v4 import diagnostics
from smartnotebook.v4.record_types import RecordType


def test_decision_stats_label_says_descriptive():
    out = diagnostics.descriptive_decision_stats([])
    assert out["label"] == "DESCRIPTIVE_STATS_NOT_PREDICTIVE"


def test_rejection_stats_label_says_descriptive():
    out = diagnostics.descriptive_rejection_stats([])
    assert out["label"] == "DESCRIPTIVE_STATS_NOT_PREDICTIVE"


def test_outcome_stats_label_says_descriptive():
    out = diagnostics.descriptive_outcome_stats([])
    assert out["label"] == "DESCRIPTIVE_STATS_NOT_PREDICTIVE"


def test_decision_stats_count_correct():
    recs = [
        {"record_type": RecordType.DECISION_CYCLE.value, "final_status": "ENTER_CANDIDATE", "blocking_reason": "", "symbol": "EUR_USD", "session_window": "morning_3_5"},
        {"record_type": RecordType.DECISION_CYCLE.value, "final_status": "BLOCK", "blocking_reason": "schema_invalid", "symbol": "EUR_USD"},
        {"record_type": RecordType.DECISION_CYCLE.value, "final_status": "WAIT", "blocking_reason": "", "symbol": "EUR_USD"},
    ]
    out = diagnostics.descriptive_decision_stats(recs)
    assert out["n_total_decision_cycles"] == 3
    assert out["n_enter"] == 1
    assert out["n_block"] == 1
    assert out["n_wait"] == 1


def test_outcome_stats_pnl_aggregation():
    recs = [
        {"record_type": RecordType.TRADE_OUTCOME.value, "outcome_class": "WIN", "pnl": 10.0},
        {"record_type": RecordType.TRADE_OUTCOME.value, "outcome_class": "LOSS", "pnl": -4.0},
        {"record_type": RecordType.TRADE_OUTCOME.value, "outcome_class": "WIN", "pnl": 6.0},
    ]
    out = diagnostics.descriptive_outcome_stats(recs)
    assert out["pnl_total"] == 12.0
    assert out["n_win"] == 2
    assert out["n_loss"] == 1
    assert abs(out["win_rate"] - (2/3)) < 1e-9


def test_rejection_stats_groups_by_reason():
    recs = [
        {"record_type": RecordType.REJECTED_TRADE.value, "rejection_reason": "directional_conflict", "rejecting_mind": "gatemind"},
        {"record_type": RecordType.REJECTED_TRADE.value, "rejection_reason": "directional_conflict", "rejecting_mind": "gatemind"},
        {"record_type": RecordType.REJECTED_TRADE.value, "rejection_reason": "outside_window", "rejecting_mind": "gatemind"},
    ]
    out = diagnostics.descriptive_rejection_stats(recs)
    assert out["n_rejections"] == 3
    assert out["by_reason"]["directional_conflict"] == 2
