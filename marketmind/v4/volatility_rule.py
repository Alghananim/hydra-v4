"""VOL_RULE — ATR(14) percentile rank in last 100 bars + last-bar extremity.

Spec (Phase 1 audit):
  pct < 25                                  -> compressed
  25 <= pct <= 75                           -> normal
  75 < pct <= 90                            -> expanded
  pct > 90 OR last_bar_range > 4 * ATR      -> dangerous
  insufficient bars                         -> unknown
"""
from __future__ import annotations

from typing import Sequence, Tuple, Dict, Any

from marketmind.v4.models import Bar
from marketmind.v4.indicators import (
    ATR_PERIOD, PERCENTILE_WINDOW,
    atr, atr_percentile_now,
)


COMPRESSED_MAX = 25.0
NORMAL_MAX = 75.0
EXPANDED_MAX = 90.0
DANGEROUS_BAR_MULT = 4.0


def evaluate(bars: Sequence[Bar]) -> Tuple[str, Dict[str, Any]]:
    ev: Dict[str, Any] = {"rule": "VOL_RULE"}
    needed = ATR_PERIOD + 2
    if len(bars) < needed:
        ev["reason"] = f"insufficient_bars({len(bars)}<{needed})"
        return "unknown", ev

    a = atr(bars, ATR_PERIOD)
    pct = atr_percentile_now(bars, PERCENTILE_WINDOW, ATR_PERIOD)
    last = bars[-1]
    last_range = last.high - last.low

    ev.update({
        "atr": round(a, 6),
        "atr_percentile": round(pct, 2),
        "last_bar_range": round(last_range, 6),
        "last_range_x_atr": round(last_range / a, 3) if a > 0 else None,
        "window": PERCENTILE_WINDOW,
    })

    # Dangerous trumps everything: extreme bar OR top-decile percentile
    if a > 0 and last_range > DANGEROUS_BAR_MULT * a:
        ev["match"] = f"dangerous(last_range>{DANGEROUS_BAR_MULT}xATR)"
        return "dangerous", ev
    if pct > EXPANDED_MAX:
        ev["match"] = "dangerous(pct>90)"
        return "dangerous", ev
    if pct > NORMAL_MAX:
        ev["match"] = "expanded"
        return "expanded", ev
    if pct < COMPRESSED_MAX:
        ev["match"] = "compressed"
        return "compressed", ev
    ev["match"] = "normal"
    return "normal", ev
