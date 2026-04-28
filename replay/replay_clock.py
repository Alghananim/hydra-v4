"""HYDRA V4 — replay_clock.

Monotonic chronological clock. The orchestrator MUST query `now()` to
obtain the current replay time; it MUST NOT use `datetime.utcnow()`
during a replay.

The clock starts at `start_utc`, advances only via `advance_to(t)` or
`tick()` to next bar, and refuses to step backwards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional


class ReplayClockError(RuntimeError):
    pass


class ReplayClock:
    def __init__(self, start_utc: datetime) -> None:
        if start_utc.tzinfo is None:
            raise ValueError("start_utc must be tz-aware UTC")
        self._now: datetime = start_utc.astimezone(timezone.utc)
        self._step_count: int = 0

    def now(self) -> datetime:
        return self._now

    def advance_to(self, target_utc: datetime) -> None:
        if target_utc.tzinfo is None:
            raise ValueError("target_utc must be tz-aware UTC")
        target = target_utc.astimezone(timezone.utc)
        if target < self._now:
            raise ReplayClockError(
                f"refusing to rewind clock from {self._now.isoformat()} "
                f"to {target.isoformat()}"
            )
        self._now = target
        self._step_count += 1

    @property
    def step_count(self) -> int:
        return self._step_count
