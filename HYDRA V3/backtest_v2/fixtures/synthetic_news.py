# -*- coding: utf-8 -*-
"""Deterministic NewsVerdict replays for tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Iterable

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class FixedNewsReplay:
    def __init__(self, *, permission: str = "allow", grade: str = "B",
                 bias: str = "neutral", impact: str = "low",
                 reason: str = "test_fixture"):
        self._perm = permission
        self._grade = grade
        self._bias = bias
        self._impact = impact
        self._reason = reason

    def at(self, now_utc: datetime):
        from newsmind.v3.models import NewsVerdict   # type: ignore
        return NewsVerdict(
            headline=f"fixture:{self._reason}",
            source_name="FixedNewsReplay",
            source_type="calendar",
            normalized_utc_time=now_utc,
            freshness_status="fresh",
            verified=True,
            impact_level=self._impact,
            market_bias=self._bias,
            risk_mode="unclear",
            grade=self._grade, confidence=0.7,
            trade_permission=self._perm,
            reason=self._reason,
        )


def make_quiet_news_replay() -> FixedNewsReplay:
    return FixedNewsReplay(permission="allow", grade="B", bias="neutral",
                            impact="low", reason="quiet_market")
