"""LIQ_RULE — three-flag liquidity / session classifier.

Spec (Phase 1 audit + Hardening Pass):
  flag_spread:   spread anomaly. Triggers if ANY of:
                   (a) current spread > absolute pair ceiling (e.g. EUR/USD 5 pips)
                   (b) current spread > 2 * adversarially-anchored baseline
                       baseline = min(rolling 60-bar median,
                                      sticky 7-session P5 baseline)
                       sticky baseline only RATCHETS DOWN — an attacker walking
                       the median up over 60 bars cannot raise it.
                   (c) current spread > 3 * rolling-min(60) — last-resort
                       backstop when both (a) and (b) miss.
  flag_volume:   bar volume < 40% of same-hour-of-day mean over last 20 sessions
  flag_offsess:  CURRENT WALL-CLOCK timestamp (now_utc) is OUTSIDE NY active
                 windows.  Bar timestamp is NOT used: a stale 6h-old bar must
                 not lock us into "active session".
  Combine:
    0 flags                  -> good
    1 flag                   -> fair
    2 or 3 flags             -> poor
    flag_offsess set         -> forces 'off-session' (overrides)

NY active windows (UTC):
  - London open / overlap:  07:00 - 12:00 UTC
  - NY core:               12:00 - 21:00 UTC
  We treat 21:00 - 07:00 UTC as "off-session" for FX majors.

If we lack enough bars or hour-of-day history, we mark `unknown`.
"""
from __future__ import annotations

from typing import Sequence, Tuple, Dict, Any, List, Optional
from datetime import datetime

from marketmind.v4.models import Bar


SPREAD_LOOKBACK = 60
SPREAD_MULT = 2.0
SPREAD_MIN_MULT = 3.0              # backstop: current > 3x rolling-min(60)
VOLUME_BASELINE_SESSIONS = 20      # ~20 same-hour observations
VOLUME_FRACTION_FLOOR = 0.40

ACTIVE_HOURS_UTC = set(range(7, 21))   # 07:00..20:59 UTC inclusive

# Absolute per-pair spread ceilings (pips). Anything above is auto-flagged
# regardless of any moving baseline — defeats slow-drift baseline poisoning.
PAIR_SPREAD_CEILING_PIPS: Dict[str, float] = {
    "EURUSD": 5.0,
    "GBPUSD": 5.0,
    "USDJPY": 5.0,
    "USDCHF": 5.0,
    "AUDUSD": 5.0,
    "NZDUSD": 5.0,
    "USDCAD": 5.0,
    "EURJPY": 6.0,
    "GBPJPY": 7.0,
    "XAUUSD": 50.0,
}
DEFAULT_SPREAD_CEILING_PIPS = 8.0   # conservative default for unknown pairs


# Sticky 7-session P5 baseline state, keyed by pair. Initialized lazily.
# Only ratchets DOWN (so an attacker walking spread up can never raise it).
_STICKY_P5_BASELINE: Dict[str, float] = {}
STICKY_INIT_BARS = 60                       # initialize from first 60-bar median
STICKY_LOOKBACK_BARS = 7 * 24 * 4           # 7 sessions @ 15-min bars


def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 == 1 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def _percentile(xs: List[float], p: float) -> float:
    """Simple percentile (0..100). p=5 -> low end of distribution."""
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    k = max(0, min(n - 1, int(round((p / 100.0) * (n - 1)))))
    return s[k]


def is_off_session(ts: datetime) -> bool:
    return ts.hour not in ACTIVE_HOURS_UTC


def _normalize_pair(pair: Optional[str]) -> str:
    if not pair:
        return ""
    return pair.upper().replace("/", "").replace("-", "").replace("_", "")


def _ceiling_for(pair: Optional[str]) -> float:
    p = _normalize_pair(pair)
    return PAIR_SPREAD_CEILING_PIPS.get(p, DEFAULT_SPREAD_CEILING_PIPS)


def _update_sticky_p5(pair: Optional[str], spread_history: List[float]) -> Optional[float]:
    """Maintain a sticky P5 baseline that only ratchets DOWN.

    - If state is empty, initialize from the first STICKY_INIT_BARS median.
    - On subsequent calls, recompute the rolling P5 of the last
      STICKY_LOOKBACK_BARS spreads.  If new P5 < stored, update.  If new P5 is
      higher (attacker drift), KEEP the stored value.

    Returns the current sticky baseline or None if not yet initialized.
    """
    key = _normalize_pair(pair) or "_GLOBAL_"
    if not spread_history:
        return _STICKY_P5_BASELINE.get(key)

    # Initialize from first STICKY_INIT_BARS median if we have enough samples.
    if key not in _STICKY_P5_BASELINE:
        if len(spread_history) >= STICKY_INIT_BARS:
            init = _median(spread_history[-STICKY_INIT_BARS:])
            if init > 0:
                _STICKY_P5_BASELINE[key] = init
        # While not initialized, return None — caller must fall back.
        return _STICKY_P5_BASELINE.get(key)

    # Rolling P5 over the last STICKY_LOOKBACK_BARS spreads.
    window = spread_history[-STICKY_LOOKBACK_BARS:]
    candidate = _percentile(window, 5.0)
    if candidate > 0 and candidate < _STICKY_P5_BASELINE[key]:
        # Ratchet DOWN only.
        _STICKY_P5_BASELINE[key] = candidate
    return _STICKY_P5_BASELINE[key]


def reset_sticky_state() -> None:
    """Test helper — clear sticky P5 state."""
    _STICKY_P5_BASELINE.clear()


def evaluate(
    bars: Sequence[Bar],
    *,
    pair: Optional[str] = None,
    now_utc: Optional[datetime] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Return (liquidity_state, evidence_dict).

    Args:
      bars: chronological bar history.
      pair: pair symbol (e.g. "EURUSD"); used for absolute spread ceiling and
            sticky baseline keying.  Optional but strongly recommended.
      now_utc: current wall-clock UTC.  Used for off-session detection so
               that a stale bar timestamp can never lock us into "active".
               If None, falls back to the last bar's timestamp (legacy).
    """
    ev: Dict[str, Any] = {"rule": "LIQ_RULE", "pair": _normalize_pair(pair) or None}
    if len(bars) < 5:
        ev["reason"] = f"insufficient_bars({len(bars)}<5)"
        return "unknown", ev

    last = bars[-1]
    flags: List[str] = []

    # Flag 3: off-session — use now_utc when supplied, NEVER bar timestamp alone.
    session_ts = now_utc if now_utc is not None else last.timestamp
    off = is_off_session(session_ts)
    ev["off_session"] = off
    ev["hour_utc"] = session_ts.hour
    ev["session_source"] = "now_utc" if now_utc is not None else "bar_ts_fallback"
    if off:
        flags.append("off_session")

    # ---- Flag 1: spread anomaly (multi-check, drift-resistant) -------------
    spread_window = bars[-(SPREAD_LOOKBACK + 1):-1] if len(bars) > SPREAD_LOOKBACK else bars[:-1]
    spreads = [b.spread_pips for b in spread_window if b.spread_pips and b.spread_pips > 0]
    spread_median = _median(spreads) if spreads else 0.0
    cur_spread = float(last.spread_pips or 0.0)

    # Long-history rolling MIN — uses the full available history (not just
    # the last 60 bars).  An attacker who walks the spread up over 60 bars
    # cannot raise this number, because old low-spread bars are still
    # included.  This is the cheapest defense against slow-drift poisoning.
    full_spreads = [b.spread_pips for b in bars[:-1] if b.spread_pips and b.spread_pips > 0]
    spread_min = min(full_spreads) if full_spreads else 0.0

    # Sticky P5 baseline (ratchets-down) using the FULL available spread series
    sticky_p5 = _update_sticky_p5(pair, full_spreads)

    ceiling = _ceiling_for(pair)

    # Anchored baseline = min(rolling 60-bar median, sticky P5).  An attacker
    # who walks the median up cannot ratchet sticky_p5 up.
    if sticky_p5 is not None and sticky_p5 > 0 and spread_median > 0:
        anchored_baseline = min(spread_median, sticky_p5)
    elif spread_median > 0:
        anchored_baseline = spread_median
    elif sticky_p5 is not None and sticky_p5 > 0:
        anchored_baseline = sticky_p5
    else:
        anchored_baseline = 0.0

    ev["spread_median_60"] = round(spread_median, 4)
    ev["spread_sticky_p5"] = round(sticky_p5, 4) if sticky_p5 else None
    ev["spread_anchored_baseline"] = round(anchored_baseline, 4)
    ev["spread_min_60"] = round(spread_min, 4)
    ev["spread_now"] = round(cur_spread, 4)
    ev["spread_ceiling"] = ceiling

    spread_flag = False
    spread_reason: Optional[str] = None

    # (a) Absolute ceiling — defeats slow drift entirely.
    if cur_spread > ceiling:
        spread_flag = True
        spread_reason = f"absolute_ceiling({cur_spread:.2f}>{ceiling})"
    # (b) Anchored-baseline multiple.
    elif anchored_baseline > 0 and cur_spread > SPREAD_MULT * anchored_baseline:
        spread_flag = True
        spread_reason = (
            f"baseline_multiple({cur_spread:.2f}>{SPREAD_MULT}x{anchored_baseline:.2f})"
        )
    # (c) Last-resort: 3x rolling-min — catches monotonic ramps.
    elif spread_min > 0 and cur_spread > SPREAD_MIN_MULT * spread_min:
        spread_flag = True
        spread_reason = (
            f"min_multiple({cur_spread:.2f}>{SPREAD_MIN_MULT}x{spread_min:.2f})"
        )

    if spread_flag:
        # Keep `wide_spread` for backward-compat tests; add `spread_anomaly`
        # as the canonical hardening token. Both names refer to the SAME
        # anomaly so we count it ONCE in the flag total.
        flags.append("spread_anomaly")
        ev["spread_reason"] = spread_reason
        # legacy alias surfaced in evidence (not counted toward flag total)
        ev["legacy_flag_alias"] = "wide_spread"

    # ---- Flag 2: volume vs same-hour-of-day baseline -----------------------
    same_hour = [b.volume for b in bars[:-1]
                 if b.timestamp.hour == last.timestamp.hour and b.volume > 0]
    same_hour = same_hour[-VOLUME_BASELINE_SESSIONS:]
    vol_baseline = sum(same_hour) / len(same_hour) if same_hour else 0.0
    ev["same_hour_baseline_n"] = len(same_hour)
    ev["same_hour_baseline_mean"] = round(vol_baseline, 4)
    ev["volume_now"] = last.volume
    volume_flag = (
        vol_baseline > 0
        and last.volume > 0
        and last.volume < VOLUME_FRACTION_FLOOR * vol_baseline
    )
    if volume_flag:
        flags.append("low_volume")

    ev["flags"] = flags

    # off-session is sticky: overrides
    if off:
        ev["match"] = "off-session"
        return "off-session", ev

    n = len(flags)
    if n == 0:
        ev["match"] = "good"
        return "good", ev
    if n == 1:
        ev["match"] = "fair"
        return "fair", ev
    ev["match"] = f"poor({n}_flags)"
    return "poor", ev
