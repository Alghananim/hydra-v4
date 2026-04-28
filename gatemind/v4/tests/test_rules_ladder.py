"""Tests for the rule ladder ordering and short-circuit behaviour."""

from __future__ import annotations

import pytest

from gatemind.v4.rules import (
    RULE_LADDER,
    RuleContext,
    _Verdict,
    evaluate_rules,
    r1_schema,
    r2_session,
    r3_grade,
    r4_brain_block,
    r5_kill_flag,
    r6_direction,
    r7_unanimous_wait,
    r8_enter,
)

from .conftest import (
    make_brain_output_a_wait,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    make_brain_output_aplus_wait,
    make_brain_output_b_grade,
    make_brain_output_block,
    make_brain_output_invalid_schema,
    make_brain_output_with_kill_flag,
    now_in_ny_window,
    now_outside_ny_window,
)


def _ctx(news, market, chart, now_utc):
    return RuleContext(news=news, market=market, chart=chart, now_utc=now_utc, symbol="EUR_USD")


def test_ladder_order_is_locked():
    expected = (
        r1_schema, r2_session, r3_grade, r4_brain_block,
        r5_kill_flag, r6_direction, r7_unanimous_wait, r8_enter,
    )
    assert RULE_LADDER == expected
    assert len(RULE_LADDER) == 8


def test_r1_short_circuits_before_session():
    """Bad schema must block before NY-session check is even consulted."""
    bad = make_brain_output_invalid_schema("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    # Use OUTSIDE-window now_utc to prove R2 is never reached
    ctx = _ctx(bad, m, c, now_outside_ny_window())
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "schema_invalid"
    # R2 must not have run
    assert all(not entry.startswith("R2_session") for entry in ctx.audit_trail)


def test_r2_short_circuits_before_grade():
    """Outside NY must block before grade check runs."""
    n = make_brain_output_b_grade("NewsMind")  # would also fail R3 if we got there
    m = make_brain_output_b_grade("MarketMind")
    c = make_brain_output_b_grade("ChartMind")
    ctx = _ctx(n, m, c, now_outside_ny_window())
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "outside_new_york_trading_window"
    assert all(not entry.startswith("R3_grade") for entry in ctx.audit_trail)


def test_r3_blocks_b_grade_in_window():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_b_grade("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "grade_below_threshold"


def test_r4_blocks_brain_should_block():
    n = make_brain_output_block("NewsMind", "blackout active")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    # Note: should_block→grade=BLOCK, so grade check (R3) catches it first.
    assert res.reason in ("brain_block", "grade_below_threshold")


def test_r5_blocks_kill_flag():
    n = make_brain_output_with_kill_flag("NewsMind", "news_blackout")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "kill_flag_active"


def test_r6_blocks_directional_conflict():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "directional_conflict"


def test_r6_blocks_incomplete_agreement():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_a_wait("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.BLOCK
    assert res.reason == "incomplete_agreement"


def test_r7_unanimous_wait_returns_wait():
    n = make_brain_output_a_wait("NewsMind")
    m = make_brain_output_a_wait("MarketMind")
    c = make_brain_output_aplus_wait("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.WAIT
    assert res.reason == "unanimous_wait"


def test_r8_enter_unanimous_buy():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(1))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.ENTER
    assert res.reason == "all_brains_unanimous_enter"


def test_r8_enter_unanimous_sell():
    n = make_brain_output_aplus_sell("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_aplus_sell("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    res = evaluate_rules(ctx)
    assert res.verdict == _Verdict.ENTER


def test_audit_trail_records_each_pass():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ctx = _ctx(n, m, c, now_in_ny_window(2))
    evaluate_rules(ctx)
    # At least 8 entries in order R1..R8
    rule_tags = [t.split(":")[0] for t in ctx.audit_trail]
    assert rule_tags[:8] == ["R1_schema", "R2_session", "R3_grade",
                              "R4_brain_block", "R5_kill_flag",
                              "R6_direction", "R7_unanimous_wait", "R8_enter"]
