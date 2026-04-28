"""SmartNoteBook V4 — time integrity helpers.

Enforces:
  * timestamp_utc is tz-aware UTC
  * timestamp_ny is the same instant rendered in America/New_York for ops
  * sequence_id is monotonic *per process* — attackers cannot rewind it

The `SequenceCounter` is process-local. Across restarts, sequence resets to
0 BUT records still chain via prev_hash, so monotonicity within a JSONL day
file is maintained by the chain hash, not by sequence_id alone.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Tuple

from zoneinfo import ZoneInfo

NY_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc


def utc_now() -> datetime:
    """tz-aware UTC now. The only blessed source of `now` in the notebook."""
    return datetime.now(UTC)


def to_ny(when_utc: datetime) -> datetime:
    """Convert a tz-aware UTC datetime to America/New_York."""
    if when_utc.tzinfo is None:
        raise ValueError("to_ny requires tz-aware UTC datetime")
    return when_utc.astimezone(NY_TZ)


def assert_utc(when: datetime) -> None:
    """Raise if `when` is naive or non-UTC."""
    if when.tzinfo is None:
        raise ValueError("timestamp must be tz-aware")
    if when.utcoffset().total_seconds() != 0:
        raise ValueError(
            f"timestamp must be UTC, got offset {when.utcoffset()}"
        )


def to_iso_utc(when_utc: datetime) -> str:
    """ISO 8601 with explicit Z suffix, microsecond precision."""
    assert_utc(when_utc)
    # Force trailing Z (json convention) instead of +00:00
    return when_utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def parse_iso_utc(s: str) -> datetime:
    """Inverse of to_iso_utc."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SequenceCounter:
    """Process-local monotonic sequence id.

    Each call to .next() returns a strictly increasing integer. Thread-safe.
    """

    def __init__(self, start: int = 0) -> None:
        self._n = start
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._n += 1
            return self._n

    def peek(self) -> int:
        with self._lock:
            return self._n

    def reset(self, value: int = 0) -> None:
        """Test-only — resets to a known value. Not for production use."""
        with self._lock:
            self._n = value

    def set_floor(self, min_value: int) -> None:
        """S7 — Bump counter to at least `min_value`. Idempotent. Used by
        Storage.__init__ to seed the counter from MAX(sequence_id) found
        in the SQLite mirror so two notebook instances pointed at the
        same base_dir do not reuse sequence_ids 1..N.
        """
        with self._lock:
            if min_value > self._n:
                self._n = min_value


# Singleton — production code uses this. Tests can construct their own.
_GLOBAL_COUNTER = SequenceCounter()


def next_sequence_id() -> int:
    return _GLOBAL_COUNTER.next()


def reset_sequence_counter(value: int = 0) -> None:
    """Test-only helper."""
    _GLOBAL_COUNTER.reset(value)


def set_counter_floor(min_value: int) -> None:
    """S7 — Bump the global sequence counter to at least `min_value`.

    Called by Storage.__init__ after seeding from SQLite MAX(sequence_id)
    so that fresh notebook processes don't collide with a prior
    instance's sequence range.
    """
    _GLOBAL_COUNTER.set_floor(min_value)


def peek_sequence_id() -> int:
    """Return the current counter value without incrementing."""
    return _GLOBAL_COUNTER.peek()


def now_pair() -> Tuple[datetime, datetime]:
    """Return (utc, ny) for the current instant."""
    u = utc_now()
    return u, to_ny(u)
