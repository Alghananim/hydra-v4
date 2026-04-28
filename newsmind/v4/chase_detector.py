"""NewsMind V4 — chase detector.

KEEP from V3 (per audit) — pure function, drop-in.

Detects whether the news situation is a 'chase' — i.e. an unverified social /
single-source rumor that we should NOT enter on. Returns True if any of:

  - source_type == "social" without an authoritative or tier1 confirmation
  - source_type == "tier1" but confirmation_count < 2 AND impact_level >= high
  - the headline contains a known chase trigger keyword AND the source is unverified

When True, the caller MUST cap grade at C.
"""

from __future__ import annotations

from typing import Iterable, Sequence


_CHASE_TRIGGERS = (
    "rumor",
    "rumour",
    "sources say",
    "unconfirmed",
    "leaked",
    "report claims",
)


def is_chase(
    *,
    source_type: str,
    confirmation_count: int,
    impact_level: str,
    headline: str = "",
    unverified_source_names: Sequence[str] = (),
    source_name: str = "",
) -> bool:
    s = source_type.lower()
    h = (headline or "").lower()
    sn = (source_name or "").lower()

    if s == "social" and confirmation_count < 1:
        return True
    if s == "tier1" and confirmation_count < 2 and impact_level in ("high", "extreme"):
        return True
    if any(trig in h for trig in _CHASE_TRIGGERS) and any(
        u.lower() in sn for u in unverified_source_names
    ):
        return True
    return False
