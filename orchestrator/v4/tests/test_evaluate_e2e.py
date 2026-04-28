"""HYDRA V4 — 15 integration scenarios for orchestrator -> GateMind.

Each scenario builds a (news, market, chart) bundle, runs a full mock
orchestrator cycle, and asserts the GateMind verdict propagated to the
DecisionCycleResult.
"""

from __future__ import annotations

from contracts.brain_output import BrainGrade

from orchestrator.v4.orchestrator_constants import (
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_WAIT,
)


def _run(tmp_path, news, market, chart, when, bars, make_mock):
    orch, *_ = make_mock(tmp_path,
                          news_out=news, market_out=market, chart_out=chart)
    return orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars["bars_by_pair"],
        bars_by_tf=bars["bars_by_tf"],
    )


# ---------------------------------------------------------------------------
# 1. All A+ BUY in NY window -> ENTER_CANDIDATE
# ---------------------------------------------------------------------------
def test_01_all_aplus_buy_in_window(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_ENTER_CANDIDATE
    assert res.gate_decision.gate_decision.value == "ENTER_CANDIDATE"
    assert res.gate_decision.direction.value == "BUY"


# ---------------------------------------------------------------------------
# 2. All A SELL in NY window -> ENTER_CANDIDATE
# ---------------------------------------------------------------------------
def test_02_all_a_sell_in_window(
    tmp_path, in_window_1, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="SELL", grade=BrainGrade.A,
                              when=in_window_1)
    m = make_market_state_fn(decision="SELL", grade=BrainGrade.A, when=in_window_1)
    c = make_chart_assessment_fn(decision="SELL", grade=BrainGrade.A, when=in_window_1)
    res = _run(tmp_path, n, m, c, in_window_1, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_ENTER_CANDIDATE
    assert res.gate_decision.direction.value == "SELL"


# ---------------------------------------------------------------------------
# 3. Mixed A and A+ BUY -> ENTER_CANDIDATE
# ---------------------------------------------------------------------------
def test_03_mixed_a_aplus_buy(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_ENTER_CANDIDATE


# ---------------------------------------------------------------------------
# 4. All WAIT -> WAIT
# ---------------------------------------------------------------------------
def test_04_all_wait(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="WAIT", grade=BrainGrade.A,
                              when=in_window_2)
    m = make_market_state_fn(decision="WAIT", grade=BrainGrade.A, when=in_window_2)
    c = make_chart_assessment_fn(decision="WAIT", grade=BrainGrade.A, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_WAIT


# ---------------------------------------------------------------------------
# 5. 2 BUY + 1 WAIT -> BLOCK incomplete_agreement
# ---------------------------------------------------------------------------
def test_05_two_buy_one_wait(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="WAIT", grade=BrainGrade.A_PLUS, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_BLOCK
    assert "incomplete_agreement" in res.final_reason


# ---------------------------------------------------------------------------
# 6. 2 BUY + 1 SELL -> BLOCK directional_conflict
# ---------------------------------------------------------------------------
def test_06_two_buy_one_sell(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="SELL", grade=BrainGrade.A_PLUS, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_BLOCK
    assert "directional_conflict" in res.final_reason


# ---------------------------------------------------------------------------
# 7. ChartMind grade=B -> BLOCK grade_below_threshold
# ---------------------------------------------------------------------------
def test_07_chartmind_grade_b(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    # B grade requires data_quality != "good" (BrainOutput contract)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.B,
                                  data_quality="stale", when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_BLOCK
    assert "grade_below_threshold" in res.final_reason


# ---------------------------------------------------------------------------
# 8. NewsMind kill_flag -> BLOCK kill_flag_active or brain_block
# ---------------------------------------------------------------------------
def test_08_news_kill_flag(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              risk_flags=["news_blackout"], when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    res = _run(tmp_path, n, m, c, in_window_2, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_BLOCK
    reason = res.final_reason
    assert ("kill_flag_active" in reason) or ("brain_block" in reason)


# ---------------------------------------------------------------------------
# 9. ChartMind returns a non-BrainOutput object (not a real schema_invalid
#    test — this exercises the orchestrator's stronger isinstance safety
#    net which raises MissingBrainOutputError BEFORE GateMind's R1 fires).
#    See test_16 for the actual GateMind R1_schema BLOCK path end-to-end.
# ---------------------------------------------------------------------------
def test_09_chart_returns_invalid_brain_output_type(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Build a chart output that LOOKS like a ChartAssessment but is in
    fact a non-BrainOutput object. The orchestrator's isinstance check
    raises MissingBrainOutputError before GateMind ever sees it — that's
    the build-integrity safety net (stronger than R1_schema)."""

    class _Counterfeit:
        # Has BrainOutput-like attributes but is NOT a BrainOutput instance
        brain_name = "chartmind"
        decision = "BUY"
        grade = "A+"     # wrong type — should be Enum
        reason = "fake"
        evidence = ["x"]
        data_quality = "good"
        should_block = False
        risk_flags: list = []
        confidence = 0.9

        def __init__(self, when):
            from datetime import datetime, timezone
            self.timestamp_utc = when

    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    bad_chart = _Counterfeit(in_window_2)

    # The orchestrator's MissingBrainOutputError fires because bad_chart
    # is not isinstance BrainOutput. That's the stronger-than-schema_invalid
    # safety net.
    import pytest
    from orchestrator.v4.orchestrator_errors import MissingBrainOutputError

    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m,
        # Pass a real chart so the mock builds, then swap the fake brain
        # in directly via the chartmind handle.
        chart_out=make_chart_assessment_fn(when=in_window_2),
    )

    class FakeChartMind:
        def evaluate(self, *a, **kw):
            return bad_chart
    orch.chartmind = FakeChartMind()

    with pytest.raises(MissingBrainOutputError):
        orch.run_cycle(
            symbol="EUR_USD",
            now_utc=in_window_2,
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )


# ---------------------------------------------------------------------------
# 10. Outside NY window -> BLOCK outside_new_york_trading_window
# ---------------------------------------------------------------------------
def test_10_outside_ny_window(
    tmp_path, outside_window, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=outside_window)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=outside_window)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=outside_window)
    res = _run(tmp_path, n, m, c, outside_window, bars_input, make_mock_orchestrator_fn)
    assert res.final_status == FINAL_BLOCK
    assert "outside_new_york_trading_window" in res.final_reason


# ---------------------------------------------------------------------------
# 11. SmartNoteBook records DECISION_CYCLE with all 4 brain snapshots intact
# ---------------------------------------------------------------------------
def test_11_decision_cycle_carries_4_snapshots(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    from smartnotebook.v4.record_types import RecordType
    rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    rec = rows[0]
    for k in ("newsmind_output", "marketmind_output",
              "chartmind_output", "gatemind_output"):
        assert rec[k]
    assert rec["gatemind_output"]["gate_decision"] == "ENTER_CANDIDATE"


# ---------------------------------------------------------------------------
# 12. SmartNoteBook GATE_AUDIT.audit_id matches gate_decision.audit_id
# ---------------------------------------------------------------------------
def test_12_gate_audit_id_consistency(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    from smartnotebook.v4.record_types import RecordType
    rows = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert rows[0]["audit_id"] == res.gate_decision.audit_id


# ---------------------------------------------------------------------------
# 13. cycle_id is unique across two consecutive cycles
# ---------------------------------------------------------------------------
def test_13_cycle_id_unique(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    r1 = orch.run_cycle(
        symbol="EUR_USD", now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    r2 = orch.run_cycle(
        symbol="EUR_USD", now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert r1.cycle_id != r2.cycle_id


# ---------------------------------------------------------------------------
# 14. Orchestrator never writes to disk outside SmartNoteBook
# ---------------------------------------------------------------------------
def test_14_orchestrator_writes_only_via_smartnotebook(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Snapshot tmp_path BEFORE the cycle. Run the cycle. Verify the only
    NEW files / dirs that appeared live under tmp_path/ledger/.
    """
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )

    before = set(p for p in tmp_path.rglob("*"))

    orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )

    after = set(p for p in tmp_path.rglob("*"))
    new_paths = after - before

    expected_root = tmp_path / "ledger"
    bad = [p for p in new_paths
           if expected_root not in p.parents and p != expected_root]
    assert not bad, f"unexpected writes outside ledger: {bad}"


# ---------------------------------------------------------------------------
# 16. Real schema_invalid: a BrainOutput that passes BrainOutput.__post_init__
#     but is mutated post-construction so that GateMind's R1_schema
#     validator rejects it. The orchestrator's isinstance check passes
#     (the object IS a BrainOutput); GateMind's R1 catches the violation
#     and emits BLOCK schema_invalid. This is the missing real R1 path
#     that test_09 was supposed to exercise but didn't (Multi-Reviewer O4).
# ---------------------------------------------------------------------------
def test_16_real_schema_invalid_propagates_to_block(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Mutate a freshly-built BrainOutput so that R1_schema rejects it.

    BrainOutput is a non-frozen dataclass: post-init invariants pass,
    but a downstream consumer that mutates fields can drift the contract.
    GateMind's R1 schema validator is exactly the defence-in-depth layer
    that catches this — and we prove it propagates as BLOCK schema_invalid
    end-to-end through the orchestrator.
    """
    from orchestrator.v4.orchestrator_constants import FINAL_BLOCK as _BLOCK

    n = make_brain_output_fn(
        "newsmind", decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2,
    )
    m = make_market_state_fn(
        decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2,
    )
    c = make_chart_assessment_fn(
        decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2,
    )
    # Mutate AFTER construction — a non-string risk_flag entry slips
    # past BrainOutput.__post_init__ but trips
    # validate_brain_output -> "risk_flags_contains_invalid_entry".
    n.risk_flags = ["valid_flag", ""]   # empty string is invalid

    res = _run(tmp_path, n, m, c, in_window_2, bars_input,
               make_mock_orchestrator_fn)
    # GateMind R1_schema FAILed -> BLOCK with schema_invalid reason.
    assert res.final_status == _BLOCK
    assert "schema_invalid" in res.final_reason


# ---------------------------------------------------------------------------
# 15. Orchestrator never imports oanda/requests/urllib (static)
# ---------------------------------------------------------------------------
def test_15_no_forbidden_imports_anywhere():
    import re
    from pathlib import Path
    from orchestrator.v4.orchestrator_constants import FORBIDDEN_IMPORTS

    orch_dir = Path(__file__).resolve().parents[1]
    files = list(orch_dir.glob("*.py"))
    for forbidden in FORBIDDEN_IMPORTS:
        pat = re.compile(
            rf"^\s*(?:import|from)\s+{re.escape(forbidden)}(?:\.|\s|$)",
            re.MULTILINE,
        )
        for p in files:
            text = p.read_text(encoding="utf-8")
            assert not pat.search(text), (
                f"orchestrator/{p.name} imports forbidden module {forbidden!r}"
            )
