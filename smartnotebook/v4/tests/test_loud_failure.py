"""test_loud_failure.py — R4. Disk-full / OS errors raise LedgerWriteError."""

from __future__ import annotations

from unittest import mock

import pytest

from smartnotebook.v4.error_handling import LedgerWriteError


def test_R4_disk_full_raises(tmpdir_storage, factory, fixed_now, monkeypatch):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    from pathlib import Path
    real_path_open = Path.open

    def boom(self, *a, **kw):
        if str(self).endswith(".jsonl") and ((a and a[0] == "a") or kw.get("mode") == "a"):
            raise OSError(28, "No space left on device")
        return real_path_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", boom)
    with pytest.raises(LedgerWriteError, match="JSONL append failed"):
        tmpdir_storage.append_record(rec)


def test_R4_sqlite_failure_raises(tmpdir_storage, factory, fixed_now, monkeypatch):
    """Patch sqlite3.connect to fail when storage tries to mirror."""
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    import sqlite3
    real_connect = sqlite3.connect
    call_count = {"n": 0}

    def fail_on_first(*a, **kw):
        # Storage is already constructed (init connects once before this patch).
        # The next sqlite call is the SQLite mirror inside append_record.
        call_count["n"] += 1
        if call_count["n"] >= 1:
            raise sqlite3.OperationalError("disk image is malformed")
        return real_connect(*a, **kw)

    monkeypatch.setattr("smartnotebook.v4.storage.sqlite3.connect", fail_on_first)
    with pytest.raises(LedgerWriteError, match="SQLite mirror failed"):
        tmpdir_storage.append_record(rec)


def test_R4_no_silent_swallow(tmpdir_storage, factory, fixed_now, monkeypatch):
    """The critical path must not silently log-and-continue."""
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    from pathlib import Path
    real_path_open = Path.open

    def boom(self, *a, **kw):
        if str(self).endswith(".jsonl") and ((a and a[0] == "a") or kw.get("mode") == "a"):
            raise OSError(13, "Permission denied")
        return real_path_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", boom)
    try:
        tmpdir_storage.append_record(rec)
        pytest.fail("append_record returned without raising LedgerWriteError")
    except LedgerWriteError:
        pass  # correct
