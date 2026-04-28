"""Confidence scoring — DERIVED from state enums, no magic weights.

Phase 1 audit verdict: V3's scoring.py with 0.4/0.3/0.2/0.1 magic weights
is REJECTED. V4 derives confidence from a transparent table keyed on the
named states.

confidence(grade, states) -> float in [0,1]
"""
from __future__ import annotations

from typing import Mapping

from contracts.brain_output import BrainGrade


# Base by grade (single source of "how sure are we, given the verdict")
_GRADE_BASE = {
    BrainGrade.BLOCK:  0.00,
    BrainGrade.C:      0.30,
    BrainGrade.B:      0.55,
    BrainGrade.A:      0.75,
    BrainGrade.A_PLUS: 0.90,
}


# Bonuses (named, traceable). Each adds to base; clipped to 0.99.
_BONUS = {
    "trend_strong":          0.03,   # trend in {strong_up, strong_down}
    "momentum_accel":        0.02,
    "vol_normal":            0.02,
    "liq_good":              0.02,
    "data_good":             0.01,
    "news_aligned":          0.02,
    "no_contradiction":      0.02,
    "correlation_normal":    0.01,
}


def compute_confidence(
    grade: BrainGrade,
    *,
    trend_state: str,
    momentum_state: str,
    volatility_state: str,
    liquidity_state: str,
    correlation_status: str,
    news_state: str,
    contradiction_severity: str | None,
    data_quality: str,
) -> float:
    base = _GRADE_BASE.get(grade, 0.0)
    if grade == BrainGrade.BLOCK:
        return 0.0
    if trend_state in ("strong_up", "strong_down"):
        base += _BONUS["trend_strong"]
    if momentum_state == "accelerating":
        base += _BONUS["momentum_accel"]
    if volatility_state == "normal":
        base += _BONUS["vol_normal"]
    if liquidity_state == "good":
        base += _BONUS["liq_good"]
    if data_quality == "good":
        base += _BONUS["data_good"]
    if news_state == "aligned":
        base += _BONUS["news_aligned"]
    if contradiction_severity is None:
        base += _BONUS["no_contradiction"]
    if correlation_status == "normal":
        base += _BONUS["correlation_normal"]
    return float(max(0.0, min(0.99, base)))
