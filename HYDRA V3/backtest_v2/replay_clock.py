# -*- coding: utf-8 -*-
"""replay_clock — drive the engine bar by bar."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ReplayClock:
    total_bars: int
    cursor: int = -1
    started_at: Optional[datetime] = None

    def advance(self) -> bool:
        if self.cursor + 1 >= self.total_bars:
            return False
        self.cursor += 1
        return True

    def has_next(self) -> bool:
        return (self.cursor + 1) < self.total_bars

    def remaining(self) -> int:
        return max(0, self.total_bars - self.cursor - 1)

    def progress_pct(self) -> float:
        if self.total_bars <= 0:
            return 0.0
        return (self.cursor + 1) / self.total_bars * 100.0
