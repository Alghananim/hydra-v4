"""test_error_handling.py — custom exceptions raised correctly."""

from __future__ import annotations

import pytest

from smartnotebook.v4.error_handling import (
    AppendOnlyViolation,
    ChainBrokenError,
    LedgerError,
    LedgerWriteError,
    LessonLeakError,
    SecretLeakError,
)


def test_all_inherit_from_ledger_error():
    assert issubclass(LedgerWriteError, LedgerError)
    assert issubclass(ChainBrokenError, LedgerError)
    assert issubclass(LessonLeakError, LedgerError)
    assert issubclass(AppendOnlyViolation, LedgerError)
    assert issubclass(SecretLeakError, LedgerError)


def test_chain_broken_error_carries_context():
    e = ChainBrokenError(record_id="r1", expected="a" * 64, actual="b" * 64, position=2)
    assert "r1" in str(e)
    assert e.record_id == "r1"
    assert e.position == 2


def test_ledger_write_error_message():
    e = LedgerWriteError("disk full")
    assert "disk full" in str(e)


def test_secret_leak_error_message():
    e = SecretLeakError("found bearer")
    assert "bearer" in str(e)
