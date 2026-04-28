"""Replay must call the orchestrator once per (timestep, pair)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from replay.two_year_replay import TwoYearReplay


def _bar(t: datetime) -> Dict[str, Any]:
    return {
        "time": t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "complete": True,
        "volume": 100,
        "mid": {"c": "1.10"},
    }


class _Counter:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def run_cycle(self, *, symbol, now_utc, bars_by_pair, bars_by_tf):
        self.calls.append({"symbol": symbol, "now": now_utc, "n_visible": len(bars_by_pair[symbol])})
        return {"final_status": "BLOCK", "blocking_reason": "stub", "session_window": "MORNING"}


def test_replay_calls_orchestrator_per_pair_per_step():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars_eu = [_bar(base + timedelta(minutes=15 * i)) for i in range(5)]
    bars_jp = [_bar(base + timedelta(minutes=15 * i)) for i in range(5)]
    counter = _Counter()
    replay = TwoYearReplay(
        orchestrator=counter,
        smartnotebook=None,
        bars_by_pair={"EUR_USD": bars_eu, "USD_JPY": bars_jp},
    )
    result = replay.run(start=base, end=base + timedelta(hours=2))
    # 5 timesteps × 2 pairs = 10 cycles.
    assert result.total_cycles == 10
    assert len(counter.calls) == 10
    # First call per pair sees only 1 bar; last sees 5.
    n_visibles_eur = [c["n_visible"] for c in counter.calls if c["symbol"] == "EUR_USD"]
    assert n_visibles_eur[0] == 1
    assert n_visibles_eur[-1] == 5


def test_replay_handles_missing_bars_gracefully():
    """Pair with no bars in the window: zero cycles, no crash."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    counter = _Counter()
    replay = TwoYearReplay(
        orchestrator=counter,
        smartnotebook=None,
        bars_by_pair={"EUR_USD": []},
    )
    result = replay.run(start=base, end=base + timedelta(days=1))
    assert result.total_cycles == 0


def test_replay_iterates_over_two_year_window():
    base = datetime(2022, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # Create 200 bars spread over the window (one every ~3 days).
    bars = [_bar(base + timedelta(days=3 * i)) for i in range(200)]
    counter = _Counter()
    replay = TwoYearReplay(
        orchestrator=counter,
        smartnotebook=None,
        bars_by_pair={"EUR_USD": bars},
    )
    result = replay.run(start=base, end=end)
    assert result.total_cycles == 200


def test_replay_classifies_status():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [_bar(base + timedelta(minutes=15 * i)) for i in range(3)]

    class _Mixed:
        def __init__(self):
            self.idx = 0

        def run_cycle(self, *, symbol, now_utc, bars_by_pair, bars_by_tf):
            self.idx += 1
            if self.idx == 1:
                return {"final_status": "ENTER_CANDIDATE", "session_window": "MORNING"}
            if self.idx == 2:
                return {"final_status": "BLOCK", "session_window": "MORNING"}
            return {"final_status": "REJECT", "session_window": "MORNING"}

    replay = TwoYearReplay(orchestrator=_Mixed(), smartnotebook=None,
                           bars_by_pair={"EUR_USD": bars})
    r = replay.run(start=base, end=base + timedelta(hours=2))
    assert r.accepted_candidates == 1
    assert r.blocks == 1
    assert r.rejected_candidates == 1
    assert r.ny_session_blocks == 1


def test_replay_rejects_naive_dates():
    import pytest
    counter = _Counter()
    replay = TwoYearReplay(orchestrator=counter, smartnotebook=None, bars_by_pair={"X": []})
    with pytest.raises(ValueError):
        replay.run(start=datetime(2024, 1, 1), end=datetime(2024, 2, 1, tzinfo=timezone.utc))
