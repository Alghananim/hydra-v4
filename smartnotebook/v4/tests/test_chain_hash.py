"""test_chain_hash.py — R2 (chain_hash present) and R3 (verify_chain)."""

from __future__ import annotations

import json
from datetime import timezone

import pytest

from smartnotebook.v4 import chain_hash as _chain
from smartnotebook.v4.error_handling import ChainBrokenError


def test_R2_every_persisted_record_has_chain_hash(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)

    path = tmpdir_storage.jsonl_path_for(fixed_now)
    obj = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert obj["chain_hash"]
    assert len(obj["chain_hash"]) == 64  # sha256 hex


def test_R3_verify_chain_passes_unmodified(tmpdir_storage, factory, fixed_now):
    for _ in range(3):
        rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
        tmpdir_storage.append_record(rec)
    # Should not raise
    tmpdir_storage.verify_chain_for_day(fixed_now)
    tmpdir_storage.verify_full_chain()


def test_R3_verify_chain_raises_on_tamper(tmpdir_storage, factory, fixed_now):
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    rec2 = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec2)

    path = tmpdir_storage.jsonl_path_for(fixed_now)
    lines = path.read_text(encoding="utf-8").splitlines()
    # Tamper: change the symbol of the second record but keep its chain_hash
    obj = json.loads(lines[1])
    obj["symbol"] = "BTC_USD"  # mutated AFTER hash was computed
    lines[1] = json.dumps(obj)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ChainBrokenError):
        tmpdir_storage.verify_chain_for_day(fixed_now)


def test_R3_verify_chain_raises_on_byte_flip(tmpdir_storage, factory, fixed_now):
    """Smoke: flipping a single byte in payload causes ChainBrokenError."""
    rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
    tmpdir_storage.append_record(rec)
    path = tmpdir_storage.jsonl_path_for(fixed_now)
    raw = path.read_bytes()
    # Flip a byte that's part of the JSON — somewhere in the middle
    target_idx = len(raw) // 3
    flipped = bytearray(raw)
    # Change "EUR_USD" → "EUR_uSD" if symbol is present, else just change a char
    new_b = b"X"[0] if flipped[target_idx] != b"X"[0] else b"Y"[0]
    flipped[target_idx] = new_b
    path.write_bytes(bytes(flipped))
    with pytest.raises((ChainBrokenError, json.JSONDecodeError, ValueError)):
        tmpdir_storage.verify_chain_for_day(fixed_now)


def test_chain_hash_links_correctly(tmpdir_storage, factory, fixed_now):
    """Each record's prev_hash equals the previous record's chain_hash."""
    for _ in range(3):
        rec = factory["decision_cycle"](storage=tmpdir_storage, when=fixed_now)
        tmpdir_storage.append_record(rec)
    path = tmpdir_storage.jsonl_path_for(fixed_now)
    lines = path.read_text(encoding="utf-8").splitlines()
    objs = [json.loads(l) for l in lines]
    assert objs[0]["prev_hash"] == _chain.first_prev_hash()
    assert objs[1]["prev_hash"] == objs[0]["chain_hash"]
    assert objs[2]["prev_hash"] == objs[1]["chain_hash"]
