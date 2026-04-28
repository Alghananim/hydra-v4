# -*- coding: utf-8 -*-
"""calendar_provider — adapter over Backtest.calendar.HistoricalCalendar."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class CalendarReplay:
    def __init__(self, *, start: Optional[datetime] = None,
                 end: Optional[datetime] = None,
                 pair: str = "EUR/USD"):
        from Backtest.calendar import HistoricalCalendar    # type: ignore
        self._cal = HistoricalCalendar(
            start=start.date() if start else None,
            end=end.date() if end else None)
        self._pair = pair

    def at(self, now_utc: datetime):
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        from newsmind.v3.models import NewsVerdict     # type: ignore

        is_blackout, event = self._cal.is_blackout(now_utc, tiers=("T1", "T2"))
        if is_blackout and event is not None:
            return NewsVerdict(
                headline=f"calendar:{event.name}",
                source_name="HistoricalCalendar",
                source_type="calendar",
                normalized_utc_time=event.when_utc,
                freshness_status="fresh",
                verified=True,
                impact_level="high" if event.tier == "T1" else "medium",
                affected_assets=("USD", "EUR"),
                market_bias="unclear",
                risk_mode="risk_off",
                grade="C", confidence=0.9,
                trade_permission="block",
                reason=f"calendar_blackout:{event.name}@{event.when_utc.isoformat()}",
                pre_event_window=now_utc < event.when_utc,
                post_event_window=now_utc >= event.when_utc,
                is_scheduled_event=True,
                event_id=event.name,
            )
        return NewsVerdict(
            headline="no_news_window",
            source_name="HistoricalCalendar",
            source_type="calendar",
            normalized_utc_time=now_utc,
            freshness_status="fresh",
            verified=True,
            impact_level="low",
            market_bias="neutral",
            risk_mode="unclear",
            grade="B", confidence=0.6,
            trade_permission="allow",
            reason="no_calendar_event_in_window",
        )
