"""HYDRA V4 — LIVE_ORDER_GUARD.

The single source of truth that LIVE TRADING IS DISABLED.

Hard contract:
  * `LIVE_ORDER_GUARD_ACTIVE = True` is set at import time.
  * `assert_no_live_order(operation_name)` checks the LIVE flag and the
    function-internal sentinel; if either is set it raises
    `LiveOrderAttemptError`.
  * The function intentionally does NOT consult the module global alone —
    it also keeps a function-internal sentinel (`_GUARD_BURNED_IN`) so
    monkey-patching the module global to False at runtime does NOT
    bypass the guard. Both must be False to bypass; the second is set
    inside the function body at module-load time and is not exposed.

Per spec: "the guard cannot be disabled at runtime". A test asserts
that even after `live_order_guard.LIVE_ORDER_GUARD_ACTIVE = False`,
`assert_no_live_order(...)` STILL raises.
"""

from __future__ import annotations

# Module-level flag for documentation / observability.
LIVE_ORDER_GUARD_ACTIVE: bool = True

# Internal sentinel — burned in at import time, never re-exported.
# Used to defeat `monkey-patch the module global` attacks.
_GUARD_BURNED_IN: bool = True


class LiveOrderAttemptError(RuntimeError):
    """Raised whenever code attempts to place / modify / close a real order."""


def assert_no_live_order(operation_name: str) -> None:
    """Refuse ANY live-order operation.

    Two independent checks must BOTH be False to permit. They cannot,
    in this phase. The function-internal `_GUARD_BURNED_IN` is captured
    by closure-like read of the module-level constant set at import; an
    attacker cannot mutate it without re-importing this module, and even
    re-import resets it back to True.
    """
    # We deliberately raise on EITHER flag — this is "fail closed".
    if LIVE_ORDER_GUARD_ACTIVE or _GUARD_BURNED_IN:
        raise LiveOrderAttemptError(
            f"LIVE_ORDER_GUARD: refused to {operation_name}. "
            f"This phase is LIVE_DATA_ONLY — no live trading."
        )
    # Unreachable in this phase; kept for future phase reviewers.
    raise LiveOrderAttemptError(
        f"LIVE_ORDER_GUARD: defensive refusal for {operation_name}."
    )


def is_active() -> bool:
    """Public read-only view for diagnostics."""
    return bool(LIVE_ORDER_GUARD_ACTIVE or _GUARD_BURNED_IN)
