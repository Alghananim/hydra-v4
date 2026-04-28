"""SmartNoteBook V4 — outcome classifier.

KEPT from V3 with cleaner enum surface.

Classifies a TradeOutcome into discrete labels used by reports / attribution.
"""

from __future__ import annotations

from enum import Enum


class OutcomeClass(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"


def classify_pnl(pnl: float, breakeven_band: float = 0.0) -> OutcomeClass:
    """Convert raw PnL to an OutcomeClass.

    `breakeven_band` is an inclusive symmetric band around zero treated as
    BREAKEVEN. Use 0.0 to treat exactly-zero as BREAKEVEN, anything else as
    WIN/LOSS.
    """
    if pnl > breakeven_band:
        return OutcomeClass.WIN
    if pnl < -breakeven_band:
        return OutcomeClass.LOSS
    return OutcomeClass.BREAKEVEN


def direction_match(direction: str, pnl: float) -> bool:
    """Did the trade move in the predicted direction?

    For a BUY, positive pnl = match. For a SELL, also positive pnl = match
    (since pnl is realized profit not price delta).

    A True direction_match + positive pnl is the basis for the attribution
    "earned" vs "lucky" decision.
    """
    if direction not in ("BUY", "SELL"):
        return False
    return pnl > 0
