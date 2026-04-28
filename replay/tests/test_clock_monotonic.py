"""ReplayClock must be monotonic and tz-aware."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from replay.replay_clock import ReplayClock, ReplayClockError


def test_clock_starts_at_start():
    s = datetime(2024, 1, 1, tzinfo=timezone.utc)
    c = ReplayClock(s)
    assert c.now() == s


def test_clock_advances_forward():
    s = datetime(2024, 1, 1, tzinfo=timezone.utc)
    c = ReplayClock(s)
    later = s + timedelta(hours=1)
    c.advance_to(later)
    assert c.now() == later
    assert c.step_count == 1


def test_clock_refuses_rewind():
    s = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    c = ReplayClock(s)
    earlier = s - timedelta(hours=1)
    with pytest.raises(ReplayClockError):
        c.advance_to(earlier)


def test_clock_refuses_naive_start():
    with pytest.raises(ValueError):
        ReplayClock(datetime(2024, 1, 1))


def test_clock_refuses_naive_advance():
    s = datetime(2024, 1, 1, tzinfo=timezone.utc)
    c = ReplayClock(s)
    with pytest.raises(ValueError):
        c.advance_to(datetime(2024, 1, 2))


def test_clock_same_time_allowed():
    """Advancing to the same time is a no-op, not an error."""
    s = datetime(2024, 1, 1, tzinfo=timezone.utc)
    c = ReplayClock(s)
    c.advance_to(s)
    assert c.now() == s
