"""Support/Resistance detection — ATR-tolerant cluster of swing pivots.

ADAPT from V3 (the cluster logic was the strongest piece):
- Cluster swing prices within CLUSTER_TOL_ATR (0.3 × ATR) of one another.
- Strength = number of touches (1 weak, 2 medium, 3+ strong).
- Type = "support" if mostly lows, "resistance" if mostly highs.
"""
from __future__ import annotations

from typing import List, Sequence

from marketmind.v4 import indicators
from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    CLUSTER_TOL_ATR,
    LEVEL_LOOKBACK_BARS,
    SWING_K,
)
from chartmind.v4.market_structure import find_swings_adaptive
from chartmind.v4.models import Level


def detect_levels(bars: Sequence[Bar],
                  *,
                  atr_value: float,
                  lookback: int = LEVEL_LOOKBACK_BARS,
                  k: int = SWING_K) -> List[Level]:
    """Return clustered key levels in price order (ascending)."""
    if not bars or atr_value <= 0:
        return []
    cutoff = max(0, len(bars) - lookback)
    swings = [s for s in find_swings_adaptive(bars, k=k, lookback=lookback)
              if s.index >= cutoff]
    if not swings:
        return []
    tol = CLUSTER_TOL_ATR * atr_value

    # Sort by price for greedy clustering
    swings_sorted = sorted(swings, key=lambda s: s.price)

    clusters: List[List] = [[swings_sorted[0]]]
    for s in swings_sorted[1:]:
        # Compare to representative price of current cluster (mean)
        cur = clusters[-1]
        mean_p = sum(x.price for x in cur) / len(cur)
        if abs(s.price - mean_p) <= tol:
            cur.append(s)
        else:
            clusters.append([s])

    levels: List[Level] = []
    for cluster in clusters:
        prices = [s.price for s in cluster]
        mean_p = sum(prices) / len(prices)
        n_high = sum(1 for s in cluster if s.kind == "high")
        n_low = sum(1 for s in cluster if s.kind == "low")
        kind = "resistance" if n_high >= n_low else "support"
        levels.append(Level(
            price=float(mean_p),
            type=kind,
            strength=int(len(cluster)),
            touches=[s.index for s in cluster],
        ))
    levels.sort(key=lambda L: L.price)
    return levels


def nearest_levels(levels: List[Level], price: float):
    """Return (support_below, resistance_above). Either may be None."""
    below = [L for L in levels if L.price <= price]
    above = [L for L in levels if L.price > price]
    sup = max(below, key=lambda L: L.price) if below else None
    res = min(above, key=lambda L: L.price) if above else None
    return sup, res
