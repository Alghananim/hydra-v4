"""Cross-asset correlation tracker — adapted from V3.

Phase 1 audit verdict: KEEP V3 logic (Pearson on log returns), LOCK
expected ranges, drop the V3 'broken correlation = block' override —
status is informational; the permission_engine decides downgrade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Mapping, Tuple, Dict

from marketmind.v4.models import Bar


WINDOW = 60


# Locked expected normal ranges (M15, last 60 bars). DO NOT TUNE without
# re-running the calibration in Phase 1.
EXPECTED: Dict[str, Tuple[float, float]] = {
    "EURUSD_vs_USDJPY": (-1.0, 0.1),
    "EURUSD_vs_GOLD":   (-0.3, 0.7),
    "USDJPY_vs_GOLD":   (-0.7, 0.3),
    "EURUSD_vs_SPX":    (-0.2, 0.5),
    "USDJPY_vs_SPX":    (0.0, 0.6),
}
TOLERANCE = 0.4   # how far outside the band we must be to call it 'broken'


@dataclass
class CorrelationResult:
    status: str = "unavailable"   # "normal" | "broken" | "unavailable"
    pairs: Dict[str, float] = field(default_factory=dict)
    anomalies: Tuple[str, ...] = ()
    rationale: Tuple[str, ...] = ()


def _log_returns(bars: Sequence[Bar]) -> List[float]:
    out: List[float] = []
    for i in range(1, len(bars)):
        a = bars[i - 1].close
        b = bars[i].close
        if a <= 0 or b <= 0:
            continue
        out.append(math.log(b / a))
    return out


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = min(len(xs), len(ys))
    if n < 5:
        return None
    xs, ys = list(xs[-n:]), list(ys[-n:])
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    vx = sum((x - mx) ** 2 for x in xs) / n
    vy = sum((y - my) ** 2 for y in ys) / n
    if vx == 0 or vy == 0:
        return None
    return cov / math.sqrt(vx * vy)


def assess(
    *,
    bars_eurusd: Optional[Sequence[Bar]] = None,
    bars_usdjpy: Optional[Sequence[Bar]] = None,
    bars_xau: Optional[Sequence[Bar]] = None,
    bars_spx: Optional[Sequence[Bar]] = None,
    window: int = WINDOW,
) -> CorrelationResult:
    series = {
        "EURUSD": _log_returns(bars_eurusd or [])[-window:],
        "USDJPY": _log_returns(bars_usdjpy or [])[-window:],
        "GOLD":   _log_returns(bars_xau or [])[-window:],
        "SPX":    _log_returns(bars_spx or [])[-window:],
    }

    test_pairs = [
        ("EURUSD_vs_USDJPY", "EURUSD", "USDJPY"),
        ("EURUSD_vs_GOLD",   "EURUSD", "GOLD"),
        ("USDJPY_vs_GOLD",   "USDJPY", "GOLD"),
        ("EURUSD_vs_SPX",    "EURUSD", "SPX"),
        ("USDJPY_vs_SPX",    "USDJPY", "SPX"),
    ]

    pairs: Dict[str, float] = {}
    anomalies: List[str] = []

    for label, a, b in test_pairs:
        if not series[a] or not series[b]:
            continue
        c = _pearson(series[a], series[b])
        if c is None:
            continue
        pairs[label] = round(c, 3)
        lo, hi = EXPECTED.get(label, (-1.0, 1.0))
        if c < lo - TOLERANCE or c > hi + TOLERANCE:
            anomalies.append(f"{label}={c:.2f}_outside_{lo}..{hi}")

    if not pairs:
        return CorrelationResult(rationale=("no_data",))
    status = "broken" if anomalies else "normal"
    return CorrelationResult(
        status=status,
        pairs=pairs,
        anomalies=tuple(anomalies),
        rationale=("computed",),
    )
