"""SmartNoteBook V4 — custom exception hierarchy.

Every notebook-level error inherits from `LedgerError` so callers can do a
single fail-closed handler.

These exceptions are LOUD: they are raised on the critical write path. The
notebook does NOT swallow them — the caller (engine) is expected to enter
fail-closed mode.
"""

from __future__ import annotations


class LedgerError(Exception):
    """Base for all SmartNoteBook ledger errors."""


class LedgerWriteError(LedgerError):
    """A write to the JSONL or SQLite ledger failed.

    Raised by Storage.append_record on disk-full, permission denied, or any
    OS-level failure. The engine MUST treat this as fail-closed and stop
    issuing new decisions.

    Critical to R4 — never swallowed.
    """


class ChainBrokenError(LedgerError):
    """The chain hash verification failed.

    Raised by chain_hash.verify_chain when a record's `chain_hash` does not
    match the recomputed hash from `prev_hash || canonical_payload`.

    Critical to R3 — proves the ledger has been tampered with or corrupted.
    """

    def __init__(self, record_id: str, expected: str, actual: str, position: int):
        super().__init__(
            f"Chain broken at record_id={record_id} position={position}: "
            f"expected={expected[:16]}... actual={actual[:16]}..."
        )
        self.record_id = record_id
        self.expected = expected
        self.actual = actual
        self.position = position


class LessonLeakError(LedgerError):
    """A lesson with allowed_from_timestamp > replay_clock was returned.

    Raised by lesson_engine.load_active_lessons when invariants would be
    violated. Critical to R5 — no future leak.
    """


class AppendOnlyViolation(LedgerError):
    """Attempted update / delete on append-only ledger.

    Raised if anyone calls Storage.update_record or .delete_record (the
    methods do not exist; this exception is raised by the explicit
    __getattr__ guard for clearer error messages in case of dynamic access).
    """


class SecretLeakError(LedgerError):
    """A record was about to be persisted with a secret-shaped token.

    Raised by secret_redactor.assert_clean when called for a final
    sanity-check after redaction. Used by Storage as a defense-in-depth
    boundary check.
    """


class NonMonotonicTimestampError(LedgerError):
    """A record's timestamp_utc went backwards relative to the prior record
    in the same JSONL day file.

    Raised by Storage.append_record when `new.timestamp_utc <
    last.timestamp_utc`. Equal timestamps (sub-millisecond ties) are
    accepted. This protects the chain from clock-rewind attacks.
    """


class StorageConsistencyError(LedgerError):
    """SQLite and JSONL diverged: a record exists in one but not the other,
    or chain_hash differs between them.

    Raised by Storage.verify_storage_consistency. Indicates SQLite-only
    tampering or a partial write.
    """
