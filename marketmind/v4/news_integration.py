"""NewsMind V4 integration adapter.

This module is the ONE place MarketMind talks to NewsMind. It:
  1. Maps NewsMind's BrainOutput into a (news_state, news_grade_cap) pair
     consumable by the permission engine.
  2. Fails CLOSED if NewsMind is unavailable or returned malformed output.

NewsMind contract recap (frozen at newsmind/v4):
  - decision in {"BUY","SELL","WAIT","BLOCK"}, but newsmind never emits BUY/SELL
  - grade in {A+, A, B, C, BLOCK}
  - should_block True iff grade == BLOCK
  - risk_flags is a list of short tags

Mapping:
  news.should_block            -> news_state="block",   news_grade_cap=BLOCK
  news.grade in {C, B} and risk_flags non-empty
                                -> news_state="warning", news_grade_cap=B
  news.grade in {C, B} clean    -> news_state="warning", news_grade_cap=B
  news.grade in {A, A+}         -> news_state="aligned", news_grade_cap=A_PLUS (no cap)
  news None                     -> news_state="no_news", news_grade_cap=None
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from contracts.brain_output import BrainOutput, BrainGrade


@dataclass
class NewsContext:
    news_state: str                          # "aligned" | "warning" | "block" | "no_news"
    news_grade_cap: Optional[BrainGrade]
    snapshot: Dict[str, Any]


def _to_snapshot(news: BrainOutput) -> Dict[str, Any]:
    return {
        "brain_name": news.brain_name,
        "decision": news.decision,
        "grade": news.grade.value,
        "reason": news.reason,
        "risk_flags": list(news.risk_flags),
        "should_block": news.should_block,
        "data_quality": news.data_quality,
        "confidence": news.confidence,
    }


def map_news_output(news: Optional[BrainOutput]) -> NewsContext:
    if news is None:
        return NewsContext(
            news_state="no_news",
            news_grade_cap=None,
            snapshot={"present": False},
        )

    snap = _to_snapshot(news)

    # Hard block — MarketMind MUST respect
    if news.should_block or news.grade == BrainGrade.BLOCK:
        return NewsContext(
            news_state="block",
            news_grade_cap=BrainGrade.BLOCK,
            snapshot=snap,
        )

    # Warnings cap at B
    if news.grade in (BrainGrade.B, BrainGrade.C):
        return NewsContext(
            news_state="warning",
            news_grade_cap=BrainGrade.B,
            snapshot=snap,
        )

    # A / A+ — aligned, no cap
    return NewsContext(
        news_state="aligned",
        news_grade_cap=None,
        snapshot=snap,
    )
