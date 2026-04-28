"""HYDRA V4 — leakage_guard.

Tools to PROVE that no future bar leaks into the orchestrator's view.

  * `slice_visible(bars, now_utc)` — return bars with timestamp <= now.
  * `assert_no_future(bars, now_utc)` — raise if any bar has ts > now.

Used both inside the replay engine AND inside adversarial tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class LeakageError(RuntimeError):
    pass


def _bar_time(b: Any) -> Optional[datetime]:
    """Extract UTC time from a bar — works with dict candles AND Bar dataclass."""
    # Bar dataclass instance (has .timestamp attribute)
    if hasattr(b, "timestamp") and not isinstance(b, dict):
        ts = getattr(b, "timestamp", None)
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        return None
    # Dict candle (OANDA-shaped)
    if not isinstance(b, dict):
        return None
    t = b.get("time") or b.get("timestamp")
    if not t:
        return None
    if isinstance(t, datetime):
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc)
    if not isinstance(t, str):
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def slice_visible(bars: List[Dict[str, Any]], now_utc: datetime) -> List[Dict[str, Any]]:
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware UTC")
    out: List[Dict[str, Any]] = []
    for b in bars:
        bt = _bar_time(b)
        if bt is None:
            continue
        if bt <= now_utc:
            out.append(b)
    return out


def assert_no_future(bars: List[Dict[str, Any]], now_utc: datetime) -> None:
    for b in bars:
        bt = _bar_time(b)
        if bt is not None and bt > now_utc:
            raise LeakageError(
                f"future bar in visible set: bar_time={bt.isoformat()} > now={now_utc.isoformat()}"
            )


def assert_chronological(bars: List[Dict[str, Any]]) -> None:
    last: Optional[datetime] = None
    for b in bars:
        bt = _bar_time(b)
        if bt is None:
            continue
        if last is not None and bt < last:
            raise LeakageError(
                f"bars not chronological: {bt.isoformat()} after {last.isoformat()}"
            )
        last = bt
