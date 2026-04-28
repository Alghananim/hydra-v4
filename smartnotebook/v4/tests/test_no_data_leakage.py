"""test_no_data_leakage.py — adversarial: try to inject future state.

Red Team scenarios:
  1. Activate a lesson with allowed_from_timestamp 30 days in the future.
     Replaying as-of "today" must NOT see this lesson. (R5)
  2. Construct an ACTIVE LessonRecord without allowed_from_timestamp →
     must raise at construction time.
  3. Try to retroactively backdate an ACTIVE lesson by submitting a
     RETIRED record with an *older* timestamp than activation. The
     ledger is append-only; latest wins — so a retired record after
     activation supersedes activation.
  4. Try to supply replay_clock that's naive — must raise.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from smartnotebook.v4 import SmartNoteBookV4
from smartnotebook.v4 import lesson_engine
from smartnotebook.v4.error_handling import LessonLeakError
from smartnotebook.v4.record_types import LessonState

UTC = timezone.utc


def test_adversarial_future_lesson_excluded(tmp_path, fixed_now):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    nb.propose_lesson(
        lesson_id="L_future",
        lesson_text="future lesson",
        affected_mind="newsmind",
        evidence=["e"],
        source_records=[],
        proposed_rule_change={"type": "block"},
        now_utc=fixed_now,
    )
    nb.activate_lesson(
        lesson_id="L_future",
        allowed_from_timestamp=fixed_now + timedelta(days=30),
        now_utc=fixed_now,
    )
    # replaying as-of fixed_now must not see L_future
    active = nb.load_active_lessons(fixed_now)
    assert all(l.get("lesson_id") != "L_future" for l in active)


def test_adversarial_active_lesson_without_allowed_from_raises():
    """Constructing an ACTIVE lesson without allowed_from must raise."""
    from smartnotebook.v4 import chain_hash as _ch
    from smartnotebook.v4.models import LessonRecord
    from smartnotebook.v4.record_types import RecordType
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    u = datetime(2025, 7, 15, 14, 0, 0, tzinfo=UTC)
    n = u.astimezone(NY)
    partial = {
        "record_id": "L1", "record_type": RecordType.LESSON.value,
        "timestamp_utc": u.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z", "timestamp_ny": n.isoformat(),
        "sequence_id": 1, "parent_record_id": None, "prev_record_id": None,
        "lesson_id": "L1", "source_records": [], "lesson_text": "x",
        "affected_mind": "n", "evidence": ["e"], "proposed_rule_change": {},
        "state": LessonState.ACTIVE.value, "allowed_from_timestamp": None,
    }
    partial["prev_hash"] = "0" * 64
    ch = _ch.compute_chain_hash(partial["prev_hash"], partial)
    with pytest.raises(ValueError, match="ACTIVE lesson requires allowed_from_timestamp"):
        LessonRecord(
            record_id="L1", record_type=RecordType.LESSON,
            timestamp_utc=u, timestamp_ny=n, sequence_id=1,
            prev_hash=partial["prev_hash"], chain_hash=ch,
            lesson_id="L1", lesson_text="x", affected_mind="n",
            evidence=["e"], state=LessonState.ACTIVE,
            allowed_from_timestamp=None,
        )


def test_adversarial_retire_supersedes_activation(tmp_path, fixed_now):
    """Retired AFTER activation: lesson should not be active."""
    nb = SmartNoteBookV4(tmp_path / "ledger")
    nb.propose_lesson(
        lesson_id="L_retire",
        lesson_text="x", affected_mind="newsmind",
        evidence=["e"], source_records=[],
        proposed_rule_change={"a": 1},
        now_utc=fixed_now,
    )
    nb.activate_lesson(
        lesson_id="L_retire",
        allowed_from_timestamp=fixed_now,
        now_utc=fixed_now + timedelta(seconds=1),
    )
    nb.retire_lesson(
        lesson_id="L_retire",
        now_utc=fixed_now + timedelta(seconds=2),
    )
    active = nb.load_active_lessons(fixed_now + timedelta(seconds=10))
    assert all(l.get("lesson_id") != "L_retire" for l in active)


def test_adversarial_naive_replay_clock_rejected(tmp_path):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    naive = datetime(2025, 7, 15, 14, 0, 0)  # no tz
    with pytest.raises(ValueError):
        nb.load_active_lessons(naive)


def test_adversarial_assert_no_future_leak_catches_smuggle():
    """Even if upstream code attempts to bypass filtering, the explicit
    assertion still catches future-dated lessons."""
    far = datetime(2030, 1, 1, tzinfo=UTC)
    smuggled = [{
        "lesson_id": "L_smuggle",
        "state": "ACTIVE",
        "allowed_from_timestamp": far.isoformat(),
    }]
    with pytest.raises(LessonLeakError):
        lesson_engine.assert_no_future_leak(
            smuggled, datetime(2025, 1, 1, tzinfo=UTC)
        )


def test_adversarial_secrets_in_evidence_redacted(tmp_path, fixed_now):
    """A lesson 'evidence' list containing a token must be redacted before persistence."""
    nb = SmartNoteBookV4(tmp_path / "ledger")
    nb.propose_lesson(
        lesson_id="L_sec",
        lesson_text="never log Bearer abcdefghij1234567890XYZ ever",
        affected_mind="newsmind",
        evidence=["sk-deadbeefdeadbeefdeadbeef0000"],
        source_records=[],
        proposed_rule_change={"note": "Bearer xyzxyzxyz1234567890ABC"},
        now_utc=fixed_now,
    )
    path = nb.storage.jsonl_path_for(fixed_now)
    text = path.read_text(encoding="utf-8")
    assert "abcdefghij1234567890XYZ" not in text
    assert "sk-deadbeef" not in text
    assert "xyzxyzxyz1234567890ABC" not in text
