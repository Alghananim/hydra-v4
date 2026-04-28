"""Adversarial: place a marker bar in the future and verify the
orchestrator never sees it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from replay.leakage_guard import LeakageError, assert_no_future, slice_visible
from replay.two_year_replay import TwoYearReplay


def _bar(t: datetime, marker: bool = False) -> Dict[str, Any]:
    return {
        "time": t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "complete": True,
        "volume": 100,
        "mid": {"o": "1.10", "h": "1.11", "l": "1.09", "c": "1.10"},
        "marker": marker,
    }


class _SnoopOrchestrator:
    """Records the maximum bar timestamp it ever sees per cycle."""

    def __init__(self):
        self.cycles: List[Dict[str, Any]] = []
        self.saw_marker = False

    def run_cycle(self, *, symbol, now_utc, bars_by_pair, bars_by_tf):
        bars = bars_by_pair[symbol]
        for b in bars:
            if b.get("marker"):
                self.saw_marker = True
        max_t = None
        for b in bars:
            t = b["time"]
            if t.endswith("Z"):
                t = t[:-1] + "+00:00"
            dt = datetime.fromisoformat(t)
            if max_t is None or dt > max_t:
                max_t = dt
        self.cycles.append({"now": now_utc, "max_bar_time": max_t})
        return {"final_status": "BLOCK", "blocking_reason": "stub", "session_window": "MORNING"}


def test_orchestrator_never_sees_future_bar():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(base + timedelta(minutes=15 * i)) for i in range(20)]
    # Add a marker bar in the FUTURE.
    bars.append(_bar(base + timedelta(days=30), marker=True))

    snoop = _SnoopOrchestrator()
    replay = TwoYearReplay(
        orchestrator=snoop,
        smartnotebook=None,
        bars_by_pair={"EUR_USD": bars},
    )
    result = replay.run(start=base, end=base + timedelta(hours=10))
    assert result.total_cycles > 0
    assert snoop.saw_marker is False, "orchestrator must NEVER see the future marker"
    # Every cycle's max bar time must be <= the clock at that cycle.
    for c in snoop.cycles:
        assert c["max_bar_time"] <= c["now"], (
            f"future leak: max_bar={c['max_bar_time']}, now={c['now']}"
        )


def test_slice_visible_excludes_future():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(base + timedelta(minutes=15 * i)) for i in range(10)]
    cutoff = base + timedelta(minutes=15 * 5)
    out = slice_visible(bars, cutoff)
    assert len(out) == 6  # bars at i=0..5 inclusive


def test_assert_no_future_raises_on_leak():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(base + timedelta(minutes=15 * i)) for i in range(5)]
    with pytest.raises(LeakageError):
        assert_no_future(bars, base + timedelta(minutes=10))  # i=1 already > 10


def test_assert_no_future_passes_clean():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(base + timedelta(minutes=15 * i)) for i in range(5)]
    assert_no_future(bars, base + timedelta(hours=10))
