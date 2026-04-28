# -*- coding: utf-8 -*-
"""test_engine_parity — backtest uses the SAME EngineV3 production uses."""
from __future__ import annotations

import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.config import BacktestConfig
from backtest_v2.runner import BacktestRunner, _BacktestNotebookProxy
from backtest_v2.fixtures.synthetic_bars import make_trending_series
from backtest_v2.fixtures.synthetic_news import make_quiet_news_replay


def _runner():
    bars = make_trending_series(n_bars=40)
    cfg = BacktestConfig(pair="EUR/USD",
                          smartnotebook_dir=pathlib.Path("/tmp/bt2_test_engine_parity_nb"),
                          output_dir=pathlib.Path("/tmp/bt2_test_engine_parity_out"))
    return BacktestRunner(cfg=cfg, bars=bars,
                            calendar_replay=make_quiet_news_replay())


def test_engine_is_production_class():
    from engine.v3 import EngineV3
    r = _runner()
    assert isinstance(r._engine, EngineV3), (
        f"backtest engine is {type(r._engine)}, not production EngineV3")


def test_decide_method_is_production_method():
    from engine.v3 import EngineV3
    r = _runner()
    inst_fn = r._engine.decide_and_maybe_trade.__func__
    cls_fn = EngineV3.decide_and_maybe_trade
    assert inst_fn is cls_fn, "decide_and_maybe_trade differs from production"


def test_notebook_is_tagged_proxy_over_real_smartnotebook():
    from smartnotebook.v3 import SmartNoteBookV3
    r = _runner()
    assert isinstance(r._engine.nb, _BacktestNotebookProxy)
    assert isinstance(r._engine.nb._nb, SmartNoteBookV3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
