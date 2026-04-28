"""HYDRA V4 — scalability / extensibility tests.

The orchestrator must be pair-agnostic — adding a new symbol like
USD_JPY should not require touching orchestrator.v4. We verify by:

  1. Running the same orchestrator on EUR_USD AND USD_JPY with
     equivalent bundles. Both must produce DecisionCycleResult.
  2. Running two cycles back-to-back on the same orchestrator
     instance (no internal state leaks between cycles).
"""

from __future__ import annotations

from contracts.brain_output import BrainGrade


def test_orchestrator_supports_eur_usd_and_usd_jpy_back_to_back(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Run EUR_USD then USD_JPY through the SAME orchestrator instance."""
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    res_eur = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    res_jpy = orch.run_cycle(
        symbol="USD_JPY",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res_eur.symbol == "EUR_USD"
    assert res_jpy.symbol == "USD_JPY"
    assert res_eur.cycle_id != res_jpy.cycle_id


def test_no_internal_state_between_cycles(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Cycle A's BrainOutput references must NOT leak into Cycle B's
    DecisionCycleResult."""
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    r1 = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    r2 = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=in_window_2,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    # Each cycle must have its own audit_id (gate decision is recomputed
    # by GateMind every call) and cycle_id.
    assert r1.gate_decision.audit_id != r2.gate_decision.audit_id
    assert r1.decision_cycle_record_id != r2.decision_cycle_record_id


def test_orchestrator_is_pair_agnostic_in_signature():
    """The orchestrator's run_cycle takes `symbol: str`, not a hardcoded
    'EUR_USD'/'USD_JPY' enum. Static reflection via inspect."""
    import inspect

    from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4

    sig = inspect.signature(HydraOrchestratorV4.run_cycle)
    assert "symbol" in sig.parameters
    p = sig.parameters["symbol"]
    # No default — caller must pass one
    assert p.default is inspect.Parameter.empty


def test_concurrent_cycles_have_unique_cycle_ids(
    tmp_path, in_window_2, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """Run 50 cycles fast — cycle_ids must all be unique."""
    n = make_brain_output_fn("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                              when=in_window_2)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c
    )
    ids = set()
    for _ in range(50):
        r = orch.run_cycle(
            symbol="EUR_USD",
            now_utc=in_window_2,
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )
        ids.add(r.cycle_id)
    assert len(ids) == 50
