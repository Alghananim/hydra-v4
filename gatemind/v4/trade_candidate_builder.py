"""GateMind V4 — TradeCandidate builder.

Constructs a TradeCandidate IFF the gate decision is ENTER_CANDIDATE. The
builder DOES NOT compute SL/TP/size — those are the Execution layer's job.
This module just records the *fact of consensus* with grades + evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from gatemind.v4.consensus_check import (
    collect_data_quality,
    collect_grades,
)
from gatemind.v4.gatemind_constants import REQUIRED_BRAINS
from gatemind.v4.models import TradeCandidate, TradeDirection
from gatemind.v4.session_check import to_ny


def _gather_evidence(news, market, chart) -> List[str]:
    """Concatenate a small evidence digest from each brain.

    Each line is prefixed by brain name for traceability. We cap each brain to
    its first 5 evidence lines to keep the candidate audit-readable.
    """
    out: List[str] = []
    for label, brain in (("NewsMind", news), ("MarketMind", market), ("ChartMind", chart)):
        items = [e for e in (brain.evidence or []) if isinstance(e, str) and e.strip()]
        for item in items[:5]:
            out.append(f"{label}: {item}")
    return out


def build_trade_candidate(
    *,
    symbol: str,
    direction: TradeDirection,
    news,
    market,
    chart,
    warning_flags: List[str],
    now_utc: datetime,
) -> TradeCandidate:
    """Construct the TradeCandidate. Caller has already verified ENTER conditions."""
    if direction not in (TradeDirection.BUY, TradeDirection.SELL):
        raise ValueError(
            f"build_trade_candidate: direction must be BUY or SELL, got {direction}"
        )

    grades = collect_grades(news, market, chart)
    return TradeCandidate(
        symbol=symbol,
        direction=direction,
        approved_by=list(REQUIRED_BRAINS),
        approval_grades=grades,
        evidence_summary=_gather_evidence(news, market, chart),
        risk_flags=list(warning_flags),  # warnings only by construction
        timestamp_utc=now_utc,
        timestamp_ny=to_ny(now_utc),
    )
