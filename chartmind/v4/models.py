"""ChartMind V4 — data models.

ChartAssessment IS-A BrainOutput. The contract invariants in
`contracts.brain_output` run first; ChartMind-specific invariants run
afterwards in this module's __post_init__.

Reuses Bar from marketmind.v4.models — DO NOT redefine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from contracts.brain_output import BrainGrade, BrainOutput
from marketmind.v4.models import Bar  # noqa: F401  re-export


_VALID_TREND_STRUCTURE = {
    "bullish_strong",
    "bullish_weak",
    "bearish_strong",
    "bearish_weak",
    "range",
    "choppy",
    "transitioning",
    "none",
}

_VALID_VOLATILITY = {"compressed", "normal", "expanded", "dangerous", "unknown"}

_VALID_SETUP = {
    "breakout",
    "retest",
    "pullback_in_trend",
    "range_reversal",
    "no_setup",
}


@dataclass
class ChartAssessment(BrainOutput):
    """ChartMind's contract output. Extends BrainOutput.

    Local invariants (validated AFTER BrainOutput's own):
      C1: brain_name == "chartmind"
      C2: trend_structure in _VALID_TREND_STRUCTURE
      C3: volatility_state in _VALID_VOLATILITY
      C4: setup_type in _VALID_SETUP
      C5: atr_value >= 0.0 (finite)
      C6: entry_zone has finite low/high with low <= high
      C7: invalidation_level finite
      C8: stop_reference == invalidation_level
      C9: target_reference is None or finite
      C10: BUY/SELL decisions require entry_zone width > 0 (not a single price)
    """

    trend_structure: str = "none"
    volatility_state: str = "unknown"
    atr_value: float = 0.0
    key_levels: List[Dict[str, Any]] = field(default_factory=list)
    setup_type: str = "no_setup"
    entry_zone: Dict[str, float] = field(default_factory=dict)
    invalidation_level: float = 0.0
    stop_reference: float = 0.0
    target_reference: Optional[float] = None
    chart_warnings: List[str] = field(default_factory=list)
    indicator_snapshot: Dict[str, Any] = field(default_factory=dict)
    news_context_used: Optional[Dict[str, Any]] = None
    market_context_used: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # BrainOutput invariants first
        super().__post_init__()
        # C1
        if self.brain_name != "chartmind":
            raise ValueError(
                f"ChartAssessment.brain_name must be 'chartmind', got {self.brain_name!r}"
            )
        # C2..C4 vocab
        if self.trend_structure not in _VALID_TREND_STRUCTURE:
            raise ValueError(
                f"trend_structure {self.trend_structure!r} not in {_VALID_TREND_STRUCTURE}"
            )
        if self.volatility_state not in _VALID_VOLATILITY:
            raise ValueError(
                f"volatility_state {self.volatility_state!r} not in {_VALID_VOLATILITY}"
            )
        if self.setup_type not in _VALID_SETUP:
            raise ValueError(
                f"setup_type {self.setup_type!r} not in {_VALID_SETUP}"
            )
        # C5
        if not isinstance(self.atr_value, (int, float)) or not math.isfinite(self.atr_value):
            raise ValueError(f"atr_value must be a finite number, got {self.atr_value!r}")
        if self.atr_value < 0:
            raise ValueError(f"atr_value must be >= 0, got {self.atr_value}")
        # C6
        if not isinstance(self.entry_zone, dict):
            raise TypeError("entry_zone must be a dict")
        if self.entry_zone:
            lo = self.entry_zone.get("low")
            hi = self.entry_zone.get("high")
            for name, x in (("low", lo), ("high", hi)):
                if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
                    raise ValueError(f"entry_zone.{name} must be a finite number, got {x!r}")
            if lo > hi:
                raise ValueError(f"entry_zone.low > entry_zone.high ({lo} > {hi})")
        # C7
        if not isinstance(self.invalidation_level, (int, float)) or not math.isfinite(self.invalidation_level):
            raise ValueError(
                f"invalidation_level must be a finite number, got {self.invalidation_level!r}"
            )
        # C8
        if self.stop_reference != self.invalidation_level:
            raise ValueError(
                f"stop_reference ({self.stop_reference}) must == invalidation_level "
                f"({self.invalidation_level})"
            )
        # C9
        if self.target_reference is not None:
            if not isinstance(self.target_reference, (int, float)) or not math.isfinite(self.target_reference):
                raise ValueError(
                    f"target_reference must be None or finite, got {self.target_reference!r}"
                )
        # C10 — BUY/SELL must carry a real BAND, not a hardcoded scalar
        if self.decision in ("BUY", "SELL"):
            lo = self.entry_zone.get("low")
            hi = self.entry_zone.get("high")
            if lo is None or hi is None:
                raise ValueError("BUY/SELL requires entry_zone {low, high}")
            if hi <= lo:
                raise ValueError(
                    f"BUY/SELL requires entry_zone band (high>low), got low={lo} high={hi}"
                )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp_utc"), datetime):
            d["timestamp_utc"] = d["timestamp_utc"].isoformat()
        if isinstance(d.get("grade"), BrainGrade):
            d["grade"] = self.grade.value
        elif hasattr(self.grade, "value"):
            d["grade"] = self.grade.value
        return d


# ---------------------------------------------------------------------------
# Internal helper — Level value object
# ---------------------------------------------------------------------------


@dataclass
class Level:
    """A clustered key price level.

    type:    "support" | "resistance"
    strength: integer touch count (>=1)
    """

    price: float
    type: str
    strength: int
    touches: List[int] = field(default_factory=list)  # bar indices where touched

    def to_public(self) -> Dict[str, Any]:
        return {"price": float(self.price), "type": self.type, "strength": int(self.strength)}
