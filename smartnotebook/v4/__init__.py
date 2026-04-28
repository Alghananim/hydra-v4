"""SmartNoteBook V4 — institutional ledger for HYDRA.

Public surface: SmartNoteBookV4 + record dataclasses + custom exceptions.
"""

from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
from smartnotebook.v4.error_handling import (
    AppendOnlyViolation,
    ChainBrokenError,
    LedgerError,
    LedgerWriteError,
    LessonLeakError,
    NonMonotonicTimestampError,
    SecretLeakError,
    StorageConsistencyError,
)
from smartnotebook.v4.models import (
    BaseRecord,
    BugRecord,
    DailySummaryRecord,
    DecisionCycleRecord,
    ExecutedTradeRecord,
    GateAuditRecord,
    LessonRecord,
    MindPerformanceRecord,
    RejectedTradeRecord,
    ShadowOutcomeRecord,
    TradeOutcomeRecord,
    WeeklySummaryRecord,
)
from smartnotebook.v4.record_types import LessonState, RecordType, ShadowStatus

__all__ = [
    "SmartNoteBookV4",
    "RecordType",
    "LessonState",
    "ShadowStatus",
    "BaseRecord",
    "DecisionCycleRecord",
    "GateAuditRecord",
    "RejectedTradeRecord",
    "ShadowOutcomeRecord",
    "ExecutedTradeRecord",
    "TradeOutcomeRecord",
    "MindPerformanceRecord",
    "LessonRecord",
    "BugRecord",
    "DailySummaryRecord",
    "WeeklySummaryRecord",
    "LedgerError",
    "LedgerWriteError",
    "ChainBrokenError",
    "LessonLeakError",
    "SecretLeakError",
    "AppendOnlyViolation",
    "NonMonotonicTimestampError",
    "StorageConsistencyError",
]
