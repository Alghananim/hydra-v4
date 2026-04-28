# -*- coding: utf-8 -*-
"""test_no_mode_pollution — every entry tagged system_mode='backtest'."""
from __future__ import annotations

import sys
import sqlite3
import pathlib
import shutil
import json
from datetime import datetime, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.config import BacktestConfig
from backtest_v2.runner import BacktestRunner
from backtest_v2.fixtures.synthetic_bars import make_breakout_series
from backtest_v2.fixtures.synthetic_news import make_quiet_news_replay


def _isolated_paths(tag: str):
    nb = pathlib.Path(f"/tmp/bt2_test_no_pollution_{tag}_nb")
    out = pathlib.Path(f"/tmp/bt2_test_no_pollution_{tag}_out")
    for p in (nb, out):
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)
    return nb, out


def test_every_entry_tagged_backtest():
    nb_dir, out_dir = _isolated_paths("primary")
    bars = make_breakout_series(n_bars=80)
    cfg = BacktestConfig(pair="EUR/USD", initial_balance=10_000.0,
                          smartnotebook_dir=nb_dir, output_dir=out_dir,
                          max_bars=70, label="pollution_test",
                          strict_mode=True)
    runner = BacktestRunner(cfg=cfg, bars=bars,
                             calendar_replay=make_quiet_news_replay())
    runner.run()

    db_path = nb_dir / "notebook.db"
    assert db_path.exists(), f"notebook DB not created at {db_path}"

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("SELECT payload FROM decision_events")
    rows = cur.fetchall()
    assert rows, "no decision events recorded"
    bad = []
    for (payload_json,) in rows:
        d = json.loads(payload_json)
        if d.get("system_mode") != "backtest":
            bad.append(d.get("system_mode"))
    assert not bad, f"non-backtest decisions found: modes={set(bad)}"

    cur.execute("SELECT system_mode FROM trade_audit")
    trade_modes = [r[0] for r in cur.fetchall()]
    for m in trade_modes:
        assert m == "backtest", f"trade tagged {m!r}, not 'backtest'"

    conn.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
