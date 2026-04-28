"""MarketMind V4 — data models.

MarketState IS-A BrainOutput (the V4 contract). No fields override the
contract's invariants. Anything MarketMind-specific lives alongside in
extra fields and is validated locally.

Bar is a minimal OHLCV row. Hour-of-day is derived from `timestamp` (UTC).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from contracts.brain_output import BrainOutput, BrainGrade


# ---------------------------------------------------------------------------
# Bar
# ---------------------------------------------------------------------------


@dataclass
class Bar:
    """OHLCV bar. timestamp MUST be tz-aware UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread_pips: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("Bar.timestamp must be tz-aware UTC")
        # Reject NaN / Inf in OHLC — these silently poison ATR/EMA chains
        # and end up graded as WAIT/C in permission_engine instead of BLOCK.
        for name, x in (("open", self.open), ("high", self.high),
                        ("low", self.low), ("close", self.close)):
            if not isinstance(x, (int, float)) or not math.isfinite(float(x)):
                raise ValueError(f"Bar.{name} must be a finite number, got {x!r}")
        if self.high < self.low:
            raise ValueError(f"Bar high<low: {self.high}<{self.low}")
        if self.close <= 0 or self.open <= 0:
            raise ValueError("Bar prices must be positive")
        # volume must be non-negative finite
        if (self.volume is None
                or not isinstance(self.volume, (int, float))
                or not math.isfinite(float(self.volume))
                or self.volume < 0):
            raise ValueError(f"Bar.volume must be a finite non-negative number, got {self.volume!r}")
        # spread_pips: if provided, must be finite and non-negative
        if self.spread_pips is not None:
            if (not isinstance(self.spread_pips, (int, float))
                    or not math.isfinite(float(self.spread_pips))
                    or self.spread_pips < 0):
                raise ValueError(
                    f"Bar.spread_pips must be a finite non-negative number or None, "
                    f"got {self.spread_pips!r}"
                )


# ---------------------------------------------------------------------------
# Valid state vocab — local invariants, NOT in BrainOutput
# ---------------------------------------------------------------------------

_VALID_REGIME = {"trending", "ranging", "choppy", "transitioning"}
_VALID_TREND = {
    "strong_up", "weak_up", "strong_down", "weak_down",
    "range", "choppy", "none",
}
_VALID_MOMENTUM = {"accelerating", "fading", "divergent", "steady", "none"}
_VALID_VOLATILITY = {"compressed", "normal", "expanded", "dangerous", "unknown"}
_VALID_LIQUIDITY = {"good", "fair", "poor", "off-session", "unknown"}


@dataclass
class MarketState(BrainOutput):
    """MarketMind's contract output. Extends BrainOutput.

    Local invariants (validated in __post_init__ AFTER BrainOutput's own):
      M1: regime_state in _VALID_REGIME
      M2: trend_state in _VALID_TREND
      M3: momentum_state in _VALID_MOMENTUM
      M4: volatility_state in _VALID_VOLATILITY
      M5: liquidity_state in _VALID_LIQUIDITY
      M6: brain_name == "marketmind"
    """

    regime_state: str = "transitioning"
    trend_state: str = "none"
    momentum_state: str = "none"
    volatility_state: str = "unknown"
    liquidity_state: str = "unknown"
    currency_strength: Dict[str, Any] = field(default_factory=dict)
    news_context_used: Dict[str, Any] = field(default_factory=dict)
    contradictions: List[str] = field(default_factory=list)
    indicator_snapshot: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Run BrainOutput invariants first
        super().__post_init__()
        # M6 — must be marketmind
        if self.brain_name != "marketmind":
            raise ValueError(
                f"MarketState.brain_name must be 'marketmind', got {self.brain_name!r}"
            )
        # M1..M5
        if self.regime_state not in _VALID_REGIME:
            raise ValueError(f"regime_state {self.regime_state!r} not in {_VALID_REGIME}")
        if self.trend_state not in _VALID_TREND:
            raise ValueError(f"trend_state {self.trend_state!r} not in {_VALID_TREND}")
        if self.momentum_state not in _VALID_MOMENTUM:
            raise ValueError(f"momentum_state {self.momentum_state!r} not in {_VALID_MOMENTUM}")
        if self.volatility_state not in _VALID_VOLATILITY:
            raise ValueError(f"volatility_state {self.volatility_state!r} not in {_VALID_VOLATILITY}")
        if self.liquidity_state not in _VALID_LIQUIDITY:
            raise ValueError(f"liquidity_state {self.liquidity_state!r} not in {_VALID_LIQUIDITY}")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("timestamp_utc"), datetime):
            d["timestamp_utc"] = d["timestamp_utc"].isoformat()
        if isinstance(d.get("grade"), BrainGrade):
            d["grade"] = self.grade.value
        elif hasattr(self.grade, "value"):
            d["grade"] = self.grade.value
        return d
