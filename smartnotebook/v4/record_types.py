"""SmartNoteBook V4 — record type enum.

Single source of truth for the kinds of records the ledger persists. Every
BaseRecord carries one of these values; Storage uses the enum for routing
and SQLite indexing.
"""

from __future__ import annotations

from enum import Enum


class RecordType(str, Enum):
    """Kinds of records persisted in the SmartNoteBook ledger.

    Inherits from str so JSON serialization is automatic.
    """

    DECISION_CYCLE = "DECISION_CYCLE"
    GATE_AUDIT = "GATE_AUDIT"
    REJECTED_TRADE = "REJECTED_TRADE"
    SHADOW_OUTCOME = "SHADOW_OUTCOME"
    EXECUTED_TRADE = "EXECUTED_TRADE"
    TRADE_OUTCOME = "TRADE_OUTCOME"
    MIND_PERFORMANCE = "MIND_PERFORMANCE"
    LESSON = "LESSON"
    BUG = "BUG"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    WEEKLY_SUMMARY = "WEEKLY_SUMMARY"


class LessonState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ShadowStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVED_WIN = "RESOLVED_WIN"
    RESOLVED_LOSS = "RESOLVED_LOSS"
    RESOLVED_BREAKEVEN = "RESOLVED_BREAKEVEN"
