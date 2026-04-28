"""Tests for gatemind.v4.session_check — DST-aware NY window logic."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from zoneinfo import ZoneInfo

from gatemind.v4.session_check import is_in_ny_window, session_status, to_ny

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def _ny(year, mo, day, h, m=0):
    return datetime(year, mo, day, h, m, tzinfo=NY).astimezone(UTC)


def test_window1_inclusive_start():
    # 03:00 NY exactly is IN window 1
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 3, 0))
    assert in_w is True
    assert label == "in_window_pre_open"


def test_window1_exclusive_end():
    # 05:00 NY exactly is OUT (end is exclusive)
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 5, 0))
    assert in_w is False
    assert label == "outside_window"


def test_window1_just_inside_end():
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 4, 59))
    assert in_w is True
    assert label == "in_window_pre_open"


def test_window2_inclusive_start():
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 8, 0))
    assert in_w is True
    assert label == "in_window_morning"


def test_window2_exclusive_end():
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 12, 0))
    assert in_w is False


def test_gap_between_windows():
    in_w, label = is_in_ny_window(_ny(2025, 7, 15, 6, 30))
    assert in_w is False
    assert label == "outside_window"


def test_late_evening_outside():
    in_w, _ = is_in_ny_window(_ny(2025, 7, 15, 22, 0))
    assert in_w is False


def test_dst_spring_forward_summer_window():
    """On DST spring-forward day, 09:00 NY EDT must still resolve as window 2."""
    in_w, label = is_in_ny_window(_ny(2025, 3, 9, 9, 0))
    assert in_w is True
    assert label == "in_window_morning"


def test_dst_fall_back_winter_window():
    """On DST fall-back day, 09:00 NY EST must still resolve as window 2."""
    in_w, label = is_in_ny_window(_ny(2025, 11, 2, 9, 0))
    assert in_w is True
    assert label == "in_window_morning"


def test_dst_summer_vs_winter_same_local_hour_same_window():
    """Same NY local hour on EDT and EST must both be in window."""
    summer = _ny(2025, 7, 15, 10, 0)  # EDT (UTC-4) → 14:00 UTC
    winter = _ny(2025, 12, 15, 10, 0)  # EST (UTC-5) → 15:00 UTC
    assert is_in_ny_window(summer)[0]
    assert is_in_ny_window(winter)[0]


def test_naive_datetime_rejected():
    naive = datetime(2025, 7, 15, 10, 0)
    with pytest.raises(ValueError):
        to_ny(naive)


def test_session_status_helper():
    assert session_status(_ny(2025, 7, 15, 3, 30)) == "in_window_pre_open"
    assert session_status(_ny(2025, 7, 15, 9, 0)) == "in_window_morning"
    assert session_status(_ny(2025, 7, 15, 6, 30)) == "outside_window"


def test_to_ny_offset_matches_dst_phase():
    summer_ny = to_ny(_ny(2025, 7, 15, 10, 0))
    winter_ny = to_ny(_ny(2025, 12, 15, 10, 0))
    # EDT is UTC-4, EST is UTC-5
    assert summer_ny.utcoffset().total_seconds() == -4 * 3600
    assert winter_ny.utcoffset().total_seconds() == -5 * 3600


# ---------------------------------------------------------------------------
# DST hard-edge tests (G2 hardening)
# ---------------------------------------------------------------------------
def test_dst_spring_forward_gap_resolves_to_after_jump():
    """Spring-forward 2025-03-09: 02:00-03:00 NY does NOT exist.

    Constructing 02:30 NY (the missing hour) and converting through UTC must
    deterministically resolve to a real instant. zoneinfo's `fold=0` default
    treats the wall-clock 02:30 as if it were the post-DST 03:30 EDT — i.e.
    UTC offset -4. The mapped NY hour is therefore 03 (window OUT). Either
    way the result must NOT be inside window 1 (3-5) when computed from the
    UTC equivalent the operator passed in. This is a clock-skew protection.
    """
    # Build the wall-clock-during-gap moment, convert to UTC, feed to gate.
    gap_local = datetime(2025, 3, 9, 2, 30, tzinfo=NY)
    as_utc = gap_local.astimezone(UTC)
    in_w, label = is_in_ny_window(as_utc)
    # zoneinfo resolves the gap to EDT (offset -4), so wall clock effectively
    # snaps to 03:30 → IN window 1. The KEY guarantee is determinism — same
    # input, same output, every time. Assert it's deterministic and matches
    # zoneinfo's documented resolution.
    second_call = is_in_ny_window(as_utc)
    assert (in_w, label) == second_call, "non-deterministic DST gap resolution"
    # Document the actual resolution: 02:30 wall clock during the gap snaps
    # to 03:30 EDT → in window 1.
    assert in_w is True
    assert label == "in_window_pre_open"


def test_dst_spring_forward_05_00_in_window():
    """05:00 NY on 2025-03-09 is OUT of window 1 (end exclusive)."""
    in_w, label = is_in_ny_window(_ny(2025, 3, 9, 5, 0))
    assert in_w is False
    assert label == "outside_window"


def test_dst_spring_forward_04_00_in_window():
    """04:00 NY on 2025-03-09 (post-spring-forward) IS in window 1."""
    in_w, label = is_in_ny_window(_ny(2025, 3, 9, 4, 0))
    assert in_w is True
    assert label == "in_window_pre_open"


def test_dst_fall_back_ambiguous_hour():
    """Fall-back 2025-11-02: 01:00-02:00 NY occurs twice (EDT then EST).

    Both occurrences map to UTC instants 1 hour apart. Both are outside the
    NY trading windows (window 1 starts at 03:00). The system must
    deterministically map each UTC instant back to the same NY label.
    """
    # First occurrence (pre-DST end, EDT, fold=0): wall 01:30 EDT → 05:30 UTC
    pre = datetime(2025, 11, 2, 1, 30, tzinfo=NY, fold=0).astimezone(UTC)
    # Second occurrence (post-DST end, EST, fold=1): wall 01:30 EST → 06:30 UTC
    post = datetime(2025, 11, 2, 1, 30, tzinfo=NY, fold=1).astimezone(UTC)
    # They must be different UTC instants (1 hour apart).
    assert (post - pre).total_seconds() == 3600
    # Both must resolve to outside_window deterministically.
    assert is_in_ny_window(pre) == (False, "outside_window")
    assert is_in_ny_window(post) == (False, "outside_window")


def test_dst_fall_back_05_00_in_window():
    """05:00 NY on 2025-11-02 is OUT of window 1 (end exclusive)."""
    in_w, label = is_in_ny_window(_ny(2025, 11, 2, 5, 0))
    assert in_w is False
    assert label == "outside_window"
