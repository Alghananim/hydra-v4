"""test_attribution.py — R7. Lucky-win rule.

  - direction match + grade A/A+ → earned, responsible=that mind
  - direction match + grade C → lucky, responsible=luck (NOT news/market/chart)
  - loss with A+ agreement → unforced_loss, responsible=that mind
  - loss with no A+ agreement → unforced_loss, responsible=luck
"""

from __future__ import annotations

from smartnotebook.v4.attribution import attribute_outcome
from smartnotebook.v4.notebook_constants import (
    QUALITY_EARNED,
    QUALITY_LUCKY,
    QUALITY_UNFORCED,
    RESPONSIBLE_LUCK,
    RESPONSIBLE_NEWS,
    RESPONSIBLE_MARKET,
)


def test_R7_grade_C_match_is_lucky_not_news():
    """The locked R7 example: grade C + direction match → lucky/luck."""
    a = attribute_outcome(
        direction="BUY",
        pnl=10.0,
        direction_matched=True,
        mind_grades={"newsmind": "C", "marketmind": "C", "chartmind": "C"},
        mind_decisions={"newsmind": "BUY", "marketmind": "BUY", "chartmind": "BUY"},
    )
    assert a.quality == QUALITY_LUCKY
    assert a.responsible == RESPONSIBLE_LUCK
    assert a.responsible != RESPONSIBLE_NEWS


def test_R7_grade_B_match_is_lucky():
    a = attribute_outcome(
        direction="BUY",
        pnl=5.0,
        direction_matched=True,
        mind_grades={"newsmind": "B"},
        mind_decisions={"newsmind": "BUY"},
    )
    assert a.quality == QUALITY_LUCKY
    assert a.responsible == RESPONSIBLE_LUCK


def test_R7_grade_A_plus_match_is_earned_news():
    a = attribute_outcome(
        direction="BUY",
        pnl=10.0,
        direction_matched=True,
        mind_grades={"newsmind": "A+", "marketmind": "C", "chartmind": "C"},
        mind_decisions={"newsmind": "BUY", "marketmind": "WAIT", "chartmind": "WAIT"},
    )
    assert a.quality == QUALITY_EARNED
    assert a.responsible == RESPONSIBLE_NEWS


def test_R7_grade_A_match_is_earned():
    a = attribute_outcome(
        direction="BUY",
        pnl=10.0,
        direction_matched=True,
        mind_grades={"marketmind": "A", "newsmind": "C", "chartmind": "C"},
        mind_decisions={"marketmind": "BUY", "newsmind": "WAIT", "chartmind": "WAIT"},
    )
    assert a.quality == QUALITY_EARNED
    assert a.responsible == RESPONSIBLE_MARKET


def test_R7_no_direction_match_is_lucky():
    """profit but the trade went the OTHER way of brain prediction."""
    a = attribute_outcome(
        direction="BUY",
        pnl=10.0,
        direction_matched=False,  # somehow profitable but didn't match direction
        mind_grades={"newsmind": "A+"},
        mind_decisions={"newsmind": "BUY"},
    )
    assert a.quality == QUALITY_LUCKY
    assert a.responsible == RESPONSIBLE_LUCK


def test_R7_loss_with_A_plus_agreement_is_unforced():
    a = attribute_outcome(
        direction="BUY",
        pnl=-10.0,
        direction_matched=False,
        mind_grades={"newsmind": "A+"},
        mind_decisions={"newsmind": "BUY"},
    )
    assert a.quality == QUALITY_UNFORCED
    assert a.responsible == RESPONSIBLE_NEWS


def test_R7_loss_with_no_high_grade_is_luck():
    a = attribute_outcome(
        direction="BUY",
        pnl=-10.0,
        direction_matched=False,
        mind_grades={"newsmind": "C"},
        mind_decisions={"newsmind": "BUY"},
    )
    assert a.quality == QUALITY_UNFORCED
    assert a.responsible == RESPONSIBLE_LUCK


def test_breakeven_is_unknown():
    a = attribute_outcome(
        direction="BUY",
        pnl=0.0,
        direction_matched=True,
        mind_grades={"newsmind": "A+"},
        mind_decisions={"newsmind": "BUY"},
    )
    # breakeven → unknown
    assert a.responsible == RESPONSIBLE_LUCK


def test_two_a_plus_minds_only_first_credited():
    a = attribute_outcome(
        direction="BUY",
        pnl=10.0,
        direction_matched=True,
        mind_grades={"newsmind": "A+", "marketmind": "A+"},
        mind_decisions={"newsmind": "BUY", "marketmind": "BUY"},
    )
    # earned by news (deterministic order); both in earned_minds
    assert a.quality == QUALITY_EARNED
    assert a.responsible == RESPONSIBLE_NEWS
    assert RESPONSIBLE_MARKET in a.earned_minds
