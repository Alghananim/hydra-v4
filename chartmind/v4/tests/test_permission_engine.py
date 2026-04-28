"""Additive-evidence permission engine tests."""
from __future__ import annotations

from contracts.brain_output import BrainGrade

from chartmind.v4 import permission_engine as pe
from chartmind.v4.chart_thresholds import EVIDENCE_KEYS


def _ev(*keys) -> dict:
    return {k: (k in keys) for k in EVIDENCE_KEYS}


def test_zero_evidence_is_block():
    r = pe.decide(pe.PermissionInputs(evidence=_ev(), data_quality="good"))
    assert r.grade == BrainGrade.BLOCK
    assert r.decision == "BLOCK"
    assert r.should_block is True


def test_one_evidence_is_C():
    r = pe.decide(pe.PermissionInputs(evidence=_ev("strong_trend"),
                                       data_quality="good"))
    assert r.grade == BrainGrade.C


def test_three_evidence_is_B():
    r = pe.decide(pe.PermissionInputs(
        evidence=_ev("strong_trend", "key_level_confluence", "real_breakout"),
        data_quality="good",
    ))
    assert r.grade == BrainGrade.B


def test_five_evidence_is_A_with_setup_long():
    r = pe.decide(pe.PermissionInputs(
        evidence=_ev("strong_trend", "key_level_confluence", "real_breakout",
                     "in_context_candle", "mtf_aligned"),
        data_quality="good",
        direction="long",
        setup_present=True,
    ))
    assert r.grade == BrainGrade.A
    assert r.decision == "BUY"


def test_six_evidence_is_A_plus():
    r = pe.decide(pe.PermissionInputs(
        evidence=_ev("strong_trend", "key_level_confluence", "real_breakout",
                     "in_context_candle", "mtf_aligned", "volatility_normal"),
        data_quality="good",
        direction="long",
        setup_present=True,
    ))
    assert r.grade == BrainGrade.A_PLUS
    assert r.decision == "BUY"


def test_eight_evidence_is_A_plus():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(
        evidence=full, data_quality="good",
        direction="long", setup_present=True,
    ))
    assert r.grade == BrainGrade.A_PLUS


def test_data_broken_forces_block():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(evidence=full, data_quality="broken"))
    assert r.grade == BrainGrade.BLOCK


def test_data_stale_caps_at_B():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(evidence=full, data_quality="stale",
                                       direction="long", setup_present=True))
    assert r.grade == BrainGrade.B
    assert r.decision == "WAIT"  # B never triggers BUY/SELL


def test_upstream_block_forces_block():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(evidence=full, data_quality="good",
                                       upstream_block=True))
    assert r.grade == BrainGrade.BLOCK


def test_upstream_cap_caps():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(evidence=full, data_quality="good",
                                       upstream_cap=BrainGrade.B,
                                       direction="long", setup_present=True))
    assert r.grade == BrainGrade.B


def test_no_setup_means_wait_even_with_high_score():
    full = {k: True for k in EVIDENCE_KEYS}
    r = pe.decide(pe.PermissionInputs(evidence=full, data_quality="good",
                                       direction="long", setup_present=False))
    assert r.grade == BrainGrade.A_PLUS
    assert r.decision == "WAIT"


def test_short_direction_yields_sell():
    r = pe.decide(pe.PermissionInputs(
        evidence={k: True for k in EVIDENCE_KEYS}, data_quality="good",
        direction="short", setup_present=True,
    ))
    assert r.decision == "SELL"


def test_score_attribute_present():
    r = pe.decide(pe.PermissionInputs(
        evidence=_ev("strong_trend", "real_breakout"), data_quality="good",
    ))
    assert r.score == 2
