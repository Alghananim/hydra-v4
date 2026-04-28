# -*- coding: utf-8 -*-
"""reporter — before/after diff between two BacktestReports."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import List, Tuple

from .metrics import BacktestReport


def _fmt_int(x) -> str:
    try:
        return f"{int(x):,}"
    except Exception:
        return str(x)


def _fmt_pct(x) -> str:
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return str(x)


def _fmt_float(x, ndp: int = 2) -> str:
    try:
        return f"{float(x):.{ndp}f}"
    except Exception:
        return str(x)


def _delta(a, b) -> str:
    try:
        d = float(b) - float(a)
        if abs(d) >= 100:
            return f"{d:+,.0f}"
        if abs(d) >= 1:
            return f"{d:+.2f}"
        return f"{d:+.4f}"
    except Exception:
        return "n/a"


def diff_text(left: BacktestReport, right: BacktestReport) -> str:
    rows: List[Tuple[str, str, str, str]] = []
    rows.append(("metric",
                 left.label or ("loose" if not left.strict_mode else "strict"),
                 right.label or ("strict" if right.strict_mode else "loose"),
                 "delta"))
    rows.append(("-----", "-----", "-----", "-----"))
    rows.append(("Total decisions",
                 _fmt_int(left.total_decisions),
                 _fmt_int(right.total_decisions),
                 _delta(left.total_decisions, right.total_decisions)))
    rows.append(("Accepted trades",
                 _fmt_int(left.accepted_trades),
                 _fmt_int(right.accepted_trades),
                 _delta(left.accepted_trades, right.accepted_trades)))
    rows.append(("Closed trades",
                 _fmt_int(left.closed_trades),
                 _fmt_int(right.closed_trades),
                 _delta(left.closed_trades, right.closed_trades)))
    rows.append(("Win rate",
                 _fmt_pct(left.win_rate * 100),
                 _fmt_pct(right.win_rate * 100),
                 _delta(left.win_rate * 100, right.win_rate * 100) + "pp"))
    rows.append(("Profit factor",
                 _fmt_float(left.profit_factor, 2),
                 _fmt_float(right.profit_factor, 2),
                 _delta(left.profit_factor, right.profit_factor)))
    rows.append(("Net P&L",
                 _fmt_pct(left.net_pnl_pct),
                 _fmt_pct(right.net_pnl_pct),
                 _delta(left.net_pnl_pct, right.net_pnl_pct) + "pp"))
    rows.append(("Max DD",
                 _fmt_pct(left.max_drawdown_pct),
                 _fmt_pct(right.max_drawdown_pct),
                 _delta(left.max_drawdown_pct, right.max_drawdown_pct) + "pp"))
    rows.append(("Sharpe (ann)",
                 _fmt_float(left.sharpe_annualised, 2),
                 _fmt_float(right.sharpe_annualised, 2),
                 _delta(left.sharpe_annualised, right.sharpe_annualised)))
    rows.append(("Expectancy (R)",
                 _fmt_float(left.expectancy_R, 2),
                 _fmt_float(right.expectancy_R, 2),
                 _delta(left.expectancy_R, right.expectancy_R)))
    rows.append(("Gate blocks",
                 _fmt_int(left.gate_blocked),
                 _fmt_int(right.gate_blocked),
                 _delta(left.gate_blocked, right.gate_blocked)))

    col_w = [max(len(r[i]) for r in rows) for i in range(4)]
    out = []
    for r in rows:
        line = " | ".join(r[i].ljust(col_w[i]) for i in range(4))
        out.append(line)
    return "\n".join(out)


def diff_json(left: BacktestReport, right: BacktestReport) -> str:
    return json.dumps(
        {"left": left.to_dict(), "right": right.to_dict()},
        indent=2, default=str)
