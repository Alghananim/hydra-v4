"""HYDRA V4 — NY session classification tests.

GateMind owns the NY-window classification via session_check; the
orchestrator simply REPORTS what GateMind decided. We verify that:

  * In-window inputs propagate as in_window_pre_open or
    in_window_morning.
  * Outside-window inputs propagate as outside_window AND
    final_status=BLOCK.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from zoneinfo import ZoneInfo

from orchestrator.v4.orchestrator_constants import FINAL_BLOCK
from orchestrator.v4.tests.conftest import (
    now_in_ny_window,
    now_outside_ny_window,
)

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def test_window_1_is_pre_open(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    when = now_in_ny_window(1)
    bundle = {
        "news": bundle_aplus_buy["news"],
        "market": bundle_aplus_buy["market"],
        "chart": bundle_aplus_buy["chart"],
    }
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle["news"],
        market_out=bundle["market"],
        chart_out=bundle["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.session_status == "in_window_pre_open"


def test_window_2_is_morning(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    when = now_in_ny_window(2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.session_status == "in_window_morning"


def test_outside_window_blocks(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    when = now_outside_ny_window()
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_BLOCK
    assert "outside_new_york_trading_window" in res.final_reason
    assert res.session_status == "outside_window"


def test_dst_spring_forward_morning(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    """2025-03-09 09:00 NY (post-spring-forward, EDT). Should be morning."""
    ny_local = datetime(2025, 3, 9, 9, 0, 0, tzinfo=NY)
    when = ny_local.astimezone(UTC)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.session_status == "in_window_morning"


def test_timestamp_ny_is_in_ny_zone(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn
):
    when = now_in_ny_window(2)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=when,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    # timestamp_ny tz key is "America/New_York"
    assert res.timestamp_ny.tzinfo is not None
    assert "New_York" in str(res.timestamp_ny.tzinfo)
