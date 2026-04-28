"""HYDRA V4 — fail-CLOSED propagation tests.

Any brain BLOCK output must propagate. The orchestrator NEVER:
  * Throws on a BLOCK BrainOutput (it's valid data).
  * Modifies the BLOCK BrainOutput.
  * Returns ENTER_CANDIDATE when any brain blocked.
"""

from __future__ import annotations

from contracts.brain_output import BrainGrade, BrainOutput

from orchestrator.v4.orchestrator_constants import FINAL_BLOCK


def _block_news(when):
    return BrainOutput.fail_closed(
        brain_name="newsmind",
        reason="news_blackout_test",
        risk_flags=["news_blackout"],
    )


def _block_market_state(make_market_state_fn, when):
    return make_market_state_fn(grade=BrainGrade.BLOCK, when=when)


def _block_chart_assessment(make_chart_assessment_fn, when):
    return make_chart_assessment_fn(grade=BrainGrade.BLOCK, when=when)


def test_news_block_propagates(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn, make_brain_output_fn
):
    blocked_news = _block_news(bundle_aplus_buy["now_utc"])
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=blocked_news,
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    # The block must surface either as schema_invalid (not a BrainOutput),
    # brain_block, or kill_flag — all of which mean "we obeyed the BLOCK".
    assert res.news_output is blocked_news or res.news_output.should_block


def test_market_block_propagates(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn, make_market_state_fn
):
    blocked_market = _block_market_state(
        make_market_state_fn, bundle_aplus_buy["now_utc"]
    )
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=blocked_market,
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    assert res.market_output is not None
    assert res.market_output.should_block


def test_chart_block_propagates(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn, make_chart_assessment_fn
):
    blocked_chart = _block_chart_assessment(
        make_chart_assessment_fn, bundle_aplus_buy["now_utc"]
    )
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=blocked_chart,
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    assert res.chart_output is not None
    assert res.chart_output.should_block


def test_orchestrator_does_not_modify_block_brain_output(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn, make_market_state_fn
):
    """Identity check — the BLOCK MarketState reference reaches the result
    unchanged in field values (mock restamps timestamp but every other
    field is intact)."""
    blocked = _block_market_state(make_market_state_fn, bundle_aplus_buy["now_utc"])
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=blocked,
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    out = res.market_output
    assert out.grade == blocked.grade
    assert out.decision == blocked.decision
    assert out.should_block == blocked.should_block
    assert out.reason == blocked.reason


def test_unexpected_brain_exception_recorded(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn
):
    """If a brain throws an unhandled exception (e.g. its fail-CLOSED
    boundary doesn't catch it), the orchestrator catches it ONCE,
    stamps ORCHESTRATOR_ERROR, records it, and does not raise to the
    caller. (We construct the broken brain ad hoc.)"""

    class BoomBrain:
        calls = 0

        def evaluate(self, *a, **kw):
            BoomBrain.calls += 1
            raise RuntimeError("boom-from-brain")

    from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
    from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
    from orchestrator.v4.tests.conftest import (
        MockMarketMind,
        MockChartMind,
        MockNewsMind,
    )

    nb = SmartNoteBookV4(tmp_path / "ledger")
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=BoomBrain(),
        marketmind=MockMarketMind(bundle_aplus_buy["market"]),
        chartmind=MockChartMind(bundle_aplus_buy["chart"]),
        smartnotebook=nb,
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    from orchestrator.v4.orchestrator_constants import FINAL_ORCHESTRATOR_ERROR
    assert res.final_status == FINAL_ORCHESTRATOR_ERROR
    assert any("RuntimeError" in e for e in res.errors)
    assert "boom-from-brain" in res.final_reason
