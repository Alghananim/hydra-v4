"""Deterministic fixtures for backtest_v2 tests + smoke runs."""
from .synthetic_bars import (
    make_trending_series, make_choppy_series, make_breakout_series,
    SyntheticBar,
)
from .synthetic_news import make_quiet_news_replay, FixedNewsReplay

__all__ = [
    "make_trending_series", "make_choppy_series", "make_breakout_series",
    "SyntheticBar",
    "make_quiet_news_replay", "FixedNewsReplay",
]
