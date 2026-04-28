"""HYDRA V4 — Brain calling order tests.

The Phase 1 contract: News -> Market -> Chart -> Gate, in that order.
We verify call order via a shared call-log on the mock brains.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
from orchestrator.v4.orchestrator_constants import (
    T_CHART,
    T_GATE,
    T_MARKET,
    T_NEWS,
    T_NOTEBOOK,
    T_TOTAL,
)
from orchestrator.v4.tests.conftest import (
    MockChartMind,
    MockMarketMind,
    MockNewsMind,
)
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4


class CallLog:
    def __init__(self):
        self.events = []


class _OrderedNews(MockNewsMind):
    def __init__(self, output, log):
        super().__init__(output)
        self.log = log

    def evaluate(self, *a, **kw):
        self.log.events.append("news")
        return super().evaluate(*a, **kw)


class _OrderedMarket(MockMarketMind):
    def __init__(self, output, log):
        super().__init__(output)
        self.log = log

    def evaluate(self, *a, **kw):
        self.log.events.append("market")
        return super().evaluate(*a, **kw)


class _OrderedChart(MockChartMind):
    def __init__(self, output, log):
        super().__init__(output)
        self.log = log

    def evaluate(self, *a, **kw):
        self.log.events.append("chart")
        return super().evaluate(*a, **kw)


def test_brain_call_order_locked(
    tmp_path, bundle_aplus_buy, bars_input
):
    log = CallLog()
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=_OrderedNews(bundle_aplus_buy["news"], log),
        marketmind=_OrderedMarket(bundle_aplus_buy["market"], log),
        chartmind=_OrderedChart(bundle_aplus_buy["chart"], log),
        smartnotebook=SmartNoteBookV4(tmp_path / "ledger"),
    )
    orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert log.events == ["news", "market", "chart"]


def test_timings_recorded_for_each_brain(
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
    for k in (T_NEWS, T_MARKET, T_CHART, T_GATE, T_NOTEBOOK, T_TOTAL):
        assert k in res.timings_ms, f"missing timing key {k}"
        assert res.timings_ms[k] >= 0


def test_total_ms_at_least_sum_of_brain_ms(
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
    parts = (res.timings_ms[T_NEWS] + res.timings_ms[T_MARKET]
             + res.timings_ms[T_CHART] + res.timings_ms[T_GATE])
    # total must be >= sum of brain times (notebook + small overhead pushes
    # it higher, never lower)
    assert res.timings_ms[T_TOTAL] + 1e-6 >= parts


def test_gate_called_after_all_three_perception_brains(
    tmp_path, bundle_aplus_buy, bars_input
):
    """GateMind MUST receive complete BrainOutputs from all 3 — even if a
    brain returned BLOCK, all three are still invoked first (audit trail
    integrity)."""
    log = CallLog()

    class FakeGate:
        def __init__(self):
            self.last = None

        def evaluate(self, news, market, chart, *a, **kw):
            log.events.append("gate")
            assert news is not None
            assert market is not None
            assert chart is not None
            from gatemind.v4.GateMindV4 import GateMindV4
            return GateMindV4().evaluate(news, market, chart, *a, **kw)

    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=_OrderedNews(bundle_aplus_buy["news"], log),
        marketmind=_OrderedMarket(bundle_aplus_buy["market"], log),
        chartmind=_OrderedChart(bundle_aplus_buy["chart"], log),
        gatemind=FakeGate(),
        smartnotebook=SmartNoteBookV4(tmp_path / "ledger"),
    )
    orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert log.events == ["news", "market", "chart", "gate"]
