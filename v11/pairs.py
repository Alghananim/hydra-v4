"""HYDRA V11 — per-pair calibration table.

Each instrument has different volatility, spread, and noise/signal
profile. Applying the same SL/TP and grade thresholds to all pairs
(as V5 did) is what produced USD/JPY = 0/8 wins.

This table is the single source of truth for per-pair parameters.
Read by ChartMindV11 and the V11 shadow simulator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PairConfig:
    symbol: str
    pip_size: float            # 0.0001 for most, 0.01 for JPY pairs
    typical_atr_pips: float    # average M5 ATR in pips
    max_spread_pips: float     # spread cap above which trades are rejected
    sl_pips: float             # default SL in pips
    tp_pips: float             # default TP in pips
    risk_reward: float         # tp / sl
    grade_a_min_evidence: int  # how many of 8 evidence flags for grade A
    notes: str = ""

    @property
    def expected_win_rate_breakeven(self) -> float:
        """Win rate needed to break even at this R:R, after cost."""
        # 0 = win_rate * tp - (1-win_rate) * sl - cost
        # Approximation: win_rate >= sl / (sl + tp)
        return self.sl_pips / (self.sl_pips + self.tp_pips)


# V11 instrument set. Six pairs covering EUR/USD/JPY/GBP/CAD/AUD majors.
# Per-pair values are conservative initial guesses based on M5 historical
# volatility on OANDA-quoted majors. They will be tuned in V11 War Room.
PAIRS: Dict[str, PairConfig] = {
    "EUR_USD": PairConfig(
        symbol="EUR_USD",
        pip_size=0.0001,
        typical_atr_pips=4.5,        # M5 ATR much smaller than M15
        max_spread_pips=1.5,
        sl_pips=8.0,
        tp_pips=16.0,
        risk_reward=2.0,
        grade_a_min_evidence=5,
        notes="Most liquid. Tightest spread. Lowest noise.",
    ),
    "USD_JPY": PairConfig(
        symbol="USD_JPY",
        pip_size=0.01,
        typical_atr_pips=5.5,
        max_spread_pips=1.5,
        sl_pips=10.0,
        tp_pips=18.0,
        risk_reward=1.8,
        grade_a_min_evidence=6,      # stricter — V5 showed 0/8 wins
        notes="JPY pairs noisier on entry; require stricter evidence.",
    ),
    "GBP_USD": PairConfig(
        symbol="GBP_USD",
        pip_size=0.0001,
        typical_atr_pips=6.0,
        max_spread_pips=1.8,
        sl_pips=12.0,
        tp_pips=24.0,
        risk_reward=2.0,
        grade_a_min_evidence=5,
        notes="Larger range than EUR/USD. Wider SL/TP.",
    ),
    "USD_CAD": PairConfig(
        symbol="USD_CAD",
        pip_size=0.0001,
        typical_atr_pips=5.0,
        max_spread_pips=1.8,
        sl_pips=10.0,
        tp_pips=18.0,
        risk_reward=1.8,
        grade_a_min_evidence=5,
        notes="Oil-correlated. Can be choppy on energy news.",
    ),
    "AUD_USD": PairConfig(
        symbol="AUD_USD",
        pip_size=0.0001,
        typical_atr_pips=4.0,
        max_spread_pips=1.8,
        sl_pips=8.0,
        tp_pips=14.0,
        risk_reward=1.75,
        grade_a_min_evidence=5,
        notes="Risk-on/risk-off proxy. Asian session active.",
    ),
    "EUR_JPY": PairConfig(
        symbol="EUR_JPY",
        pip_size=0.01,
        typical_atr_pips=7.0,
        max_spread_pips=2.0,
        sl_pips=14.0,
        tp_pips=24.0,
        risk_reward=1.71,
        grade_a_min_evidence=6,
        notes="Cross. Higher volatility on EU-JP rate divergence.",
    ),
}


def for_pair(symbol: str) -> PairConfig:
    """Return PairConfig; raises KeyError if unknown."""
    return PAIRS[symbol]


def all_pairs() -> tuple:
    return tuple(PAIRS.keys())
