"""SmartNoteBook V4 — chain hashing.

Each record carries a `chain_hash` computed as one of:

    chain_hash = sha256( prev_hash || 0x1F || canonical_json(payload) )         # insecure mode
    chain_hash = HMAC-SHA256(key, prev_hash || 0x1F || canonical_json(payload)) # secure mode

where `payload` is the record's full content EXCLUDING the chain_hash field
itself (chicken-and-egg). canonical_json uses sorted keys, no whitespace,
ensure_ascii=False so the encoding is reproducible.

Mode selection (S2):
  * If env var HYDRA_NOTEBOOK_HMAC_KEY is set, HMAC-SHA256 is used. This
    makes the chain_hash forge-resistant — an attacker who can write to
    the JSONL file CANNOT mint a valid chain_hash without the key.
  * If unset, plain sha256 is used. This provides tamper-detection
    (the chain breaks if any record is mutated) but NOT forge-resistance
    (an attacker with write access can append a new record with a
    self-consistent chain_hash).

Documented limit: without HYDRA_NOTEBOOK_HMAC_KEY, chain_hash provides
tamper-detection only, not forge-resistance.

This guarantees:
  * R2 — every record has a non-empty chain_hash (enforced in BaseRecord)
  * R3 — verify_chain replays the chain and raises ChainBrokenError on
    any divergence
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Optional

from smartnotebook.v4.error_handling import ChainBrokenError
from smartnotebook.v4.notebook_constants import (
    GENESIS_PREV_HASH,
    HASH_ALGO,
    HMAC_KEY_ENV,
)

_log = logging.getLogger("smartnotebook")

# Fields that are NOT part of the hashed payload. chain_hash itself is
# excluded (we cannot include the output in the input). prev_hash IS
# included because it's the chain link.
_EXCLUDED_FROM_PAYLOAD = {"chain_hash"}

# One-time warning latch — only complain once when the HMAC key is missing.
_HMAC_WARNING_EMITTED = False


def _get_hmac_key() -> Optional[bytes]:
    """Return the HMAC secret key bytes, or None if not configured.

    Reads HYDRA_NOTEBOOK_HMAC_KEY from the env on every call so test
    suites can monkeypatch it. Emits a one-shot WARNING if the key is
    missing, so operators see they're in insecure mode.
    """
    global _HMAC_WARNING_EMITTED
    raw = os.environ.get(HMAC_KEY_ENV)
    if raw:
        return raw.encode("utf-8")
    if not _HMAC_WARNING_EMITTED:
        _log.warning(
            "HYDRA_NOTEBOOK_HMAC_KEY is not set; chain_hash falls back to "
            "plain sha256. The chain provides tamper-detection only, "
            "not forge-resistance. Set the env var to enable HMAC mode."
        )
        _HMAC_WARNING_EMITTED = True
    return None


def _reset_hmac_warning_for_tests() -> None:
    """Test-only — re-arm the one-shot warning latch."""
    global _HMAC_WARNING_EMITTED
    _HMAC_WARNING_EMITTED = False


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization.

    Rules:
      * sort_keys=True
      * separators=(",", ":") — no whitespace
      * ensure_ascii=False — UTF-8 preserved
      * datetimes serialized as ISO 8601 with Z
      * enums serialized as their .value
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def _json_default(o: Any) -> Any:
    # datetimes
    if hasattr(o, "isoformat"):
        # Force trailing Z
        s = o.isoformat()
        if s.endswith("+00:00"):
            s = s[:-6] + "Z"
        return s
    # enums
    if hasattr(o, "value"):
        return o.value
    # dataclasses
    if is_dataclass(o):
        return asdict(o)
    # bytes
    if isinstance(o, bytes):
        return o.hex()
    raise TypeError(f"Unserializable type: {type(o).__name__}")


def hashable_payload(record_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Strip fields excluded from hashing."""
    return {k: v for k, v in record_dict.items() if k not in _EXCLUDED_FROM_PAYLOAD}


def compute_chain_hash(prev_hash: str, record_dict: Dict[str, Any]) -> str:
    """Compute chain_hash for a record dict.

    Uses HMAC-SHA256 if HYDRA_NOTEBOOK_HMAC_KEY is set, else sha256.
    `record_dict` should already contain prev_hash (set by caller) but NOT
    chain_hash. We strip chain_hash defensively in case callers pass it in.
    """
    payload = hashable_payload(record_dict)
    canonical = canonical_json(payload)
    sep = b"\x1f"  # ASCII unit separator — prevent prefix collision games
    msg = prev_hash.encode("utf-8") + sep + canonical.encode("utf-8")

    key = _get_hmac_key()
    if key is not None:
        return hmac.new(key, msg, hashlib.sha256).hexdigest()
    h = hashlib.new(HASH_ALGO)
    h.update(msg)
    return h.hexdigest()


def verify_record(prev_hash: str, record_dict: Dict[str, Any]) -> bool:
    """Verify a single record's chain_hash against prev_hash."""
    expected = compute_chain_hash(prev_hash, record_dict)
    actual = record_dict.get("chain_hash", "")
    # Use constant-time compare for the secure-mode case
    return hmac.compare_digest(expected, actual)


def verify_chain(records: Iterable[Dict[str, Any]]) -> None:
    """Verify the entire chain. Raise ChainBrokenError on first divergence.

    The first record is expected to chain off GENESIS_PREV_HASH (all-zero
    sha256). Subsequent records chain off the previous record's chain_hash.
    """
    prev = GENESIS_PREV_HASH
    for i, rec in enumerate(records):
        expected = compute_chain_hash(prev, rec)
        actual = rec.get("chain_hash", "")
        if not hmac.compare_digest(expected, actual):
            _log.warning(
                "chain mismatch detected at position=%d record_id=%s",
                i, rec.get("record_id", "?"),
            )
            raise ChainBrokenError(
                record_id=rec.get("record_id", "?"),
                expected=expected,
                actual=actual,
                position=i,
            )
        # Also ensure prev_hash field matches what we expected
        declared_prev = rec.get("prev_hash", "")
        if declared_prev != prev:
            _log.warning(
                "prev_hash mismatch detected at position=%d record_id=%s",
                i, rec.get("record_id", "?"),
            )
            raise ChainBrokenError(
                record_id=rec.get("record_id", "?"),
                expected=prev,
                actual=declared_prev,
                position=i,
            )
        prev = actual


def first_prev_hash() -> str:
    """The genesis prev_hash — used for the very first record in a day."""
    return GENESIS_PREV_HASH
