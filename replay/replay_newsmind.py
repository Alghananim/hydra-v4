"""HYDRA V4 — ReplayNewsMindV4.

Architecturally clean replacement for NewsMindV4 in HISTORICAL REPLAY only.

WHY THIS EXISTS
---------------
The frozen live NewsMindV4 fans out across HTTP feeds (faireconomy.media,
RSS, etc.) and grades news quality from real-time confirmations. During a
historical 2-year replay, this is wrong on three axes:

  1. LOOKAHEAD: live feeds return current news, not 2024-vintage news.
  2. RATE LIMIT: ~2 sec/cycle × 99k cycles = 55+ hours.
  3. DATA QUALITY GATE: with sources=[] the live brain returns "broken" →
     BLOCK every cycle, by design (silence ≠ all-clear in production).

The architecture supports a clean replay path: NewsMindV4 already accepts
an `EventScheduler` whose `load_occurrences(...)` is the documented hook
for replay. The events.yaml file curates 10 high-impact macro events; the
calendar of when they occurred 2024-2026 is publicly known (Fed, ECB,
BoJ schedules + NFP/CPI cadence) and was published BEFORE each event
— so feeding those occurrences is NOT lookahead.

WHAT THIS CLASS DOES
--------------------
Same interface as NewsMindV4: `evaluate(pair, now_utc, current_bar=None)`
returns a contract-valid BrainOutput. Behaviour:

  * Inside any blackout window of any pair-affecting event → BLOCK
        (decision=BLOCK, grade=BLOCK, should_block=True)
  * Outside every blackout window → CLEAN
        (decision=WAIT, grade=A, data_quality=good)
        Evidence cites the calendar source and the next/previous event so
        a downstream auditor can reconstruct exactly why this cycle was
        graded clean.
  * No HTTP. No retries. No rate limits. Deterministic given the scheduler.

HONESTY POINTS
--------------
  * grade=A is honest because the scheduler IS a high-quality, no-lookahead
    source (central-bank schedules are published months in advance).
  * grade=BLOCK around events is honest because we have ground truth on
    when they actually happened.
  * What's MISSING vs the live brain: surprise score, breaking-news cross-
    confirmation, social-media chase detection. We do not pretend to
    grade those. We grade A on calendar-cleanness only.
  * GateMind's 3/3 A/A+ unanimous still applies — Chart+Market still need
    to agree. NewsMind's A is necessary but not sufficient.

HOW IT'S WIRED
--------------
`run_live_replay.py` builds a `ReplayNewsMindV4(scheduler)` and passes it
to `HydraOrchestratorV4(newsmind=...)`. The frozen orchestrator is
agnostic — it duck-types `evaluate()`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from contracts.brain_output import BrainGrade, BrainOutput
from newsmind.v4.event_scheduler import EventScheduler
from newsmind.v4.models import _normalize_pair


class ReplayNewsMindV4:
    """Calendar-only NewsMind for historical replay. No HTTP. No lookahead."""

    BRAIN_NAME = "newsmind"

    def __init__(self, scheduler: EventScheduler) -> None:
        if not isinstance(scheduler, EventScheduler):
            raise TypeError("scheduler must be an EventScheduler instance")
        self._scheduler = scheduler

    # NewsMindV4-compatible interface ---------------------------------------

    def evaluate(
        self,
        pair: str,
        now_utc: datetime,
        current_bar: Optional[Dict[str, Any]] = None,
    ) -> BrainOutput:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be tz-aware UTC")
        pair_u = _normalize_pair(pair)

        active = self._scheduler.get_active_event(pair_u, now_utc)

        if active is not None:
            ev = active.event
            return BrainOutput(
                brain_name=self.BRAIN_NAME,
                decision="BLOCK",
                grade=BrainGrade.BLOCK,
                reason=(
                    f"scheduled-event blackout: {ev.id} "
                    f"at {active.scheduled_utc.isoformat()} "
                    f"(window -{ev.blackout_pre_min}m / +{ev.blackout_post_min}m)"
                ),
                evidence=[
                    f"event_id={ev.id}",
                    f"event_name={ev.name}",
                    f"event_tier={ev.tier}",
                    f"scheduled_utc={active.scheduled_utc.isoformat()}",
                    f"blackout_pre_min={ev.blackout_pre_min}",
                    f"blackout_post_min={ev.blackout_post_min}",
                    "source=replay_calendar (publicly pre-announced; no lookahead)",
                ],
                data_quality="good",
                should_block=True,
                risk_flags=["news_blackout"],
                confidence=0.95,
                timestamp_utc=now_utc,
            )

        # No active blackout — clean window.
        next_event = self._next_event(pair_u, now_utc)
        return BrainOutput(
            brain_name=self.BRAIN_NAME,
            decision="WAIT",  # NewsMind never emits BUY/SELL alone
            grade=BrainGrade.A,
            reason="no scheduled-event blackout — replay calendar clean",
            evidence=[
                f"scheduler_occurrences_loaded={self._scheduler_size()}",
                f"checked_at={now_utc.isoformat()}",
                f"next_event_for_pair={next_event}",
                "source=replay_calendar (publicly pre-announced; no lookahead)",
            ],
            data_quality="good",
            should_block=False,
            risk_flags=[],
            confidence=0.85,
            timestamp_utc=now_utc,
        )

    # ----------------------------------------------------------- helpers

    def _scheduler_size(self) -> int:
        # _occurrences is a private list inside EventScheduler; access via
        # documented internal attribute. Length is informational only.
        return len(getattr(self._scheduler, "_occurrences", []))

    def _next_event(self, pair_u: str, now_utc: datetime) -> str:
        for occ in getattr(self._scheduler, "_occurrences", []):
            if occ.scheduled_utc <= now_utc:
                continue
            if not occ.event.affects_pair(pair_u):
                continue
            return f"{occ.event.id}@{occ.scheduled_utc.isoformat()}"
        return "none_scheduled"
