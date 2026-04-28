"""GateMind V4 — audit logging.

One audit_id per `evaluate()` call. The snapshot captures everything needed
to reproduce the decision deterministically: inputs, rule trace, outcome.

This is a SESSION-SCOPED audit cache. Persistent audit is SmartNoteBook V4's
job. The cache is bounded by MAX_AUDIT_ENTRIES with LRU eviction so a long-
running process cannot grow unbounded.

What we own:
  - audit_id generation (deterministic from time + symbol + inputs hash)
  - snapshot capture (deep-copied on read so callers cannot mutate the cache)
  - reproducibility within the cache window — same audit_id can re-fetch the
    same snapshot in-process until it is evicted
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from gatemind.v4.gatemind_constants import MAX_AUDIT_ENTRIES
from gatemind.v4.models import GateDecision

_log = logging.getLogger("gatemind")

# In-process snapshot store. Bounded LRU — see MAX_AUDIT_ENTRIES.
# Tests inspect it directly via clear_audit_store() / fetch_audit().
_AUDIT_STORE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def make_audit_id(now_utc: datetime, symbol: str, news, market, chart) -> str:
    """Deterministic audit_id from time + symbol + content fingerprint.

    Format: gm-{YYYYMMDDTHHMMSSfff}Z-{symbol}-{hash8}
    """
    fingerprint_src = "|".join([
        f"news={news.brain_name}:{news.decision}:{news.grade.value}:{news.confidence:.4f}",
        f"market={market.brain_name}:{market.decision}:{market.grade.value}:{market.confidence:.4f}",
        f"chart={chart.brain_name}:{chart.decision}:{chart.grade.value}:{chart.confidence:.4f}",
    ])
    h = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()[:8]
    ts = now_utc.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]
    return f"gm-{ts}Z-{symbol}-{h}"


def _serialise_brain(b) -> Dict[str, Any]:
    return {
        "brain_name": b.brain_name,
        "decision": b.decision,
        "grade": b.grade.value,
        "reason": b.reason,
        "evidence": list(b.evidence or []),
        "data_quality": b.data_quality,
        "should_block": bool(b.should_block),
        "risk_flags": list(b.risk_flags or []),
        "confidence": float(b.confidence),
        "timestamp_utc": b.timestamp_utc.isoformat(),
    }


def _evict_if_over_cap() -> None:
    """LRU eviction — drop oldest entries until size is under MAX_AUDIT_ENTRIES."""
    while len(_AUDIT_STORE) > MAX_AUDIT_ENTRIES:
        _AUDIT_STORE.popitem(last=False)


def record_audit(
    audit_id: str,
    *,
    now_utc: datetime,
    symbol: str,
    news,
    market,
    chart,
    decision: GateDecision,
) -> Dict[str, Any]:
    """Capture a full snapshot. Returns the snapshot for inline inspection.

    Snapshot is appended to the LRU cache; if the cache exceeds
    MAX_AUDIT_ENTRIES, the oldest entries are evicted.
    """
    snapshot = {
        "audit_id": audit_id,
        "timestamp_utc": now_utc.astimezone(timezone.utc).isoformat(),
        "symbol": symbol,
        "inputs": {
            "news": _serialise_brain(news),
            "market": _serialise_brain(market),
            "chart": _serialise_brain(chart),
        },
        "decision": {
            "gate_decision": decision.gate_decision.value,
            "direction": decision.direction.value,
            "blocking_reason": decision.blocking_reason,
            "approval_reason": decision.approval_reason,
            "consensus_status": decision.consensus_status,
            "grade_status": decision.grade_status,
            "session_status": decision.session_status,
            "risk_flag_status": decision.risk_flag_status,
            "mind_votes": dict(decision.mind_votes),
            "mind_grades": dict(decision.mind_grades),
            "mind_data_quality": dict(decision.mind_data_quality),
            "audit_trail": list(decision.audit_trail),
            "model_version": decision.model_version,
        },
    }
    try:
        # If audit_id already present, refresh its position (LRU touch).
        if audit_id in _AUDIT_STORE:
            _AUDIT_STORE.move_to_end(audit_id, last=True)
        _AUDIT_STORE[audit_id] = snapshot
        _evict_if_over_cap()
    except Exception as exc:  # truly unexpected — log but never poison the decision
        _log.warning(
            "audit_store_insert_failed audit_id=%s error=%s",
            audit_id,
            exc,
        )
    return snapshot


def fetch_audit(audit_id: str) -> Optional[Dict[str, Any]]:
    """Return a DEEP COPY of the snapshot.

    Returning a deep copy prevents callers from mutating the cache and
    corrupting the audit log.
    """
    snap = _AUDIT_STORE.get(audit_id)
    if snap is None:
        return None
    try:
        return copy.deepcopy(snap)
    except Exception as exc:  # extremely unlikely — fail closed by returning None
        _log.warning(
            "audit_store_deepcopy_failed audit_id=%s error=%s",
            audit_id,
            exc,
        )
        return None


def clear_audit_store() -> None:
    """Test helper — wipe the in-process store."""
    _AUDIT_STORE.clear()


def audit_store_size() -> int:
    """Test/diagnostic helper — current cache size."""
    return len(_AUDIT_STORE)


def to_json(snapshot: Dict[str, Any]) -> str:
    return json.dumps(snapshot, sort_keys=True, default=str)
