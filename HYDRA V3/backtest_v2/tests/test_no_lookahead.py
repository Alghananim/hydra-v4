# -*- coding: utf-8 -*-
"""test_no_lookahead — adversarial: any signal-phase access to a
future bar must raise LookaheadLeakError."""
from __future__ import annotations

import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.leak_detector import LeakSafeBars, LookaheadLeakError
from backtest_v2.fixtures.synthetic_bars import make_trending_series


def _bars():
    return make_trending_series(n_bars=20)


def test_index_past_cursor_raises():
    bars = _bars()
    safe = LeakSafeBars(bars, cursor=10)
    with pytest.raises(LookaheadLeakError):
        _ = safe[11]
    with pytest.raises(LookaheadLeakError):
        _ = safe[15]


def test_slice_past_cursor_raises():
    bars = _bars()
    safe = LeakSafeBars(bars, cursor=10)
    with pytest.raises(LookaheadLeakError):
        _ = safe[: 12]
    with pytest.raises(LookaheadLeakError):
        _ = safe[8: 15]


def test_iter_stops_at_cursor():
    bars = _bars()
    safe = LeakSafeBars(bars, cursor=5)
    seen = list(safe)
    assert len(seen) == 6, f"iter should stop at cursor, got {len(seen)}"


def test_visible_returns_only_past():
    bars = _bars()
    safe = LeakSafeBars(bars, cursor=5)
    vis = safe.visible()
    assert len(vis) == 6
    assert vis[-1] is bars[5]


def test_set_cursor_advances_visibility():
    bars = _bars()
    safe = LeakSafeBars(bars, cursor=3)
    with pytest.raises(LookaheadLeakError):
        _ = safe[5]
    safe.set_cursor(5)
    assert safe[5] is bars[5]


def test_runner_signal_phase_does_not_see_next_bar():
    from backtest_v2.config import BacktestConfig
    from backtest_v2.runner import BacktestRunner
    from backtest_v2.fixtures.synthetic_news import make_quiet_news_replay

    bars = make_trending_series(n_bars=80)
    cfg = BacktestConfig(pair="EUR/USD", initial_balance=10_000.0,
                          smartnotebook_dir=pathlib.Path("/tmp/bt2_test_no_lookahead_nb"),
                          output_dir=pathlib.Path("/tmp/bt2_test_no_lookahead_out"),
                          max_bars=60, label="lookahead_test")
    runner = BacktestRunner(cfg=cfg, bars=bars,
                             calendar_replay=make_quiet_news_replay())

    captures: list = []
    real_signal = runner._signal_phase

    def spy_signal(*, bar_t, visible_bars):
        captures.append((bar_t.time, len(visible_bars), bars.index(bar_t)))
        return real_signal(bar_t=bar_t, visible_bars=visible_bars)

    runner._signal_phase = spy_signal     # type: ignore
    outcome = runner.run()

    assert captures, "runner did not iterate any bars"
    for bar_time, visible_len, idx in captures:
        assert visible_len == idx + 1, (
            f"leak: bar at idx {idx} saw {visible_len} bars "
            f"(should be {idx+1})")

    assert not outcome.leak_events, f"leaks recorded: {outcome.leak_events}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
