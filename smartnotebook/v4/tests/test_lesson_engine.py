"""test_lesson_engine.py — R5 future-leak prevention + lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from smartnotebook.v4 import lesson_engine
from smartnotebook.v4.error_handling import LessonLeakError
from smartnotebook.v4.record_types import LessonState

UTC = timezone.utc


def test_R5_future_dated_lesson_excluded(tmpdir_storage, factory, fixed_now):
    """An ACTIVE lesson with allowed_from > replay_clock must not appear."""
    far_future = fixed_now + timedelta(days=30)
    rec = factory["lesson_active"](
        storage=tmpdir_storage,
        allowed_from=far_future,
        when=fixed_now,
    )
    tmpdir_storage.append_record(rec)

    # Replay clock is "now" (before allowed_from)
    active = lesson_engine.load_active_lessons(tmpdir_storage, fixed_now)
    assert len(active) == 0


def test_R5_lesson_appears_at_or_after_allowed_from(tmpdir_storage, factory, fixed_now):
    allowed_from = fixed_now - timedelta(days=1)
    rec = factory["lesson_active"](
        storage=tmpdir_storage,
        allowed_from=allowed_from,
        when=fixed_now,
    )
    tmpdir_storage.append_record(rec)
    active = lesson_engine.load_active_lessons(tmpdir_storage, fixed_now)
    assert len(active) == 1


def test_R5_assert_no_future_leak_raises():
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    bad = [{
        "lesson_id": "L1",
        "state": "ACTIVE",
        "allowed_from_timestamp": far_future.isoformat(),
    }]
    with pytest.raises(LessonLeakError):
        lesson_engine.assert_no_future_leak(bad, datetime(2025, 1, 1, tzinfo=UTC))


def test_R5_assert_no_future_leak_passes_when_clean():
    past = datetime(2020, 1, 1, tzinfo=UTC)
    good = [{
        "lesson_id": "L1",
        "state": "ACTIVE",
        "allowed_from_timestamp": past.isoformat(),
    }]
    # Must not raise
    lesson_engine.assert_no_future_leak(good, datetime(2025, 1, 1, tzinfo=UTC))


def test_lesson_lifecycle_candidate_to_active(tmpdir_storage, factory, fixed_now):
    cand = factory["lesson_candidate"](storage=tmpdir_storage, lesson_id="LX", when=fixed_now)
    tmpdir_storage.append_record(cand)
    # Now activate via orchestrator
    from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
    nb = SmartNoteBookV4.__new__(SmartNoteBookV4)
    nb._storage = tmpdir_storage
    activated = nb.activate_lesson(
        lesson_id="LX",
        allowed_from_timestamp=fixed_now,
        now_utc=fixed_now,
    )
    assert activated.state == LessonState.ACTIVE
    assert activated.lesson_id == "LX"
    assert activated.parent_record_id == cand.record_id


def test_candidate_lessons_never_active(tmpdir_storage, factory, fixed_now):
    cand = factory["lesson_candidate"](storage=tmpdir_storage, lesson_id="LX", when=fixed_now)
    tmpdir_storage.append_record(cand)
    active = lesson_engine.load_active_lessons(tmpdir_storage, fixed_now)
    assert len(active) == 0
