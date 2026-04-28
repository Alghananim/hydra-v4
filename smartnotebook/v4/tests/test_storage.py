"""test_storage.py — JSONL+SQLite append-only invariants.

Covers R1 (no update_record), R8 (JSONL is SOT, sqlite rebuild equivalence).
"""

from __future__ import annotations

import json
from datetime import timezone

import pytest

from smartnotebook.v4.error_handling import AppendOnlyViolation
from smartnotebook.v4.record_types import RecordType
from smartnotebook.v4.storage import Storage


def test_no_update_record_method_R1(tmpdir_storage):
    assert not hasattr(Storage, "update_record"), "R1 violation: Storage.update_record exists"


def test_no_delete_record_method_R1(tmpdir_storage):
    assert not hasattr(Storage, "delete_record"), "R1 violation: Storage.delete_record exists"


def test_dynamic_update_raises_R1(tmpdir_storage):
    # Defense against dynamic attr access
    with pytest.raises(AppendOnlyViolation):
        _ = tmpdir_storage.update_record


def test_dynamic_delete_raises_R1(tmpdir_storage):
    with pytest.raises(AppendOnlyViolation):
        _ = tmpdir_storage.delete_record


def test_append_writes_jsonl_and_sqlite(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)

    # JSONL — read directly
    path = tmpdir_storage.jsonl_path_for(fixed_now)
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["record_id"] == rec.record_id

    # SQLite query
    rows = tmpdir_storage.query_by_type(RecordType.DECISION_CYCLE)
    assert len(rows) == 1
    assert rows[0]["record_id"] == rec.record_id


def test_rebuild_sqlite_from_jsonl_R8(tmpdir_storage, factory, fixed_now):
    """R8: rebuild_sqlite_from_jsonl produces identical SQLite contents."""
    # write a few
    for i in range(3):
        rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
        tmpdir_storage.append_record(rec)

    before = tmpdir_storage.query_by_type(RecordType.DECISION_CYCLE)
    n = tmpdir_storage.rebuild_sqlite_from_jsonl()
    after = tmpdir_storage.query_by_type(RecordType.DECISION_CYCLE)

    assert n == 3
    assert len(after) == 3
    ids_before = sorted(r["record_id"] for r in before)
    ids_after = sorted(r["record_id"] for r in after)
    assert ids_before == ids_after


def test_query_by_parent(tmpdir_storage, factory, fixed_now):
    parent = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(parent)
    child = factory["gate_audit"](
        storage=tmpdir_storage, decision_cycle_id=parent.record_id, when=fixed_now
    )
    tmpdir_storage.append_record(child)

    rows = tmpdir_storage.query_by_parent(parent.record_id)
    assert len(rows) == 1
    assert rows[0]["audit_id"] == child.audit_id


def test_get_by_id(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    fetched = tmpdir_storage.get_by_id(rec.record_id)
    assert fetched is not None
    assert fetched["record_id"] == rec.record_id


def test_iter_records_for_day(tmpdir_storage, factory, fixed_now):
    for _ in range(2):
        rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
        tmpdir_storage.append_record(rec)
    recs = list(tmpdir_storage.iter_records_for_day(fixed_now))
    assert len(recs) == 2
