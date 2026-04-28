"""NewsMind V4 — permission decision matrix.

KEEP from V3 (per audit). Adapted imports.

Decision matrix (precedence top → bottom; first match wins):

  1. data_quality == "broken"             → BLOCK   (fail-CLOSED)
  2. data_quality == "missing"            → BLOCK   (silent feed = BLOCK, never 'all good')
  3. is_scheduled_event AND in_blackout   → BLOCK
  4. data_quality == "stale"              → WAIT
  5. impact_level == "extreme"            → WAIT    (await confirmation)
  6. confirmation_count == 0 AND has news → WAIT    (single-source, can't grade A)
  7. otherwise                            → ENTER

Returns a tuple (permission, reason).

The matrix is intentionally exception-safe: any unhandled state collapses to
BLOCK (the `_else` branch at the bottom).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class PermissionInputs:
    data_quality: str          # "good" | "stale" | "missing" | "broken"
    is_scheduled_event: bool
    in_blackout: bool
    impact_level: str          # "low" | "medium" | "high" | "extreme"
    confirmation_count: int
    has_any_news: bool


def decide(inputs: PermissionInputs) -> Tuple[str, str]:
    """Returns (permission, reason). permission ∈ {ENTER, WAIT, BLOCK}."""
    try:
        if inputs.data_quality == "broken":
            return "BLOCK", "data_quality=broken — fail-CLOSED"
        if inputs.data_quality == "missing":
            return "BLOCK", "all sources silent — fail-CLOSED (silence != all-clear)"
        if inputs.is_scheduled_event and inputs.in_blackout:
            return "BLOCK", "scheduled event blackout window active"
        if inputs.data_quality == "stale":
            return "WAIT", "data_quality=stale — defer"
        if inputs.impact_level == "extreme":
            return "WAIT", "impact_level=extreme — await confirmation"
        if inputs.has_any_news and inputs.confirmation_count == 0:
            return "WAIT", "single-source signal — need >=2 confirmations for ENTER"
        return "ENTER", "permission decision matrix: clear"
    except Exception as e:  # noqa: BLE001 — we re-raise as ValueError below
        # If the inputs themselves are broken, fail-CLOSED.
        raise ValueError(f"permission.decide: malformed inputs: {e!r}") from e
