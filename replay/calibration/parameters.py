"""HYDRA V4.8 — calibration parameter registry.

Every knob the system has, with:
  - description : what it does
  - current     : current production value (V4.7 frozen)
  - safe_range  : range the Red Team agrees can be swept without
                  invalidating the architecture
  - extreme_range : range that would be outside V4.7's contract
                  and requires a separate architectural review
  - hypothesis_link : which War Room hypothesis (H1-H15) this knob tests

This file does not change behaviour by itself — it is read by the sweep
harness in `sweep.py`. The frozen production gate stays unaware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


@dataclass
class CalibrationKnob:
    name: str
    description: str
    current: Any
    safe_range: Tuple[Any, ...]
    extreme_range: Optional[Tuple[Any, ...]] = None
    hypothesis_link: Optional[str] = None
    notes: str = ""


def registry() -> List[CalibrationKnob]:
    return [
        CalibrationKnob(
            name="grade_gate_minimum",
            description=(
                "Minimum grade GateMind accepts on each brain. "
                "V4.7 production: A. The strict rule that produced 9 "
                "ENTER over 21k partial cycles."
            ),
            current="A",
            safe_range=("A", "B"),
            extreme_range=("A+", "A", "B", "C"),
            hypothesis_link="H2/H13",
            notes=(
                "Sweeping to B is the highest-leverage knob we have. "
                "Red Team P5 (per-pair) and P7 (drawdown floor) must pass "
                "for the variant to be promoted."
            ),
        ),
        CalibrationKnob(
            name="chart_directional_threshold",
            description=(
                "ChartMind setup detector confidence threshold for "
                "emitting BUY/SELL. Higher = more selective."
            ),
            current=0.65,
            safe_range=(0.50, 0.55, 0.60, 0.65, 0.70),
            extreme_range=(0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80),
            hypothesis_link="H1/H4",
            notes=(
                "Lower threshold = more directional decisions = more "
                "ENTER candidates, but also potentially worse win rate. "
                "Shadow P&L must show win-rate stable across the range."
            ),
        ),
        CalibrationKnob(
            name="ny_window_pre_open_hours",
            description=(
                "Pre-open NY trading window length in hours. "
                "V4.7 production: 03-05 UTC = 2h."
            ),
            current=(3, 5),
            safe_range=((3, 5), (2, 6), (1, 6)),
            extreme_range=((3, 5), (2, 6), (1, 7), (0, 8)),
            hypothesis_link="H5",
            notes="Wider window = more in-window cycles = more chances.",
        ),
        CalibrationKnob(
            name="ny_window_morning_hours",
            description=(
                "Morning NY trading window length in hours. "
                "V4.7 production: 08-12 UTC = 4h."
            ),
            current=(8, 12),
            safe_range=((8, 12), (8, 14), (7, 14)),
            extreme_range=((8, 12), (8, 14), (7, 15), (6, 16)),
            hypothesis_link="H5",
        ),
        CalibrationKnob(
            name="news_block_radius_minutes",
            description=(
                "How many minutes before/after a calendar event NewsMind "
                "BLOCKs the cycle. V4.7 production: ±5 min."
            ),
            current=5,
            safe_range=(3, 5, 10),
            extreme_range=(0, 3, 5, 10, 15, 30),
            hypothesis_link="H14",
        ),
        CalibrationKnob(
            name="market_data_quality_stale_factor",
            description=(
                "Multiplier on bar interval beyond which MarketMind "
                "flags data as stale. V4.7 production: 1.5x."
            ),
            current=1.5,
            safe_range=(1.5, 2.0, 3.0),
            extreme_range=(1.0, 1.5, 2.0, 3.0, 5.0),
            hypothesis_link="H7",
            notes="Phase 9 already increased this; further loosening "
                  "may mask real data issues.",
        ),
        CalibrationKnob(
            name="lookback_bars",
            description=(
                "Bars of history fed to MarketMind / ChartMind per cycle."
            ),
            current=500,
            safe_range=(300, 500, 700, 1000),
            extreme_range=(100, 200, 300, 500, 700, 1000, 1500),
            hypothesis_link="H8",
            notes="Higher = more indicator stability, longer warm-up.",
        ),
    ]


def by_name(name: str) -> Optional[CalibrationKnob]:
    for k in registry():
        if k.name == name:
            return k
    return None
