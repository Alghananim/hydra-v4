"""test_hardening.py — regression tests for the V4 hardening pass.

Covers fixes S1-S8 found by Multi-Reviewer + Red Team:
  S1  concurrent write chain fork (CRITICAL)
  S2  HMAC-SHA256 forge resistance (CRITICAL)
  S3  secret redactor escapes (HIGH)
  S4  object.__setattr__ frozen bypass (HIGH)
  S5  non-monotonic timestamps (MEDIUM)
  S6  SQLite-JSONL divergence on read (MEDIUM)
  S7  cross-process sequence_id collisions (MEDIUM)
  S8  magic numbers + missing logging (LOW)

Each test re-attacks the original break and asserts the system fails
CLOSED (raises) or quietly enforces the invariant.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4 import secret_redactor as _redactor
from smartnotebook.v4 import time_integrity
from smartnotebook.v4.error_handling import (
    ChainBrokenError,
    LedgerWriteError,
    NonMonotonicTimestampError,
    SecretLeakError,
    StorageConsistencyError,
)
from smartnotebook.v4.notebook_constants import (
    HMAC_KEY_ENV,
    SESSION_MORNING_END_HOUR,
    SESSION_MORNING_START_HOUR,
    SESSION_PRE_OPEN_END_HOUR,
    SESSION_PRE_OPEN_START_HOUR,
)
from smartnotebook.v4.record_types import RecordType
from smartnotebook.v4.storage import Storage

UTC = timezone.utc


# ---------------------------------------------------------------------------
# S1 — Concurrent write chain fork (CRITICAL)
# ---------------------------------------------------------------------------
def test_concurrent_writes_no_chain_fork(tmp_path, factory, fixed_now):
    """4 threads x 5 records each, all writing to the same day file.
    After all complete, verify_chain_for_day must return OK.

    The pre-S1 bug: each thread reads `last_chain_hash_for_day` BEFORE
    acquiring the file write lock, computes its own chain_hash against
    that stale prev_hash, and the writes fork. After fix, append_record
    reads prev_hash and computes chain_hash atomically inside _lock.
    """
    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)

    # Use a thread-safe global timestamp counter so timestamps are
    # strictly monotonic regardless of thread interleaving (S5).
    ts_counter = {"n": 0}
    ts_lock = threading.Lock()

    def next_when():
        with ts_lock:
            ts_counter["n"] += 1
            return fixed_now + timedelta(microseconds=ts_counter["n"] * 1000)

    errors = []

    def worker(idx: int):
        try:
            for j in range(5):
                when = next_when()
                rec = factory["decision_cycle"](
                    storage=storage,
                    when=when,
                    symbol=f"SYM{idx}",
                )
                storage.append_record(rec)
        except Exception as e:  # noqa
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"unexpected errors: {errors}"

    # All 20 records persisted
    persisted = list(storage.iter_records_for_day(fixed_now))
    assert len(persisted) == 20, f"expected 20 records, got {len(persisted)}"

    # The chain MUST verify even with concurrent writers.
    storage.verify_chain_for_day(fixed_now)
    storage.verify_full_chain()


# ---------------------------------------------------------------------------
# S2 — HMAC mode and fallback warning
# ---------------------------------------------------------------------------
def test_hmac_mode_detects_forgery(tmp_path, factory, fixed_now, monkeypatch):
    """With HMAC_KEY set, an attacker who appends a forged JSONL line
    cannot mint a valid chain_hash without the key. verify_chain raises.
    """
    monkeypatch.setenv(HMAC_KEY_ENV, "super-secret-key-do-not-leak")
    _chain._reset_hmac_warning_for_tests()

    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)
    rec = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec)

    # Verify clean state
    storage.verify_chain_for_day(fixed_now)

    # Attacker forges a record using PLAIN sha256 (since they don't have
    # the HMAC key).
    path = storage.jsonl_path_for(fixed_now)
    last_line = path.read_text(encoding="utf-8").splitlines()[-1]
    last = json.loads(last_line)

    forged = {
        "record_id": "forged-1",
        "record_type": RecordType.DECISION_CYCLE.value,
        "timestamp_utc": (fixed_now + timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        ) + "Z",
        "timestamp_ny": (fixed_now + timedelta(seconds=1)).isoformat(),
        "sequence_id": 999,
        "parent_record_id": None,
        "prev_record_id": None,
        "symbol": "EVIL",
        "session_window": "outside",
        "newsmind_output": {},
        "marketmind_output": {},
        "chartmind_output": {},
        "gatemind_output": {},
        "final_status": "ENTER_CANDIDATE",
        "blocking_reason": "",
        "evidence_summary": ["forged"],
        "risk_flags": [],
        "data_quality_summary": {},
        "model_versions": {},
        "prev_hash": last["chain_hash"],
    }
    # Compute chain_hash with PLAIN sha256 (attacker doesn't have key)
    import hashlib
    payload = _chain.canonical_json(forged)
    sep = b"\x1f"
    msg = forged["prev_hash"].encode() + sep + payload.encode()
    forged["chain_hash"] = hashlib.sha256(msg).hexdigest()

    # Append forged line to JSONL
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(forged) + "\n")

    # Verification should now FAIL — HMAC compute does not match plain sha256
    with pytest.raises(ChainBrokenError):
        storage.verify_chain_for_day(fixed_now)


def test_no_hmac_key_falls_back_to_sha256_with_warning(
    tmp_path, factory, fixed_now, monkeypatch, caplog
):
    """When HYDRA_NOTEBOOK_HMAC_KEY is unset, chain_hash uses plain sha256
    AND a WARNING is emitted so operators know they're in insecure mode.
    """
    monkeypatch.delenv(HMAC_KEY_ENV, raising=False)
    _chain._reset_hmac_warning_for_tests()

    with caplog.at_level(logging.WARNING, logger="smartnotebook"):
        storage = Storage(tmp_path / "ledger")
        time_integrity.reset_sequence_counter(0)
        rec = factory["decision_cycle"](storage=storage, when=fixed_now)
        storage.append_record(rec)
        storage.verify_chain_for_day(fixed_now)  # plain sha256 OK

    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "HYDRA_NOTEBOOK_HMAC_KEY" in msgs
    assert "tamper-detection only" in msgs


def test_hmac_chain_hash_differs_from_plain(monkeypatch):
    """HMAC mode must produce a DIFFERENT chain_hash than plain sha256."""
    monkeypatch.delenv(HMAC_KEY_ENV, raising=False)
    _chain._reset_hmac_warning_for_tests()
    payload = {
        "record_id": "x",
        "prev_hash": "0" * 64,
        "field": "value",
    }
    plain = _chain.compute_chain_hash("0" * 64, payload)

    monkeypatch.setenv(HMAC_KEY_ENV, "secret")
    hmac_h = _chain.compute_chain_hash("0" * 64, payload)
    assert plain != hmac_h, "HMAC mode produced identical hash to plain sha256"


# ---------------------------------------------------------------------------
# S3 — Secret redactor escapes
# ---------------------------------------------------------------------------
def test_redactor_catches_aws_keys():
    s = "my access key is AKIAIOSFODNN7EXAMPLE done"
    out = _redactor._redact_string(s)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED]" in out


def test_redactor_catches_aws_secret_key_dict():
    payload = {
        "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_session_token": "FQoDYXdzEJr...veryverylongtokenstring",
    }
    out = _redactor.redact(payload)
    for v in out.values():
        assert v == "[REDACTED]", f"unexpected residue: {v}"


def test_redactor_catches_jwt():
    s = "auth: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.f4k3sig123_-XYZ"
    out = _redactor._redact_string(s)
    assert "eyJhbGc" not in out
    assert "[REDACTED]" in out


def test_redactor_catches_unicode_obfuscation_bearer():
    """Soft-hyphen U+00AD inside 'Bearer' must NOT defeat redaction."""
    # "Be" + soft-hyphen + "arer"
    s = "Be­arer abcdef1234567890XYZ"
    out = _redactor._redact_string(s)
    assert "abcdef1234567890XYZ" not in out
    assert "[REDACTED]" in out


def test_redactor_catches_unicode_obfuscation_sk():
    """Zero-width-space inside sk- prefix must NOT defeat redaction."""
    s = "key: sk​-1234567890abcdefABCDEF and more"
    out = _redactor._redact_string(s)
    assert "1234567890abcdefABCDEF" not in out
    assert "[REDACTED]" in out


def test_redactor_catches_short_password_values():
    """`password=test` (4 chars) must still be redacted."""
    s = "config: password=test other=value"
    out = _redactor._redact_string(s)
    assert "password=test" not in out
    assert "[REDACTED]" in out


def test_redactor_catches_pwd_dict_key():
    payload = {"pwd": "abc", "pass": "1234"}
    out = _redactor.redact(payload)
    assert out["pwd"] == "[REDACTED]"
    assert out["pass"] == "[REDACTED]"


def test_assert_clean_raises_on_aws_key():
    payload = {"log": "AKIAIOSFODNN7EXAMPLE"}
    with pytest.raises(SecretLeakError):
        _redactor.assert_clean(payload)


def test_assert_clean_raises_on_jwt():
    payload = {"log": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.f4k3sig123_-XYZ"}
    with pytest.raises(SecretLeakError):
        _redactor.assert_clean(payload)


# ---------------------------------------------------------------------------
# S4 — object.__setattr__ bypass
# ---------------------------------------------------------------------------
def test_object_setattr_bypass_blocked(tmpdir_storage, factory, fixed_now):
    """object.__setattr__(rec, "symbol", "X") must raise — frozen=True
    alone does not block this; the FrozenDict swap does."""
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(rec, "symbol", "X")
    # Field unchanged
    assert rec.symbol == "EUR_USD"


def test_normal_setattr_blocked(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    with pytest.raises((AttributeError,)):
        rec.symbol = "BTC_USD"


def test_delattr_blocked(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    with pytest.raises((AttributeError,)):
        del rec.symbol


def test_object_delattr_blocked(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    with pytest.raises((AttributeError, TypeError)):
        object.__delattr__(rec, "symbol")


# ---------------------------------------------------------------------------
# S5 — Backwards timestamp rejected
# ---------------------------------------------------------------------------
def test_backwards_timestamp_rejected(tmp_path, factory, fixed_now):
    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)

    later = fixed_now + timedelta(seconds=10)
    rec_later = factory["decision_cycle"](storage=storage, when=later)
    storage.append_record(rec_later)

    rec_earlier = factory["decision_cycle"](storage=storage, when=fixed_now)
    with pytest.raises(NonMonotonicTimestampError):
        storage.append_record(rec_earlier)


def test_equal_timestamp_accepted(tmp_path, factory, fixed_now):
    """Equal timestamps (sub-millisecond ties) are allowed."""
    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)

    rec1 = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec1)
    rec2 = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec2)  # must not raise


# ---------------------------------------------------------------------------
# S6 — SQLite tampering detected by consistency check
# ---------------------------------------------------------------------------
def test_sqlite_tamper_detected_by_consistency_check(tmp_path, factory, fixed_now):
    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)
    rec = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec)

    # Baseline: consistency holds
    storage.verify_storage_consistency()

    # Tamper: corrupt SQLite chain_hash directly
    sq_path = tmp_path / "ledger" / "ledger.sqlite"
    with sqlite3.connect(str(sq_path)) as conn:
        conn.execute(
            "UPDATE records SET chain_hash = ? WHERE record_id = ?",
            ("0" * 64, rec.record_id),
        )
        conn.commit()

    with pytest.raises(StorageConsistencyError):
        storage.verify_storage_consistency()


def test_sqlite_missing_row_detected_by_consistency_check(tmp_path, factory, fixed_now):
    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)
    rec = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec)

    sq_path = tmp_path / "ledger" / "ledger.sqlite"
    with sqlite3.connect(str(sq_path)) as conn:
        conn.execute("DELETE FROM records WHERE record_id = ?", (rec.record_id,))
        conn.commit()

    with pytest.raises(StorageConsistencyError):
        storage.verify_storage_consistency()


# ---------------------------------------------------------------------------
# S7 — Sequence counter seeded from SQLite
# ---------------------------------------------------------------------------
def test_sequence_counter_seeded_from_sqlite_at_startup(tmp_path, factory, fixed_now):
    """Two notebook instances pointed at the same base_dir must NOT reuse
    sequence_ids 1, 2, 3, ..."""
    base = tmp_path / "ledger"
    time_integrity.reset_sequence_counter(0)

    s1 = Storage(base)
    rec_a = factory["decision_cycle"](storage=s1, when=fixed_now)
    s1.append_record(rec_a)
    rec_b = factory["decision_cycle"](storage=s1, when=fixed_now + timedelta(seconds=1))
    s1.append_record(rec_b)

    high_water = time_integrity.peek_sequence_id()
    assert high_water >= 2

    # Simulate a second process: reset the in-memory counter to 0,
    # then construct a NEW Storage on the same base_dir.
    time_integrity.reset_sequence_counter(0)
    s2 = Storage(base)
    # Counter must now be seeded from SQLite MAX(sequence_id) >= high_water
    assert time_integrity.peek_sequence_id() >= high_water

    # Next sequence id from s2 must be strictly greater than every used id.
    next_id = time_integrity.next_sequence_id()
    used_ids = {r["sequence_id"] for r in s2.query_by_type(RecordType.DECISION_CYCLE)}
    assert next_id not in used_ids
    assert next_id > max(used_ids)


def test_set_counter_floor_idempotent():
    time_integrity.reset_sequence_counter(0)
    time_integrity.set_counter_floor(100)
    assert time_integrity.peek_sequence_id() == 100
    time_integrity.set_counter_floor(50)  # no-op
    assert time_integrity.peek_sequence_id() == 100
    time_integrity.set_counter_floor(200)
    assert time_integrity.peek_sequence_id() == 200


# ---------------------------------------------------------------------------
# S8 — Magic numbers + logging
# ---------------------------------------------------------------------------
def test_session_constants_exposed():
    assert SESSION_MORNING_START_HOUR == 3
    assert SESSION_MORNING_END_HOUR == 5
    assert SESSION_PRE_OPEN_START_HOUR == 8
    assert SESSION_PRE_OPEN_END_HOUR == 12


def test_session_classifier_uses_constants():
    """The classifier must use the named constants — verified by changing
    a literal-vs-constant test would be brittle, so we just sanity-check
    the boundaries."""
    import importlib
    sn_mod = importlib.import_module("smartnotebook.v4.SmartNoteBookV4")
    _classify_session = sn_mod._classify_session
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
    # Inside morning window
    assert _classify_session(datetime(2025, 7, 15, 4, 0, 0, tzinfo=NY)) == "morning_3_5"
    # Inside pre-open window
    assert _classify_session(datetime(2025, 7, 15, 9, 0, 0, tzinfo=NY)) == "pre_open_8_12"
    # Outside both
    assert _classify_session(datetime(2025, 7, 15, 6, 0, 0, tzinfo=NY)) == "outside"
    assert _classify_session(datetime(2025, 7, 15, 13, 0, 0, tzinfo=NY)) == "outside"


def test_logger_present_in_modules():
    """Each critical module exposes a `_log` named 'smartnotebook'."""
    import importlib
    from smartnotebook.v4 import storage as _s
    from smartnotebook.v4 import secret_redactor as _sr
    from smartnotebook.v4 import chain_hash as _ch
    _nb = importlib.import_module("smartnotebook.v4.SmartNoteBookV4")
    for mod in (_s, _sr, _ch, _nb):
        assert hasattr(mod, "_log"), f"{mod.__name__} missing _log"
        assert mod._log.name == "smartnotebook"


def test_chain_mismatch_logs_warning(tmp_path, factory, fixed_now, monkeypatch, caplog):
    """When verify_chain detects a mismatch, a WARNING is logged."""
    monkeypatch.delenv(HMAC_KEY_ENV, raising=False)
    _chain._reset_hmac_warning_for_tests()

    storage = Storage(tmp_path / "ledger")
    time_integrity.reset_sequence_counter(0)
    rec = factory["decision_cycle"](storage=storage, when=fixed_now)
    storage.append_record(rec)
    rec2 = factory["decision_cycle"](
        storage=storage, when=fixed_now + timedelta(seconds=1)
    )
    storage.append_record(rec2)

    # Tamper
    path = storage.jsonl_path_for(fixed_now)
    lines = path.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[1])
    obj["symbol"] = "TAMPERED"
    lines[1] = json.dumps(obj)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="smartnotebook"):
        with pytest.raises(ChainBrokenError):
            storage.verify_chain_for_day(fixed_now)
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "chain mismatch" in msgs.lower() or "prev_hash mismatch" in msgs.lower()
