"""HYDRA V4 — lesson_extractor.

After a replay run, walk DECISION_CYCLE / REJECTED_TRADE /
SHADOW_OUTCOME records and propose CANDIDATE LESSONs.

The KEY invariant (R5): every emitted lesson carries
`allowed_from_timestamp = end_of_replay`. Any future replay starting
*before* that timestamp must NOT be allowed to consult the lesson.
SmartNoteBookV4.load_active_lessons(replay_clock) already filters by
this field; the extractor's job is to set it correctly.

Pattern detection (Phase 1 minimum):
  * If 3+ rejections share the same (rejection_reason, rejecting_mind)
    AND >= 70% of their resolved shadows show the rejection was
    INCORRECT (i.e. the trade would have won), emit a CANDIDATE
    lesson asking to RELAX that rule.
  * If 3+ rejections share the pattern AND >= 70% of resolved shadows
    show the rejection was CORRECT, emit a CANDIDATE lesson asking
    to KEEP the rule.

This keeps the engine simple but real — the user's "نظام تداول حقيقي"
demand. No fake smart-engine claims.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("replay.lessons")


@dataclass
class ProposedLesson:
    pattern_key: Tuple[str, str]
    affected_mind: str
    lesson_text: str
    evidence_record_ids: List[str]
    proposed_rule_change: Dict[str, Any]
    allowed_from_timestamp: datetime
    direction: str  # "RELAX" | "KEEP"


def extract_candidate_lessons(
    rejected_records: List[Any],
    shadow_records: List[Any],
    end_of_replay: datetime,
    min_count: int = 3,
    correctness_threshold: float = 0.7,
) -> List[ProposedLesson]:
    """Return a list of ProposedLesson objects. The caller persists them
    via SmartNoteBookV4.propose_lesson(...)."""
    if end_of_replay.tzinfo is None:
        raise ValueError("end_of_replay must be tz-aware UTC")

    # Build map: rejected_record_id -> RejectedTradeRecord
    by_id: Dict[str, Any] = {}
    for r in rejected_records:
        rid = getattr(r, "record_id", None) or (r.get("record_id") if isinstance(r, dict) else None)
        if rid:
            by_id[rid] = r

    # Group shadows by (reason, mind).
    groups: Dict[Tuple[str, str], List[Tuple[Any, Any]]] = defaultdict(list)
    for s in shadow_records:
        rt_id = getattr(s, "rejected_trade_id", None) or (
            s.get("rejected_trade_id") if isinstance(s, dict) else None
        )
        if rt_id is None or rt_id not in by_id:
            continue
        rec = by_id[rt_id]
        reason = getattr(rec, "rejection_reason", None) or (
            rec.get("rejection_reason") if isinstance(rec, dict) else ""
        )
        mind = getattr(rec, "rejecting_mind", None) or (
            rec.get("rejecting_mind") if isinstance(rec, dict) else ""
        )
        groups[(str(reason), str(mind))].append((rec, s))

    out: List[ProposedLesson] = []
    for (reason, mind), pairs in groups.items():
        if len(pairs) < min_count:
            continue
        correct = sum(
            1 for (_, s) in pairs
            if (getattr(s, "was_rejection_correct", None)
                if not isinstance(s, dict) else s.get("was_rejection_correct"))
        )
        ratio_correct = correct / len(pairs)
        if ratio_correct >= correctness_threshold:
            direction = "KEEP"
            text = (
                f"Reject pattern (mind={mind}, reason={reason!r}) was correct "
                f"in {correct}/{len(pairs)} cases — keep this rule."
            )
            change = {"action": "keep", "reason": reason, "mind": mind}
        elif (1.0 - ratio_correct) >= correctness_threshold:
            direction = "RELAX"
            text = (
                f"Reject pattern (mind={mind}, reason={reason!r}) was wrong "
                f"in {len(pairs) - correct}/{len(pairs)} cases — propose relaxing."
            )
            change = {"action": "relax", "reason": reason, "mind": mind}
        else:
            continue

        evidence_ids = []
        for (rec, s) in pairs:
            rid = getattr(rec, "record_id", None) or rec.get("record_id")
            sid = getattr(s, "record_id", None) or s.get("record_id")
            if rid:
                evidence_ids.append(rid)
            if sid:
                evidence_ids.append(sid)

        out.append(ProposedLesson(
            pattern_key=(str(reason), str(mind)),
            affected_mind=str(mind),
            lesson_text=text,
            evidence_record_ids=evidence_ids,
            proposed_rule_change=change,
            allowed_from_timestamp=end_of_replay,
            direction=direction,
        ))
    return out
