"""HYDRA V4 — data quality checker.

Inspects a list of OANDA candle dicts (after pagination/merge) and
reports:

  * total_bars
  * missing_bars (gaps where expected_dt skipped)
  * gaps_minutes_max
  * duplicate_ts_count
  * stale_bars_volume_zero
  * spread_avg_pips (if bid+ask present)
  * non_complete_bars (candle.complete != True)
  * timezone_naive_count

Returns a `dict` shaped for direct JSON dumping. The data_loader
writes it to `<cache_root>/<pair>_<granularity>_quality.json`.

Pip resolution per pair is hard-coded for EUR_USD (0.0001) and
USD_JPY (0.01); other pairs default to 0.0001 with a warning.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

_log = logging.getLogger("live_data.dq")


class InvalidCandleError(ValueError):
    """Raised when a candle contains a non-finite numeric field
    (NaN / Infinity / -Infinity). These bars MUST never reach the
    replay engine — they would propagate as nan-driven decisions.
    """

GRANULARITY_TO_MINUTES = {
    "M1": 1, "M2": 2, "M5": 5, "M10": 10, "M15": 15, "M30": 30,
    "H1": 60, "H2": 120, "H4": 240, "D": 60 * 24,
}

# Pip size per pair. Anything not in this map is treated as 0.0001.
PIP_SIZE = {
    "EUR_USD": 0.0001,
    "GBP_USD": 0.0001,
    "AUD_USD": 0.0001,
    "USD_JPY": 0.01,
    "USD_CHF": 0.0001,
    "USD_CAD": 0.0001,
}


def _parse_oanda_time(s: str) -> Optional[datetime]:
    """Parse an OANDA RFC3339 timestamp into tz-aware UTC."""
    if not s:
        return None
    try:
        # OANDA returns "...Z" with optional fractional seconds.
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _candle_mid(c: Dict[str, Any]) -> Optional[float]:
    if "mid" in c and c["mid"]:
        try:
            v = float(c["mid"]["c"])
        except (KeyError, TypeError, ValueError):
            return None
        # H1: NaN / +-Inf must never propagate into replay decisions.
        if not math.isfinite(v):
            raise InvalidCandleError(
                f"non-finite mid.c={c['mid']['c']!r} at time={c.get('time')!r}"
            )
        return v
    return None


def _candle_bid_ask_spread(c: Dict[str, Any], pip_size: float) -> Optional[float]:
    bid = c.get("bid", {})
    ask = c.get("ask", {})
    try:
        b = float(bid["c"])
        a = float(ask["c"])
    except (KeyError, TypeError, ValueError):
        return None
    # H1: refuse non-finite bid/ask outright — these poison the spread avg.
    if not (math.isfinite(b) and math.isfinite(a)):
        raise InvalidCandleError(
            f"non-finite bid/ask at time={c.get('time')!r}: bid={bid.get('c')!r}, ask={ask.get('c')!r}"
        )
    if a < b:
        return None  # corrupt
    return (a - b) / pip_size


def check_quality(
    candles: Iterable[Dict[str, Any]],
    pair: str,
    granularity: str = "M15",
) -> Dict[str, Any]:
    """Return a quality report dict over the candle iterable."""
    granularity_minutes = GRANULARITY_TO_MINUTES.get(granularity)
    pip_size = PIP_SIZE.get(pair, 0.0001)
    if pair not in PIP_SIZE:
        _log.warning("pair %s pip-size defaulted to 0.0001", pair)

    total = 0
    duplicates = 0
    stale = 0
    non_complete = 0
    naive_count = 0
    spreads: List[float] = []

    seen_times: set = set()
    parsed_times: List[datetime] = []

    rows = list(candles)  # we walk twice
    for c in rows:
        total += 1
        t = c.get("time")
        if not c.get("complete", True):
            non_complete += 1

        # Volume-zero detection. OANDA returns int volume.
        try:
            v = int(c.get("volume", 0))
        except (TypeError, ValueError):
            v = 0
        if v == 0:
            stale += 1

        dt = _parse_oanda_time(t) if t else None
        if t and dt is None:
            naive_count += 1
        if dt is not None:
            if dt in seen_times:
                duplicates += 1
            else:
                seen_times.add(dt)
                parsed_times.append(dt)

        # H1: validate mid finite — raises InvalidCandleError if NaN/Inf.
        _ = _candle_mid(c)

        # Spread (also raises InvalidCandleError on non-finite bid/ask).
        sp = _candle_bid_ask_spread(c, pip_size)
        if sp is not None:
            spreads.append(sp)

    # Gap analysis: expected step is granularity_minutes; weekend gaps
    # (Friday close → Sunday open) are marked but counted separately.
    gaps_minutes_max = 0.0
    missing_bars = 0
    weekend_gaps = 0
    parsed_times.sort()
    if granularity_minutes is not None and len(parsed_times) >= 2:
        step = timedelta(minutes=granularity_minutes)
        for i in range(1, len(parsed_times)):
            delta = parsed_times[i] - parsed_times[i - 1]
            minutes = delta.total_seconds() / 60.0
            if minutes > granularity_minutes * 1.5:
                # Could be a weekend (Fri ~21:00 UTC → Sun ~21:00 UTC ≈ 48h)
                if 40 * 60 < minutes < 56 * 60:
                    weekend_gaps += 1
                    continue
                gaps_minutes_max = max(gaps_minutes_max, minutes)
                # number of missed bars in this gap
                missing_bars += max(0, int(minutes // granularity_minutes) - 1)

    spread_avg_pips = (sum(spreads) / len(spreads)) if spreads else None

    return {
        "pair": pair,
        "granularity": granularity,
        "total_bars": total,
        "missing_bars": missing_bars,
        "gaps_minutes_max": gaps_minutes_max,
        "duplicate_ts_count": duplicates,
        "stale_bars_volume_zero": stale,
        "non_complete_bars": non_complete,
        "timezone_naive_count": naive_count,
        "spread_avg_pips": spread_avg_pips,
        "weekend_gaps_detected": weekend_gaps,
        "first_ts": parsed_times[0].isoformat() if parsed_times else None,
        "last_ts": parsed_times[-1].isoformat() if parsed_times else None,
    }


def is_acceptable(report: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Decide whether a quality report passes the bar for replay use.

    Returns (ok, reasons). Strict thresholds:
      * total_bars >= 1000 (we need a real history)
      * duplicates == 0
      * missing_bars / total_bars < 0.02
      * non_complete_bars == 0
    """
    reasons: List[str] = []
    ok = True
    if report.get("total_bars", 0) < 1000:
        ok = False
        reasons.append(f"too few bars ({report.get('total_bars')})")
    if report.get("duplicate_ts_count", 0) > 0:
        ok = False
        reasons.append(f"duplicates present ({report.get('duplicate_ts_count')})")
    miss = report.get("missing_bars", 0)
    tot = report.get("total_bars", 1) or 1
    if miss / tot > 0.02:
        ok = False
        reasons.append(f"missing-bar ratio too high ({miss}/{tot})")
    if report.get("non_complete_bars", 0) > 0:
        ok = False
        reasons.append(f"non-complete bars present ({report.get('non_complete_bars')})")
    # H8 (defense-in-depth): if spread_avg_pips is non-finite, fail closed.
    spread_avg = report.get("spread_avg_pips")
    if spread_avg is not None and not math.isfinite(spread_avg):
        ok = False
        reasons.append("spread_not_finite")
    return ok, reasons
