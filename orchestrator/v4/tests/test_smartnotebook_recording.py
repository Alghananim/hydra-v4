"""HYDRA V4 — SmartNoteBook recording tests.

Verify that for every cycle, exactly:
  * 1 DECISION_CYCLE record is written
  * 1 GATE_AUDIT record is written
  * GATE_AUDIT.parent_record_id == DECISION_CYCLE.record_id
  * GATE_AUDIT.audit_id == gate_decision.audit_id
  * The DECISION_CYCLE carries snapshots of all 4 brain outputs
"""

from __future__ import annotations

from smartnotebook.v4.record_types import RecordType


def test_decision_cycle_recorded(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    assert len(rows) == 1
    assert rows[0]["record_id"] == res.decision_cycle_record_id


def test_gate_audit_recorded(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    rows = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert len(rows) == 1
    assert rows[0]["record_id"] == res.gate_audit_record_id


def test_gate_audit_parent_links_to_decision_cycle(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    audits = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert audits[0]["parent_record_id"] == res.decision_cycle_record_id


def test_gate_audit_id_matches_gate_decision(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    audits = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert audits[0]["audit_id"] == res.gate_decision.audit_id


def test_decision_cycle_carries_all_brain_snapshots(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    rec = rows[0]
    assert rec["newsmind_output"]["brain_name"] == "newsmind"
    assert rec["marketmind_output"]["brain_name"] == "marketmind"
    assert rec["chartmind_output"]["brain_name"] == "chartmind"
    assert rec["gatemind_output"]["gate_decision"] == "ENTER_CANDIDATE"


def test_two_cycles_produce_two_pairs_of_records(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    for _ in range(2):
        orch.run_cycle(
            symbol="EUR_USD",
            now_utc=bundle_aplus_buy["now_utc"],
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )
    dcr_rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    gar_rows = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert len(dcr_rows) == 2
    assert len(gar_rows) == 2
