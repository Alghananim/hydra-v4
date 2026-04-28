"""Consume NewsMind + MarketMind outputs and translate them to ChartMind caps.

Both inputs are BrainOutput-shaped (or subclasses). We never look at internal
fields beyond the contract — only `grade`, `decision`, `should_block`,
`reason`, `risk_flags`. This keeps coupling minimal.

Mapping rules (per Phase 1 spec, integration scenarios 1..5):
- Either upstream BLOCK -> upstream_block=True (forces our BLOCK)
- NewsMind grade C/B    -> upstream_cap=B
- NewsMind missing/None -> upstream_block=True (fail-CLOSED)
- MarketMind A          -> no cap
- MarketMind B          -> upstream_cap=B
- MarketMind C          -> upstream_cap=C
- MarketMind direction conflict with chart direction -> downgrade by 1
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from contracts.brain_output import BrainGrade, BrainOutput


@dataclass
class IntegrationContext:
    upstream_block: bool
    upstream_cap: Optional[BrainGrade]
    reason_bits: list
    news_snapshot: dict
    market_snapshot: dict
    market_direction: str        # "bullish"|"bearish"|"neutral"|"unknown"


def _market_direction(out: Optional[BrainOutput]) -> str:
    if out is None:
        return "unknown"
    # MarketMind exposes trend_state; we read it dynamically, no import.
    trend = getattr(out, "trend_state", None)
    if trend in ("strong_up", "weak_up"):
        return "bullish"
    if trend in ("strong_down", "weak_down"):
        return "bearish"
    if trend in ("range", "choppy"):
        return "neutral"
    return "unknown"


def integrate(news: Optional[BrainOutput],
              market: Optional[BrainOutput],
              chart_direction: str) -> IntegrationContext:
    """`chart_direction` ∈ {"long", "short", "none"}."""
    upstream_block = False
    cap: Optional[BrainGrade] = None
    reasons: list = []

    # ---- NewsMind ----
    news_snap: dict = {"present": news is not None}
    if news is None:
        upstream_block = True
        reasons.append("newsmind_missing")
    else:
        news_snap.update({
            "grade": news.grade.value if hasattr(news.grade, "value") else str(news.grade),
            "decision": news.decision,
            "should_block": news.should_block,
        })
        if news.is_blocking():
            upstream_block = True
            reasons.append(f"newsmind_block:{news.reason[:60]}")
        elif news.grade in (BrainGrade.B, BrainGrade.C):
            cap = BrainGrade.B if cap is None else cap

    # ---- MarketMind ----
    mkt_snap: dict = {"present": market is not None}
    market_dir = _market_direction(market)
    mkt_snap["direction"] = market_dir
    if market is not None:
        mkt_snap.update({
            "grade": market.grade.value if hasattr(market.grade, "value") else str(market.grade),
            "decision": market.decision,
            "should_block": market.should_block,
            "trend_state": getattr(market, "trend_state", None),
        })
        if market.is_blocking():
            upstream_block = True
            reasons.append(f"marketmind_block:{market.reason[:60]}")
        elif market.grade == BrainGrade.B:
            cap = BrainGrade.B if (cap is None or cap == BrainGrade.A) else cap
        elif market.grade == BrainGrade.C:
            # C dominates B
            cap = BrainGrade.C
        # Direction conflict -> step down by 1 tier (cap at B if otherwise A+/A)
        if chart_direction == "long" and market_dir == "bearish":
            reasons.append("conflict:chart_long_vs_market_bearish")
            cap = BrainGrade.B if (cap is None or cap == BrainGrade.A or cap == BrainGrade.A_PLUS) else cap
        elif chart_direction == "short" and market_dir == "bullish":
            reasons.append("conflict:chart_short_vs_market_bullish")
            cap = BrainGrade.B if (cap is None or cap == BrainGrade.A or cap == BrainGrade.A_PLUS) else cap
        elif market_dir == "neutral" and chart_direction in ("long", "short"):
            # Choppy/range market while chart says directional setup -> respect, downgrade
            reasons.append(f"market_neutral_vs_chart_{chart_direction}")
            cap = BrainGrade.B if (cap is None or cap == BrainGrade.A or cap == BrainGrade.A_PLUS) else cap

    return IntegrationContext(
        upstream_block=upstream_block,
        upstream_cap=cap,
        reason_bits=reasons,
        news_snapshot=news_snap,
        market_snapshot=mkt_snap,
        market_direction=market_dir,
    )
