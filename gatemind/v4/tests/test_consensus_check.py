"""Tests for gatemind.v4.consensus_check — 3/3 direction and grade consensus."""

from __future__ import annotations

import pytest

from gatemind.v4.consensus_check import (
    all_grades_pass,
    collect_decisions,
    collect_grades,
    consensus_status,
)

from .conftest import (
    make_brain_output_a_buy,
    make_brain_output_a_sell,
    make_brain_output_a_wait,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    make_brain_output_aplus_wait,
    make_brain_output_b_grade,
    make_brain_output_block,
)


def test_unanimous_buy_aplus():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    label, direction = consensus_status(n, m, c)
    assert label == "unanimous_buy"
    assert direction == "BUY"


def test_unanimous_sell_aplus():
    n = make_brain_output_aplus_sell("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_aplus_sell("ChartMind")
    label, direction = consensus_status(n, m, c)
    assert label == "unanimous_sell"
    assert direction == "SELL"


def test_unanimous_wait():
    n = make_brain_output_a_wait("NewsMind")
    m = make_brain_output_a_wait("MarketMind")
    c = make_brain_output_aplus_wait("ChartMind")
    label, _ = consensus_status(n, m, c)
    assert label == "unanimous_wait"


def test_directional_conflict():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    label, _ = consensus_status(n, m, c)
    assert label == "directional_conflict"


def test_2buy_1wait_incomplete():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_a_wait("ChartMind")
    label, _ = consensus_status(n, m, c)
    assert label == "incomplete_agreement"


def test_2sell_1wait_incomplete():
    n = make_brain_output_aplus_sell("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_a_wait("ChartMind")
    label, _ = consensus_status(n, m, c)
    assert label == "incomplete_agreement"


def test_any_block_short_circuits():
    n = make_brain_output_block("NewsMind", "blackout")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    label, _ = consensus_status(n, m, c)
    assert label == "any_block"


def test_grades_all_aplus():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ok, status = all_grades_pass(n, m, c)
    assert ok and status == "all_a_plus"


def test_grades_mixed_a_aplus():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_a_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ok, status = all_grades_pass(n, m, c)
    assert ok and status == "all_a_or_better"


def test_grades_b_fails():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_b_grade("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ok, status = all_grades_pass(n, m, c)
    assert not ok
    assert status == "below_threshold"


def test_grade_block_fails():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_block("ChartMind")
    ok, status = all_grades_pass(n, m, c)
    assert not ok


def test_collect_decisions_shape():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    votes = collect_decisions(n, m, c)
    assert votes == {"NewsMind": "BUY", "MarketMind": "BUY", "ChartMind": "BUY"}


def test_collect_grades_shape():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_a_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    grades = collect_grades(n, m, c)
    assert grades == {"NewsMind": "A+", "MarketMind": "A", "ChartMind": "A+"}
