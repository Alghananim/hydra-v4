"""NewsMind V4 — event scheduler.

Loads events from events.yaml and answers two questions:

  is_in_blackout(pair, now_utc) -> bool
  get_active_event(pair, now_utc) -> EventSchedule | None

V3's bug: event_scheduler hardcoded an empty in-memory list and never read
events.yaml — meaning the blackout was always False. V4 actually loads.

Note: events.yaml describes blackout *windows* (pre/post minutes) but the
specific occurrence times of each event come from the calendar feed at
runtime. To support unit tests, the scheduler can also be fed a manual list
of `(event_id, scheduled_time_utc)` tuples via `load_occurrences()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from newsmind.v4.config_loader import load_events
from newsmind.v4.models import EventSchedule, _normalize_pair


@dataclass(frozen=True)
class EventOccurrence:
    event: EventSchedule
    scheduled_utc: datetime  # tz-aware UTC

    def __post_init__(self) -> None:
        if self.scheduled_utc.tzinfo is None:
            raise ValueError("scheduled_utc must be tz-aware")


class EventScheduler:
    def __init__(
        self,
        events: Optional[List[EventSchedule]] = None,
        events_yaml_path: Optional[Path] = None,
    ) -> None:
        if events is None:
            events = load_events(events_yaml_path)
        self._events: List[EventSchedule] = list(events)
        self._by_id = {e.id: e for e in self._events}
        self._occurrences: List[EventOccurrence] = []

    # ------------------------------------------------------------------ load

    def load_occurrences(
        self, occurrences: Iterable[Tuple[str, datetime]]
    ) -> None:
        """Replace the occurrence list with `(event_id, scheduled_utc)` tuples."""
        new: List[EventOccurrence] = []
        for ev_id, when in occurrences:
            if ev_id not in self._by_id:
                raise KeyError(f"Unknown event id: {ev_id!r}")
            if when.tzinfo is None:
                raise ValueError(f"Occurrence for {ev_id} must be tz-aware UTC")
            new.append(EventOccurrence(event=self._by_id[ev_id], scheduled_utc=when))
        self._occurrences = sorted(new, key=lambda o: o.scheduled_utc)

    # --------------------------------------------------------------- queries

    def known_event_ids(self) -> List[str]:
        return list(self._by_id.keys())

    def is_in_blackout(self, pair: str, now_utc: datetime) -> bool:
        return self.get_active_event(pair, now_utc) is not None

    def get_active_event(
        self, pair: str, now_utc: datetime
    ) -> Optional[EventOccurrence]:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be tz-aware UTC")
        pair_u = _normalize_pair(pair)
        for occ in self._occurrences:
            if not occ.event.affects_pair(pair_u):
                continue
            window_start = occ.scheduled_utc - timedelta(minutes=occ.event.blackout_pre_min)
            window_end = occ.scheduled_utc + timedelta(minutes=occ.event.blackout_post_min)
            if window_start <= now_utc <= window_end:
                return occ
        return None

    def in_pre_event_window(self, pair: str, now_utc: datetime) -> bool:
        occ = self.get_active_event(pair, now_utc)
        return occ is not None and now_utc < occ.scheduled_utc

    def in_post_event_window(self, pair: str, now_utc: datetime) -> bool:
        occ = self.get_active_event(pair, now_utc)
        return occ is not None and now_utc >= occ.scheduled_utc
