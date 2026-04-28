"""SmartNoteBook V4 — honest per-mind attribution.

The R7 rule, in plain English:
  A win counts as "earned" for a mind ONLY if:
    - that mind's grade was >= ATTRIBUTION_GRADE_FLOOR (default A)
    - AND the trade's direction matched the mind's recommendation
  Otherwise the win is "lucky" and credit goes to RESPONSIBLE_LUCK,
  NOT the mind. Wins on grade-C / grade-B brain calls are NOT credited
  to the brain.

This is a deliberate departure from V3 which gave any directional
match credit to the strongest brain regardless of grade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from smartnotebook.v4.notebook_constants import (
    ATTRIBUTION_GRADE_FLOOR,
    QUALITY_EARNED,
    QUALITY_LUCKY,
    QUALITY_UNFORCED,
    QUALITY_UNKNOWN,
    RESPONSIBLE_CHART,
    RESPONSIBLE_GATE,
    RESPONSIBLE_LUCK,
    RESPONSIBLE_MARKET,
    RESPONSIBLE_NEWS,
)


# Order matters here: grade rank used for "grade >= A" comparisons.
_GRADE_RANK = {"A+": 5, "A": 4, "B": 3, "C": 2, "BLOCK": 1}
_FLOOR_RANK = _GRADE_RANK[ATTRIBUTION_GRADE_FLOOR]


@dataclass(frozen=True)
class Attribution:
    """Result of a single trade's attribution analysis."""

    quality: str              # earned | lucky | unforced_loss | unknown
    responsible: str          # luck | newsmind | marketmind | chartmind | gatemind
    earned_minds: tuple = ()  # which minds earned credit (could be multiple)


def _grade_meets_floor(grade: Optional[str]) -> bool:
    if grade is None:
        return False
    return _GRADE_RANK.get(grade, 0) >= _FLOOR_RANK


def attribute_outcome(
    *,
    direction: str,
    pnl: float,
    direction_matched: bool,
    mind_grades: Dict[str, str],
    mind_decisions: Dict[str, str],
) -> Attribution:
    """Honest per-mind attribution for a closed trade.

    Args:
      direction: "BUY" or "SELL" — what the trade actually was
      pnl: realized profit/loss (positive = win)
      direction_matched: did the trade go in the predicted direction
      mind_grades: e.g. {"newsmind": "A+", "marketmind": "C", ...}
      mind_decisions: e.g. {"newsmind": "BUY", "marketmind": "WAIT", ...}

    Returns an Attribution with `quality` and `responsible`.
    """
    # LOSSes bucket by why.
    if pnl < 0:
        # An unforced loss is a loss when at least one A/A+ mind agreed
        # with the direction (so it wasn't a yolo trade). For now: if any
        # A/A+ mind agreed with direction, it's "unforced" — that mind
        # over-promised and got punished.
        unforced_responsible = _find_responsible(
            direction=direction,
            mind_grades=mind_grades,
            mind_decisions=mind_decisions,
        )
        if unforced_responsible:
            return Attribution(
                quality=QUALITY_UNFORCED,
                responsible=unforced_responsible[0],
                earned_minds=tuple(unforced_responsible),
            )
        return Attribution(
            quality=QUALITY_UNFORCED,
            responsible=RESPONSIBLE_LUCK,
        )

    if pnl == 0:
        return Attribution(
            quality=QUALITY_UNKNOWN,
            responsible=RESPONSIBLE_LUCK,
        )

    # WINs require direction match for "earned"; otherwise "lucky".
    if not direction_matched:
        return Attribution(
            quality=QUALITY_LUCKY,
            responsible=RESPONSIBLE_LUCK,
        )

    earned = _find_responsible(
        direction=direction,
        mind_grades=mind_grades,
        mind_decisions=mind_decisions,
    )
    if earned:
        return Attribution(
            quality=QUALITY_EARNED,
            responsible=earned[0],
            earned_minds=tuple(earned),
        )

    # Direction matched, profit, but NO mind was both A+/A AND agreed →
    # this win is lucky, not earned. R7.
    return Attribution(
        quality=QUALITY_LUCKY,
        responsible=RESPONSIBLE_LUCK,
    )


_MIND_TO_RESPONSIBLE = {
    "newsmind": RESPONSIBLE_NEWS,
    "marketmind": RESPONSIBLE_MARKET,
    "chartmind": RESPONSIBLE_CHART,
    "gatemind": RESPONSIBLE_GATE,
}


def _find_responsible(
    *,
    direction: str,
    mind_grades: Dict[str, str],
    mind_decisions: Dict[str, str],
) -> list:
    """Return list of "responsible" mind labels — those at A/A+ AND agreed."""
    out = []
    # Iterate in deterministic order for reproducible attribution
    for mind in ("newsmind", "marketmind", "chartmind", "gatemind"):
        grade = mind_grades.get(mind)
        decision = mind_decisions.get(mind)
        if not _grade_meets_floor(grade):
            continue
        if decision != direction:
            continue
        out.append(_MIND_TO_RESPONSIBLE[mind])
    return out
