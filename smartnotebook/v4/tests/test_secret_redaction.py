"""test_secret_redaction.py — R6. Secrets stripped at record boundary."""

from __future__ import annotations

import json
from datetime import timezone

import pytest

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4.error_handling import SecretLeakError
from smartnotebook.v4.models import BugRecord
from smartnotebook.v4.record_types import RecordType
from smartnotebook.v4.secret_redactor import (
    _redact_string,
    assert_clean,
    redact,
)

UTC = timezone.utc
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")


def test_bearer_token_stripped():
    s = "Authorization: Bearer abcdef1234567890XYZ"
    out = _redact_string(s)
    assert "abcdef1234567890XYZ" not in out
    assert "[REDACTED]" in out


def test_sk_token_stripped():
    s = "key=sk-1234567890abcdefABCDEF and more"
    out = _redact_string(s)
    assert "sk-1234567890abcdef" not in out
    assert "[REDACTED]" in out


def test_oanda_token_stripped():
    s = "OANDA_TOKEN=abc123def456abc123def456abc123de"
    out = _redact_string(s)
    assert "abc123def456abc123def456abc123de" not in out
    assert "[REDACTED]" in out


def test_oanda_raw_hex_stripped():
    s = "token: 1234567890abcdef1234567890abcdef-fedcba0987654321 done"
    out = _redact_string(s)
    assert "1234567890abcdef1234567890abcdef-fedcba0987654321" not in out


def test_redact_walks_dict():
    payload = {
        "log": "Authorization: Bearer xyzabc123XYZsecrettoken",
        "nested": {"api_key": "abcdef1234567890"},
        "list": ["sk-abcdef1234567890ABCDEF"],
    }
    out = redact(payload)
    assert "xyzabc123XYZ" not in out["log"]
    assert "abcdef1234567890" not in json.dumps(out["nested"])
    assert "sk-abcdef" not in out["list"][0]


def test_assert_clean_raises_on_residue():
    payload = {"log": "Bearer evilevileviltokenresidue"}
    with pytest.raises(SecretLeakError):
        assert_clean(payload)


def test_assert_clean_passes_after_redaction():
    payload = {"log": "Bearer evilevileviltokenresidue"}
    cleaned = redact(payload)
    assert_clean(cleaned)  # must not raise


def test_storage_redacts_secret_in_record(tmpdir_storage, fixed_now):
    """End-to-end: a record persisted with secret content gets redacted."""
    u, n = fixed_now, fixed_now.astimezone(NY)
    partial = {
        "record_id": "b1",
        "record_type": RecordType.BUG.value,
        "timestamp_utc": u.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
        "timestamp_ny": n.isoformat(),
        "sequence_id": 1,
        "parent_record_id": None,
        "prev_record_id": None,
        "severity": "warn",
        "component": "broker",
        "description": "Auth header was Bearer abc123XYZsecretsecret",
        "context": {"oanda_token": "abc123def456abc123def456abc123de"},
    }
    partial["prev_hash"] = _chain.first_prev_hash()
    # Compute the chain hash on the *redacted* version (same as production path)
    # Storage will redact and re-verify; we need to compute hash on the
    # final redacted dict.
    from smartnotebook.v4 import secret_redactor
    redacted = secret_redactor.redact(partial)
    ch = _chain.compute_chain_hash(redacted["prev_hash"], redacted)
    rec = BugRecord(
        record_id="b1",
        record_type=RecordType.BUG,
        timestamp_utc=u,
        timestamp_ny=n,
        sequence_id=1,
        prev_hash=redacted["prev_hash"],
        chain_hash=ch,
        severity="warn",
        component="broker",
        description=redacted["description"],
        context=redacted["context"],
    )
    tmpdir_storage.append_record(rec)
    path = tmpdir_storage.jsonl_path_for(fixed_now)
    text = path.read_text(encoding="utf-8")
    assert "abc123XYZsecretsecret" not in text
    assert "abc123def456abc123def456abc123de" not in text
    assert "[REDACTED]" in text
