"""Synthetic Dollar Strength Index — adapted from V3.

ICE convention DXY weights (LOCKED — Phase 1):
    EUR/USD : 57.6%   inverse
    USD/JPY : 13.6%   direct
    GBP/USD : 11.9%   inverse
    USD/CAD :  9.1%   direct
    SEK/USD :  4.2%   inverse
    USD/CHF :  3.6%   direct

If only a partial basket is available, weights are re-normalised over
what we have. Coverage is reported so callers can downgrade.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, Dict, List

from marketmind.v4.models import Bar


# (sign, weight)
WEIGHTS = {
    "EUR/USD": (-1, 0.576),
    "USD/JPY": (+1, 0.136),
    "GBP/USD": (-1, 0.119),
    "USD/CAD": (+1, 0.091),
    "SEK/USD": (-1, 0.042),
    "USD/CHF": (+1, 0.036),
}


@dataclass
class SyntheticDxyResult:
    value: float = 100.0
    direction: str = "flat"
    strength: float = 0.5
    components: Dict[str, float] = field(default_factory=dict)
    coverage: float = 0.0


def _norm_pair(p: str) -> str:
    """Accept 'EURUSD' or 'EUR/USD' -> 'EUR/USD'."""
    s = p.upper().replace("-", "/").replace("_", "/")
    if "/" not in s and len(s) == 6:
        s = s[:3] + "/" + s[3:]
    return s


def compute(*, baskets: Mapping[str, Sequence[Bar]], window: int = 20) -> SyntheticDxyResult:
    contribs: Dict[str, float] = {}
    total_w = 0.0
    net_delta = 0.0

    # Normalise basket keys
    basket_norm: Dict[str, Sequence[Bar]] = {_norm_pair(k): v for k, v in baskets.items()}

    for pair, (sign, w) in WEIGHTS.items():
        bars = basket_norm.get(pair)
        if not bars or len(bars) < window + 1:
            continue
        old = bars[-window - 1].close
        new = bars[-1].close
        if old == 0:
            continue
        pct = (new - old) / old
        usd_contribution = sign * pct
        contribs[pair] = round(usd_contribution * 100, 4)
        net_delta += usd_contribution * w
        total_w += w

    if total_w == 0:
        return SyntheticDxyResult()

    coverage = total_w / sum(w for _, w in WEIGHTS.values())
    raw = net_delta / total_w
    strength = max(0.0, min(1.0, 0.5 + raw / 0.02))
    direction = "up" if raw > 0.0005 else ("down" if raw < -0.0005 else "flat")

    return SyntheticDxyResult(
        value=round(100 * (1 + raw), 4),
        direction=direction,
        strength=round(strength, 3),
        components=contribs,
        coverage=round(coverage, 3),
    )
