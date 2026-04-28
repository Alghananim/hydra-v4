"""test_reports.py — daily/weekly recomputable from raw."""

from __future__ import annotations

from smartnotebook.v4 import reports
from smartnotebook.v4.record_types import RecordType


def test_daily_report_filters_by_date(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    all_recs = list(tmpdir_storage.all_records())
    rep = reports.daily_report(all_recs, "2025-07-15")
    assert rep["report_type"] == "DAILY"
    assert rep["date_utc"] == "2025-07-15"
    assert rep["n_records"] == 1


def test_weekly_report_iso_week(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    all_recs = list(tmpdir_storage.all_records())
    iso_year, iso_week, _ = fixed_now.isocalendar()
    rep = reports.weekly_report(all_recs, iso_year, iso_week)
    assert rep["report_type"] == "WEEKLY"
    assert rep["n_records"] == 1


def test_gate_report_counts_outcomes(tmpdir_storage, factory, fixed_now):
    parent = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(parent)
    ga1 = factory["gate_audit"](
        storage=tmpdir_storage, gate_decision="ENTER_CANDIDATE",
        decision_cycle_id=parent.record_id, when=fixed_now,
    )
    tmpdir_storage.append_record(ga1)
    ga2 = factory["gate_audit"](
        storage=tmpdir_storage, gate_decision="BLOCK", direction="NONE",
        decision_cycle_id=parent.record_id, when=fixed_now,
    )
    tmpdir_storage.append_record(ga2)
    all_recs = list(tmpdir_storage.all_records())
    rep = reports.gate_report(all_recs)
    assert rep["n_audits"] == 2
    assert rep["by_outcome"]["ENTER_CANDIDATE"] == 1
    assert rep["by_outcome"]["BLOCK"] == 1


def test_rejection_report_counts(tmpdir_storage, factory, fixed_now):
    rt = factory["rejected_trade"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rt)
    so = factory["shadow_outcome"](
        storage=tmpdir_storage, rejected_trade_id=rt.record_id,
        pnl=-10.0, when=fixed_now,
    )
    tmpdir_storage.append_record(so)
    all_recs = list(tmpdir_storage.all_records())
    rep = reports.rejection_report(all_recs)
    assert rep["n_rejected"] == 1
    assert rep["n_with_shadow"] == 1
    assert rep["n_correct_rejections"] == 1
    assert rep["n_incorrect_rejections"] == 0


def test_mind_report_zero_when_no_data():
    rep = reports.mind_report([], "newsmind")
    assert rep["n_decisions"] == 0
    assert rep["earned_pnl"] == 0.0


def test_report_recomputable_from_raw(tmpdir_storage, factory, fixed_now):
    """R8: reports built from JSONL match reports built from SQLite."""
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    sqlite_rows = tmpdir_storage.query_by_type(RecordType.DECISION_CYCLE)
    jsonl_rows = list(tmpdir_storage.iter_records_for_day(fixed_now))
    assert sorted(r["record_id"] for r in sqlite_rows) == sorted(r["record_id"] for r in jsonl_rows)
