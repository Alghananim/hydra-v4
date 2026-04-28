"""test_time_integrity.py — UTC/NY conversion + sequence_id ordering."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from smartnotebook.v4 import time_integrity


def test_utc_now_is_tz_aware():
    u = time_integrity.utc_now()
    assert u.tzinfo is not None
    assert u.utcoffset().total_seconds() == 0


def test_to_ny_requires_tz_aware():
    naive = datetime(2025, 7, 15, 14, 0, 0)
    with pytest.raises(ValueError):
        time_integrity.to_ny(naive)


def test_to_ny_summer_offset_is_minus_4():
    """July 15 2025 in NY is EDT (UTC-4)."""
    u = datetime(2025, 7, 15, 14, 0, 0, tzinfo=timezone.utc)
    n = time_integrity.to_ny(u)
    # 14 UTC → 10 EDT
    assert n.hour == 10


def test_to_ny_winter_offset_is_minus_5():
    """January 15 2025 in NY is EST (UTC-5)."""
    u = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    n = time_integrity.to_ny(u)
    assert n.hour == 9


def test_iso_utc_format_has_z():
    u = datetime(2025, 7, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
    s = time_integrity.to_iso_utc(u)
    assert s.endswith("Z")
    assert "2025-07-15T14:30:45.123456" in s


def test_parse_iso_utc_roundtrip():
    u = datetime(2025, 7, 15, 14, 30, 45, 123456, tzinfo=timezone.utc)
    s = time_integrity.to_iso_utc(u)
    u2 = time_integrity.parse_iso_utc(s)
    assert u == u2


def test_sequence_counter_monotonic():
    c = time_integrity.SequenceCounter()
    a = c.next()
    b = c.next()
    d = c.next()
    assert a < b < d


def test_sequence_counter_thread_safe():
    import threading
    c = time_integrity.SequenceCounter()
    seen = []
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            v = c.next()
            with lock:
                seen.append(v)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seen) == 500
    assert len(set(seen)) == 500   # all unique


def test_assert_utc_rejects_naive():
    with pytest.raises(ValueError):
        time_integrity.assert_utc(datetime(2025, 1, 1))


def test_assert_utc_rejects_non_utc():
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    with pytest.raises(ValueError):
        time_integrity.assert_utc(datetime(2025, 7, 15, 10, 0, 0, tzinfo=ny))
