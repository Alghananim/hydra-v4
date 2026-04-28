"""HYDRA V4 — TwoYearReplay.

Drives the orchestrator over chronologically-ordered bars. Each cycle:

  1. `replay_clock.advance_to(bar.time)`
  2. For each pair: slice visible bars (no future) and call
     `orchestrator.run_cycle(symbol=pair, now_utc=clock.now(),
                              bars_by_pair=visible, bars_by_tf={"M15": visible})`
  3. SmartNoteBook records DECISION_CYCLE + GATE_AUDIT inside run_cycle.
  4. After replay completes, walk REJECTED_TRADE records and emit
     SHADOW_OUTCOME records using actual realized prices (now in past).
  5. Lesson extractor produces CANDIDATE lessons with
     `allowed_from_timestamp = end_of_replay`.

The orchestrator is duck-typed — anything with a `run_cycle(symbol,
now_utc, bars_by_pair, bars_by_tf, ...)` signature works.

If `anthropic_bridge` is provided, it is offered to the orchestrator
via `bars_by_tf["__anthropic_bridge"]` (the orchestrator chooses
whether to consult it; we never inject it into bar streams). For the
default mock orchestrator we don't call the bridge.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from replay.leakage_guard import (
    LeakageError,
    _bar_time,
    assert_no_future,
    slice_visible,
)
from replay.replay_clock import ReplayClock

_log = logging.getLogger("replay")


class _OrchestratorLike(Protocol):
    def run_cycle(
        self,
        *,
        symbol: str,
        now_utc: datetime,
        bars_by_pair: Dict[str, List[Dict[str, Any]]],
        bars_by_tf: Dict[str, List[Dict[str, Any]]],
    ) -> Any: ...


@dataclass
class ReplayResult:
    total_cycles: int = 0
    accepted_candidates: int = 0
    rejected_candidates: int = 0
    blocks: int = 0
    ny_session_blocks: int = 0
    brain_performance: Dict[str, Any] = field(default_factory=dict)
    lessons_extracted: int = 0
    errors: int = 0
    shadow_outcomes_generated: int = 0
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None


class TwoYearReplay:
    """Chronological replay engine."""

    def __init__(
        self,
        orchestrator: _OrchestratorLike,
        smartnotebook: Any,
        bars_by_pair: Dict[str, List[Dict[str, Any]]],
        anthropic_bridge: Optional[Any] = None,
        cycle_callback: Optional[Callable[[str, datetime, Any], None]] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._notebook = smartnotebook
        self._bars_by_pair = {p: list(bars) for p, bars in bars_by_pair.items()}
        self._bridge = anthropic_bridge
        self._cycle_cb = cycle_callback

    # ------------------------------------------------------------------
    def run(
        self,
        start: datetime,
        end: datetime,
        pairs: Optional[List[str]] = None,
    ) -> ReplayResult:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start, end must be tz-aware UTC")
        if start >= end:
            raise ValueError("start must be < end")

        pairs = pairs or list(self._bars_by_pair.keys())
        for p in pairs:
            if p not in self._bars_by_pair:
                raise KeyError(f"no bars loaded for pair {p!r}")

        # Chronological master timeline = union of all bar times across pairs,
        # filtered to [start, end].
        timeline: List[datetime] = []
        for p in pairs:
            for b in self._bars_by_pair[p]:
                bt = _bar_time(b)
                if bt is None:
                    continue
                if start <= bt <= end:
                    timeline.append(bt)
        timeline.sort()
        # Dedupe — same instant across pairs only fires once.
        deduped: List[datetime] = []
        last = None
        for t in timeline:
            if t != last:
                deduped.append(t)
                last = t
        timeline = deduped

        clock = ReplayClock(start)
        result = ReplayResult(start_utc=start, end_utc=end)

        for now_utc in timeline:
            clock.advance_to(now_utc)
            for pair in pairs:
                visible = slice_visible(self._bars_by_pair[pair], now_utc)
                # Defense in depth — the slice should have removed all future.
                assert_no_future(visible, now_utc)
                try:
                    cycle = self._orchestrator.run_cycle(
                        symbol=pair,
                        now_utc=clock.now(),
                        bars_by_pair={pair: visible},
                        bars_by_tf={"M15": visible},
                    )
                    result.total_cycles += 1
                    self._classify_cycle(cycle, result)
                    if self._cycle_cb is not None:
                        self._cycle_cb(pair, clock.now(), cycle)
                except LeakageError:
                    raise  # never swallow leak errors
                except Exception as e:  # noqa: BLE001
                    result.errors += 1
                    _log.exception("orchestrator error at %s for %s: %s",
                                   now_utc.isoformat(), pair, e)

        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _classify_cycle(cycle: Any, result: ReplayResult) -> None:
        # Cycle is duck-typed; we look for `final_status` attribute or key.
        status = None
        if isinstance(cycle, dict):
            status = cycle.get("final_status")
        else:
            status = getattr(cycle, "final_status", None)
        if status == "ENTER_CANDIDATE":
            result.accepted_candidates += 1
        elif status == "REJECT" or status == "REJECTED":
            result.rejected_candidates += 1
        elif status == "BLOCK":
            result.blocks += 1
            # NY-session blocks are flagged when the cycle reports
            # session_window starting with 'MORNING' or 'PRE_OPEN'.
            sess = (cycle.get("session_window") if isinstance(cycle, dict)
                    else getattr(cycle, "session_window", "")) or ""
            if sess.startswith("MORNING") or sess.startswith("PRE_OPEN"):
                result.ny_session_blocks += 1
