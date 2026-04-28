"""SmartNoteBook V4 — lesson lifecycle engine.

States:
  CANDIDATE — newly proposed; NEVER applied to historical replays
  ACTIVE    — enforced from `allowed_from_timestamp` forward
  RETIRED   — superseded or invalidated; not enforced

R5 invariant: load_active_lessons(replay_clock) MUST exclude any lesson
whose allowed_from_timestamp > replay_clock. Activating a lesson and then
running a backtest "as of" before the activation must NOT see that
lesson. Violations raise LessonLeakError.

Append-only model: state transitions are NEW LessonRecords with the
prior lesson_id set as parent_record_id and the same lesson_id reused. The
"current state" of a lesson_id is the most recent record.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional

from smartnotebook.v4.error_handling import LessonLeakError
from smartnotebook.v4.models import LessonRecord
from smartnotebook.v4.record_types import LessonState, RecordType
from smartnotebook.v4.storage import Storage
from smartnotebook.v4.time_integrity import assert_utc


def _latest_state_per_lesson(records: Iterable[Dict]) -> Dict[str, Dict]:
    """Reduce list of LESSON records into the latest record per lesson_id.

    Latest = highest sequence_id.
    """
    latest: Dict[str, Dict] = {}
    for rec in records:
        if rec.get("record_type") != RecordType.LESSON.value:
            continue
        lid = rec.get("lesson_id")
        if not lid:
            continue
        prev = latest.get(lid)
        if prev is None or rec["sequence_id"] > prev["sequence_id"]:
            latest[lid] = rec
    return latest


def load_active_lessons(
    storage: Storage,
    replay_clock: datetime,
) -> List[Dict]:
    """Return the lessons that are ACTIVE *at* `replay_clock`.

    R5: a lesson with allowed_from_timestamp > replay_clock must NOT
    appear in the result.

    Invariant: caller must pass tz-aware UTC `replay_clock`.
    """
    assert_utc(replay_clock)
    all_lessons = storage.query_by_type(RecordType.LESSON)
    latest = _latest_state_per_lesson(all_lessons)
    out: List[Dict] = []
    leaks: List[str] = []
    for lid, rec in latest.items():
        if rec.get("state") != LessonState.ACTIVE.value:
            continue
        afts = rec.get("allowed_from_timestamp")
        if afts is None:
            # ACTIVE without allowed_from_timestamp — would have failed
            # validation at construction. Defensive.
            continue
        # afts is ISO 8601 string in storage
        if isinstance(afts, str):
            from smartnotebook.v4.time_integrity import parse_iso_utc
            afts_dt = parse_iso_utc(afts)
        else:
            afts_dt = afts
        if afts_dt > replay_clock:
            # SHOULD NOT BE RETURNED — R5
            leaks.append(lid)
            continue
        out.append(rec)
    # If we filtered any, that's the *correct* path. Leaks would only
    # surface if a caller bypassed this filter; we never raise here just
    # for filtering. We DO raise if anyone explicitly asks us to validate.
    return out


def assert_no_future_leak(
    candidate_lessons: List[Dict],
    replay_clock: datetime,
) -> None:
    """Adversarial check — used by tests / red-team paths.

    Given a *claimed* set of active lessons, raise LessonLeakError if any
    has allowed_from_timestamp > replay_clock.
    """
    assert_utc(replay_clock)
    from smartnotebook.v4.time_integrity import parse_iso_utc
    leaks: List[str] = []
    for rec in candidate_lessons:
        afts = rec.get("allowed_from_timestamp")
        if afts is None:
            continue
        afts_dt = parse_iso_utc(afts) if isinstance(afts, str) else afts
        if afts_dt > replay_clock:
            leaks.append(rec.get("lesson_id", "?"))
    if leaks:
        raise LessonLeakError(
            f"future-dated lessons leaked into replay_clock={replay_clock}: {leaks}"
        )


# ---------------------------------------------------------------------------
# Convenience builders for the orchestrator
# ---------------------------------------------------------------------------
def transition_state(
    *,
    prior: LessonRecord,
    new_state: LessonState,
    allowed_from_timestamp: Optional[datetime] = None,
    chain_hash: str,
    prev_hash: str,
    record_id: str,
    sequence_id: int,
    timestamp_utc: datetime,
    timestamp_ny: datetime,
) -> LessonRecord:
    """Build a NEW LessonRecord representing a state transition.

    The append-only ledger means transitions are new records with the
    same lesson_id and parent_record_id pointing at `prior`.
    """
    if new_state == LessonState.ACTIVE and allowed_from_timestamp is None:
        raise ValueError("ACTIVE transition requires allowed_from_timestamp")
    return LessonRecord(
        record_id=record_id,
        record_type=RecordType.LESSON,
        timestamp_utc=timestamp_utc,
        timestamp_ny=timestamp_ny,
        sequence_id=sequence_id,
        parent_record_id=prior.record_id,
        prev_record_id=prior.record_id,
        prev_hash=prev_hash,
        chain_hash=chain_hash,
        lesson_id=prior.lesson_id,
        source_records=list(prior.source_records),
        lesson_text=prior.lesson_text,
        affected_mind=prior.affected_mind,
        evidence=list(prior.evidence),
        proposed_rule_change=dict(prior.proposed_rule_change),
        state=new_state,
        allowed_from_timestamp=allowed_from_timestamp,
    )
