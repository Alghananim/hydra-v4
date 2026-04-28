# -*- coding: utf-8 -*-
"""per_brain_attribution — was each brain right on the trades it allowed?"""
from __future__ import annotations

from typing import Dict, List


def _agrees(brain_dir: str, trade_dir: str) -> bool:
    bd = (brain_dir or "").lower()
    td = (trade_dir or "").lower()
    if bd in ("up", "bullish", "buy", "long") and td == "buy":
        return True
    if bd in ("down", "bearish", "sell", "short") and td == "sell":
        return True
    return False


def attribute_per_brain(closed_trades: List) -> Dict[str, dict]:
    out: Dict[str, dict] = {
        "news":   {"trades": 0, "correct": 0, "accuracy": 0.0},
        "market": {"trades": 0, "correct": 0, "accuracy": 0.0},
        "chart":  {"trades": 0, "correct": 0, "accuracy": 0.0},
        "gate":   {"trades": 0, "correct": 0, "accuracy": 0.0},
    }

    for t in closed_trades:
        m = t.mind_outputs_dict or {}
        win = t.pnl_currency > 0
        td = t.direction

        n_dir = m.get("news_bias", "")
        out["news"]["trades"] += 1
        if _agrees(n_dir, td) and win:
            out["news"]["correct"] += 1
        elif n_dir in ("neutral", "unclear", "") and win:
            out["news"]["correct"] += 1

        out["market"]["trades"] += 1
        if _agrees(m.get("market_direction", ""), td) and win:
            out["market"]["correct"] += 1

        out["chart"]["trades"] += 1
        if _agrees(m.get("chart_trend_direction", ""), td) and win:
            out["chart"]["correct"] += 1

        out["gate"]["trades"] += 1
        if win:
            out["gate"]["correct"] += 1

    for v in out.values():
        v["accuracy"] = (v["correct"] / v["trades"]) if v["trades"] else 0.0

    return out
