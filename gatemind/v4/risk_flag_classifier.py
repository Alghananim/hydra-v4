"""GateMind V4 — risk flag classifier.

Two classes (LOCKED v1.0):
  - kill-class    → fail-CLOSED, BLOCK
  - warning-class → allowed but logged on the audit trail; recorded into
                    TradeCandidate.risk_flags

Anything not on either whitelist is treated as kill-class (fail-closed).
That decision is intentional: an unknown flag from upstream means we don't
understand the risk, so we don't trade.
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from gatemind.v4.gatemind_constants import (
    KILL_CLASS_FLAGS,
    WARNING_CLASS_FLAGS,
)


def classify_flag(flag: str) -> str:
    """Return 'kill', 'warning', or 'unknown' (treated as kill upstream)."""
    if flag in KILL_CLASS_FLAGS:
        return "kill"
    if flag in WARNING_CLASS_FLAGS:
        return "warning"
    return "unknown"


def aggregate_flags(news, market, chart) -> Tuple[List[str], List[str], List[str]]:
    """Return (kill_flags, warning_flags, unknown_flags) across all three brains.

    Each entry is "{brain}:{flag}" so the audit trail can attribute origin.
    """
    kill: List[str] = []
    warn: List[str] = []
    unknown: List[str] = []
    for brain_label, brain in (
        ("NewsMind", news),
        ("MarketMind", market),
        ("ChartMind", chart),
    ):
        for flag in (brain.risk_flags or []):
            cls = classify_flag(flag)
            tag = f"{brain_label}:{flag}"
            if cls == "kill":
                kill.append(tag)
            elif cls == "warning":
                warn.append(tag)
            else:
                unknown.append(tag)
    return kill, warn, unknown


def risk_flag_status(kill: Iterable[str], warn: Iterable[str], unknown: Iterable[str]) -> str:
    """Summarise flag state for GateDecision.risk_flag_status."""
    kill_l, warn_l, unknown_l = list(kill), list(warn), list(unknown)
    # Unknown flags are treated as kill — fail-closed default.
    if kill_l or unknown_l:
        return "kill_active"
    if warn_l:
        return "warnings_only"
    return "clean"


def has_kill(news, market, chart) -> Tuple[bool, List[str]]:
    """True iff any kill-class (or unknown) flag is present.

    Returns (has_kill, ordered_list_of_offending_flag_tags).
    """
    kill, _, unknown = aggregate_flags(news, market, chart)
    offenders = list(kill) + list(unknown)
    return bool(offenders), offenders
