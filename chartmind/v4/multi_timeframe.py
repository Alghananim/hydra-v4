"""Multi-timeframe alignment — M15 → M5 → M1 cascading.

KEEP from V3 — the cascading-conflict idea is sound.

mtf_aligned (boolean): if M5/M1 trend labels do NOT contradict M15 label.
A "conflict" means: M15 is bullish_* but M5 (or M1) is bearish_strong, or
vice versa. weak/range/transitioning are non-conflicting.

If only M15 bars are provided we report mtf_aligned=True with reason="single_tf".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.market_structure import diagnose_trend


@dataclass
class MTFResult:
    aligned: bool
    m15_trend: str
    m5_trend: Optional[str]
    m1_trend: Optional[str]
    reason: str


def _conflicts(parent: str, child: str) -> bool:
    if parent in ("bullish_strong", "bullish_weak") and child == "bearish_strong":
        return True
    if parent in ("bearish_strong", "bearish_weak") and child == "bullish_strong":
        return True
    return False


def assess(bars_by_tf: Mapping[str, Sequence[Bar]]) -> MTFResult:
    """`bars_by_tf` keys: "M15" (required), optionally "M5", "M1"."""
    m15 = bars_by_tf.get("M15") or bars_by_tf.get("15") or []
    m5 = bars_by_tf.get("M5") or bars_by_tf.get("5")
    m1 = bars_by_tf.get("M1") or bars_by_tf.get("1")

    if not m15:
        return MTFResult(False, "none", None, None, "no_m15")

    m15_label = diagnose_trend(m15).label
    m5_label = diagnose_trend(m5).label if m5 else None
    m1_label = diagnose_trend(m1).label if m1 else None

    if m5_label is None and m1_label is None:
        return MTFResult(True, m15_label, None, None, "single_tf")

    conflicts = []
    if m5_label and _conflicts(m15_label, m5_label):
        conflicts.append(f"M5={m5_label}")
    if m1_label and _conflicts(m15_label, m1_label):
        conflicts.append(f"M1={m1_label}")
    if conflicts:
        return MTFResult(False, m15_label, m5_label, m1_label,
                         f"conflict:{','.join(conflicts)}")
    return MTFResult(True, m15_label, m5_label, m1_label, "aligned")
