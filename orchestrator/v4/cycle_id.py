"""HYDRA V4 — cycle_id minting.

A cycle_id is a deterministic-looking, globally-unique identifier for
one orchestrator decision cycle. Format:

    hyd-<UTC-timestamp>-<short-uuid>

Properties:
  * Sortable by time (the timestamp prefix is lexicographically sortable
    when written in YYYYMMDDTHHMMSS%fZ form).
  * Unique under concurrent calls (UUID4 suffix).
  * Human-readable — operators can grep logs by date prefix.

The minting helper is a pure function so it's trivial to unit-test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from orchestrator.v4.orchestrator_constants import CYCLE_ID_PREFIX, CYCLE_TS_FORMAT


def mint_cycle_id(now_utc: datetime | None = None) -> str:
    """Return a fresh cycle_id.

    Args:
      now_utc: optional tz-aware UTC anchor. If naive or None, uses
        datetime.now(timezone.utc).
    """
    if now_utc is None or now_utc.tzinfo is None:
        now_utc = datetime.now(timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    ts = now_utc.strftime(CYCLE_TS_FORMAT)
    suffix = uuid.uuid4().hex[:12]
    return f"{CYCLE_ID_PREFIX}-{ts}-{suffix}"
