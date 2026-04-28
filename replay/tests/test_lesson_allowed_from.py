"""Lessons extracted at end_of_replay must carry that timestamp as
allowed_from_timestamp — and a backtester starting earlier must NOT
load them."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from replay.lesson_extractor import ProposedLesson, extract_candidate_lessons


@dataclass
class _Rejected:
    record_id: str
    rejection_reason: str
    rejecting_mind: str


@dataclass
class _Shadow:
    record_id: str
    rejected_trade_id: str
    was_rejection_correct: bool


def test_lesson_allowed_from_is_at_end_of_replay():
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    rejs = [
        _Rejected(record_id=f"r{i}", rejection_reason="low_grade", rejecting_mind="MarketMind")
        for i in range(5)
    ]
    shadows = [
        _Shadow(record_id=f"s{i}", rejected_trade_id=f"r{i}", was_rejection_correct=False)
        for i in range(5)
    ]
    lessons = extract_candidate_lessons(rejs, shadows, end_of_replay=end)
    assert len(lessons) == 1
    assert lessons[0].allowed_from_timestamp == end
    assert lessons[0].direction == "RELAX"


def test_lesson_keep_when_rejections_were_correct():
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    rejs = [
        _Rejected(record_id=f"r{i}", rejection_reason="news_blackout", rejecting_mind="NewsMind")
        for i in range(5)
    ]
    shadows = [
        _Shadow(record_id=f"s{i}", rejected_trade_id=f"r{i}", was_rejection_correct=True)
        for i in range(5)
    ]
    lessons = extract_candidate_lessons(rejs, shadows, end_of_replay=end)
    assert len(lessons) == 1
    assert lessons[0].direction == "KEEP"


def test_lesson_no_emit_below_min_count():
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    rejs = [_Rejected(record_id="r1", rejection_reason="x", rejecting_mind="M")]
    shadows = [_Shadow(record_id="s1", rejected_trade_id="r1", was_rejection_correct=False)]
    lessons = extract_candidate_lessons(rejs, shadows, end_of_replay=end, min_count=3)
    assert lessons == []


def test_lesson_no_emit_when_split_outcomes():
    """3+ rejections but only 50% correct → no clear lesson."""
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    rejs = [_Rejected(record_id=f"r{i}", rejection_reason="x", rejecting_mind="M") for i in range(6)]
    shadows = [
        _Shadow(record_id=f"s{i}", rejected_trade_id=f"r{i}",
                was_rejection_correct=(i % 2 == 0))
        for i in range(6)
    ]
    lessons = extract_candidate_lessons(rejs, shadows, end_of_replay=end)
    assert lessons == []


def test_lesson_with_future_allowed_from_excluded_by_load():
    """If a lesson's allowed_from is AFTER replay clock, a backtester must
    not load it. We assert the contract: the lesson stamp is at end-of-replay,
    so any clock < end MUST be excluded by the SmartNoteBook filter.
    This is a contract assertion against the field shape."""
    end = datetime(2024, 6, 30, tzinfo=timezone.utc)
    rejs = [_Rejected(record_id=f"r{i}", rejection_reason="x", rejecting_mind="M") for i in range(5)]
    shadows = [_Shadow(record_id=f"s{i}", rejected_trade_id=f"r{i}",
                       was_rejection_correct=False) for i in range(5)]
    lessons = extract_candidate_lessons(rejs, shadows, end_of_replay=end)
    L = lessons[0]
    # Backtester check: a clock t < L.allowed_from_timestamp filters it out.
    backtester_clock = end - timedelta(days=30)
    assert backtester_clock < L.allowed_from_timestamp
    # And t >= allowed_from would include it
    later_clock = end + timedelta(seconds=1)
    assert later_clock >= L.allowed_from_timestamp


def test_naive_end_of_replay_rejected():
    rejs = [_Rejected(record_id=f"r{i}", rejection_reason="x", rejecting_mind="M") for i in range(5)]
    shadows = [_Shadow(record_id=f"s{i}", rejected_trade_id=f"r{i}",
                       was_rejection_correct=False) for i in range(5)]
    with pytest.raises(ValueError):
        extract_candidate_lessons(rejs, shadows, end_of_replay=datetime(2024, 1, 1))


# ---------------------------------------------------------------------------
# H7: prove the FILTER, not just the field shape.
# Integration: real SmartNoteBookV4, real lesson_engine.load_active_lessons.
# ---------------------------------------------------------------------------
def test_lesson_with_future_allowed_from_actually_filtered_by_smartnotebook(tmp_path):
    """End-to-end: persist a lesson via SmartNoteBookV4 with
    allowed_from_timestamp = 2030-01-01. Calling load_active_lessons
    with replay_clock = 2024-12-31 must NOT return that lesson — proving
    the SmartNoteBook filter actually FILTERS, not just stores the field.
    """
    from smartnotebook.v4 import SmartNoteBookV4

    nb = SmartNoteBookV4(tmp_path / "ledger_h7")
    proposed_at = datetime(2024, 12, 1, tzinfo=timezone.utc)
    activate_at = datetime(2024, 12, 15, tzinfo=timezone.utc)
    future_allowed_from = datetime(2030, 1, 1, tzinfo=timezone.utc)

    nb.propose_lesson(
        lesson_id="L_h7_future",
        lesson_text="future-only lesson — must be invisible to earlier replays",
        affected_mind="MarketMind",
        evidence=["e1", "e2"],
        source_records=[],
        proposed_rule_change={"action": "relax", "rule": "low_grade"},
        now_utc=proposed_at,
    )
    nb.activate_lesson(
        lesson_id="L_h7_future",
        allowed_from_timestamp=future_allowed_from,
        now_utc=activate_at,
    )

    earlier_clock = datetime(2024, 12, 31, tzinfo=timezone.utc)
    active = nb.load_active_lessons(earlier_clock)
    assert all(l.get("lesson_id") != "L_h7_future" for l in active), (
        "SmartNoteBook returned a lesson with allowed_from_timestamp in "
        "the future — R5 leak!"
    )

    # Sanity: the SAME lesson IS visible once the replay clock advances
    # past allowed_from.
    later_clock = datetime(2030, 1, 2, tzinfo=timezone.utc)
    active_later = nb.load_active_lessons(later_clock)
    assert any(l.get("lesson_id") == "L_h7_future" for l in active_later), (
        "After allowed_from_timestamp, the lesson MUST be loadable."
    )


def test_lesson_with_exact_allowed_from_timestamp_visible(tmp_path):
    """Boundary: replay_clock == allowed_from_timestamp must INCLUDE the
    lesson (the filter is `afts > clock`, not `afts >= clock`)."""
    from smartnotebook.v4 import SmartNoteBookV4

    nb = SmartNoteBookV4(tmp_path / "ledger_h7_boundary")
    activate_at = datetime(2024, 12, 1, tzinfo=timezone.utc)
    afts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    nb.propose_lesson(
        lesson_id="L_h7_boundary",
        lesson_text="boundary lesson",
        affected_mind="ChartMind",
        evidence=["e"],
        source_records=[],
        proposed_rule_change={"action": "keep"},
        now_utc=activate_at,
    )
    nb.activate_lesson(
        lesson_id="L_h7_boundary",
        allowed_from_timestamp=afts,
        now_utc=activate_at,
    )
    active_at_exact = nb.load_active_lessons(afts)
    assert any(l.get("lesson_id") == "L_h7_boundary" for l in active_at_exact)
