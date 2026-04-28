"""HYDRA V4 — data-flow tests.

Verify that:
  * NewsMind receives (pair, now_utc).
  * MarketMind receives (pair, bars_by_pair, now_utc, news_output=news).
  * ChartMind receives (pair, bars_by_tf, now_utc, news_output=news,
                        market_output=market).

The mock brains record exactly what they were given so we can assert
identity (id()) of the upstream BrainOutput objects passed downstream.
"""

from __future__ import annotations


def test_news_called_with_pair_and_now(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, mock_news, _, _ = make_mock_orchestrator_fn(
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
    assert len(mock_news.calls) == 1
    assert mock_news.calls[0]["pair"] == "EUR_USD"
    assert mock_news.calls[0]["now_utc"] == bundle_aplus_buy["now_utc"]


def test_marketmind_receives_news_output(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, _, mock_market, _ = make_mock_orchestrator_fn(
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
    assert len(mock_market.calls) == 1
    call = mock_market.calls[0]
    assert call["news_output_passed"] is True
    assert call["pair"] == "EUR_USD"
    assert "EUR_USD" in call["bars_by_pair_keys"]


def test_chartmind_receives_news_AND_market_outputs(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, _, _, mock_chart = make_mock_orchestrator_fn(
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
    assert len(mock_chart.calls) == 1
    call = mock_chart.calls[0]
    assert call["news_output_passed"] is True
    assert call["market_output_passed"] is True
    assert "M15" in call["bars_by_tf_keys"]


def test_chartmind_news_id_matches_news_brain_output(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    """Same news object reaches both MarketMind and ChartMind (no copy)."""
    orch, _, mock_market, mock_chart = make_mock_orchestrator_fn(
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
    assert (
        mock_market.calls[0]["news_output_id"]
        == mock_chart.calls[0]["news_output_id"]
    )


def test_decision_cycle_result_carries_all_brain_snapshots(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, _, _, _ = make_mock_orchestrator_fn(
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
    assert res.news_output is not None
    assert res.market_output is not None
    assert res.chart_output is not None
    assert res.gate_decision is not None
    assert res.news_output.brain_name == "newsmind"
    assert res.market_output.brain_name == "marketmind"
    assert res.chart_output.brain_name == "chartmind"
