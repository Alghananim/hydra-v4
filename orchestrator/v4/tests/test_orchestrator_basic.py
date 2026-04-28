"""HYDRA V4 — basic smoke tests: full orchestrator pipeline runs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.v4.decision_cycle_record import DecisionCycleResult
from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
from orchestrator.v4.orchestrator_constants import (
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_WAIT,
)
from orchestrator.v4.orchestrator_errors import BarFeedError


def test_smoke_full_pipeline_aplus_buy(
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
    assert isinstance(res, DecisionCycleResult)
    assert res.final_status == FINAL_ENTER_CANDIDATE
    assert res.cycle_id.startswith("hyd-")
    assert res.symbol == "EUR_USD"
    assert res.decision_cycle_record_id
    assert res.gate_audit_record_id
    assert res.gate_decision is not None
    assert res.timings_ms.get("total_ms", 0) >= 0


def test_smoke_returns_block_on_outside_window(
    tmp_path, bundle_aplus_buy, bars_input,
    make_mock_orchestrator_fn, outside_window
):
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=outside_window,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    assert "outside_new_york_trading_window" in res.final_reason


def test_smoke_naive_now_utc_raises(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    with pytest.raises(BarFeedError, match="tz-aware"):
        orch.run_cycle(
            symbol="EUR_USD",
            now_utc=datetime(2025, 7, 15, 14, 0, 0),  # naive
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )


def test_smoke_empty_symbol_raises(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    with pytest.raises(BarFeedError, match="symbol"):
        orch.run_cycle(
            symbol="",
            now_utc=bundle_aplus_buy["now_utc"],
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )


def test_smoke_none_bars_raise(
    tmp_path, bundle_aplus_buy, make_mock_orchestrator_fn
):
    orch, _, _, _ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    with pytest.raises(BarFeedError):
        orch.run_cycle(
            symbol="EUR_USD",
            now_utc=bundle_aplus_buy["now_utc"],
            bars_by_pair=None,
            bars_by_tf={},
        )


def test_smoke_constructor_requires_storage_or_notebook():
    with pytest.raises(Exception):
        HydraOrchestratorV4()
