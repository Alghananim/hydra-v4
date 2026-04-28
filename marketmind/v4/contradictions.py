"""Cross-market contradiction detector — adapted from V3.

V3 had 8 checks; Phase 1 audit drops two:
  DROPPED: "rapid_move_chase_risk_news_allow"  — chase logic belongs to NewsMind
  DROPPED: "eurusd_strong_move_dxy_flat_no_macro_support"  — no DXY confirmation

Remaining 6 checks (severities locked):
  C1 dxy_up_with_eurusd_up                       high
  C1b dxy_down_with_eurusd_down                  high
  C2 eurusd_and_usdjpy_both_up_inconsistent_usd  high
  C2b eurusd_and_usdjpy_both_down_inconsistent_usd high
  C3 risk_off_but_usdjpy_rising_haven_violated   high
  C4 gold_up_and_dollar_up_abnormal_regime       medium
  C5 spx_down_but_usdjpy_up_risk_off_violated    high
  C6 news_X_but_market_Xprime_divergent          high

Severity outcomes (consumed by permission_engine):
  any 'critical' -> grade BLOCK (BUT contradictions never produce critical
                    in V4; reserved for future)
  any 'high'     -> downgrade (cap at C)
  any 'medium'   -> cap at B
  none           -> no override
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from marketmind.v4.models import Bar


@dataclass
class ContradictionResult:
    items: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def critical(self) -> bool:
        return any(s == "critical" for _, s in self.items)

    @property
    def high(self) -> bool:
        return any(s == "high" for _, s in self.items)

    @property
    def medium(self) -> bool:
        return any(s == "medium" for _, s in self.items)

    def labels(self) -> List[str]:
        return [label for label, _ in self.items]


def _pct(bars: Optional[Sequence[Bar]], window: int) -> Optional[float]:
    if not bars or len(bars) < window + 1:
        return None
    old = bars[-window - 1].close
    if old == 0:
        return None
    return (bars[-1].close - old) / old


def detect(
    *,
    bars_eurusd: Optional[Sequence[Bar]] = None,
    bars_usdjpy: Optional[Sequence[Bar]] = None,
    bars_xau: Optional[Sequence[Bar]] = None,
    bars_spx: Optional[Sequence[Bar]] = None,
    dxy_dir: str = "flat",
    dxy_strength: float = 0.5,
    risk_mode: str = "unclear",
    news_bias: str = "unclear",
    news_perm: str = "allow",
    market_direction: str = "neutral",
) -> ContradictionResult:
    items: List[Tuple[str, str]] = []
    eur = _pct(bars_eurusd, 10) if bars_eurusd else None
    jpy = _pct(bars_usdjpy, 10) if bars_usdjpy else None
    xau = _pct(bars_xau, 10) if bars_xau else None
    spx = _pct(bars_spx, 10) if bars_spx else None

    # C1: DXY-EURUSD same direction
    if eur is not None and abs(eur) > 0.001:
        if dxy_dir == "up" and eur > 0.001:
            items.append(("dxy_up_with_eurusd_up", "high"))
        elif dxy_dir == "down" and eur < -0.001:
            items.append(("dxy_down_with_eurusd_down", "high"))

    # C2: EURUSD + USDJPY same direction (USD signal inconsistent)
    if eur is not None and jpy is not None:
        if eur > 0.001 and jpy > 0.001:
            items.append(("eurusd_and_usdjpy_both_up_inconsistent_usd", "high"))
        elif eur < -0.001 and jpy < -0.001:
            items.append(("eurusd_and_usdjpy_both_down_inconsistent_usd", "high"))

    # C3: risk-off + USDJPY rising (haven flow violated)
    if risk_mode == "risk_off" and jpy is not None and jpy > 0.0005:
        items.append(("risk_off_but_usdjpy_rising_haven_violated", "high"))

    # C4: gold up AND dollar up = abnormal
    if xau is not None and xau > 0.005 and dxy_dir == "up" and dxy_strength > 0.55:
        items.append(("gold_up_and_dollar_up_abnormal_regime", "medium"))

    # C5: SPX down + USDJPY up (risk-off violated)
    if spx is not None and jpy is not None and spx < -0.005 and jpy > 0.001:
        items.append(("spx_down_but_usdjpy_up_risk_off_violated", "high"))

    # C6: news vs market divergence
    if (
        news_perm == "allow"
        and news_bias in ("bullish", "bearish")
        and market_direction in ("bullish", "bearish")
        and news_bias != market_direction
    ):
        items.append((f"news_{news_bias}_but_market_{market_direction}_divergent", "high"))

    return ContradictionResult(items=items)


def severity_to_grade_cap(result: ContradictionResult) -> Optional[str]:
    """Return the grade-letter cap implied by the worst severity, or None."""
    if result.critical:
        return "BLOCK"
    if result.high:
        return "C"
    if result.medium:
        return "B"
    return None
