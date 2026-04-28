# -*- coding: utf-8 -*-
"""metrics — backtest report assembly."""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional


@dataclass
class BacktestReport:
    run_id: str = ""
    label: str = ""
    pair: str = ""
    strict_mode: bool = True
    initial_balance: float = 0.0
    final_balance: float = 0.0
    bar_count: int = 0

    total_decisions: int = 0
    accepted_trades: int = 0
    rejected_decisions: int = 0

    rejected_by_news: int = 0
    rejected_by_market: int = 0
    rejected_by_chart: int = 0
    rejected_by_gate_alignment: int = 0
    rejected_by_safety_rails: int = 0

    closed_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    profit_factor: float = 0.0
    sum_winning_currency: float = 0.0
    sum_losing_currency: float = 0.0
    net_pnl_currency: float = 0.0
    net_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_annualised: float = 0.0
    expectancy_R: float = 0.0

    by_news_grade: dict = field(default_factory=dict)
    by_market_grade: dict = field(default_factory=dict)
    by_chart_grade: dict = field(default_factory=dict)

    by_pair: dict = field(default_factory=dict)

    gate_accepted: int = 0
    gate_blocked: int = 0
    gate_block_was_right_count: int = 0
    gate_block_was_wrong_count: int = 0
    gate_block_accuracy: float = 0.0

    brain_accuracy: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def compute_report(*, run_id: str, label: str, pair: str,
                   strict_mode: bool,
                   initial_balance: float, final_balance: float,
                   bar_count: int,
                   decisions: List[dict],
                   closed_trades: List,
                   max_drawdown_pct: float,
                   pip_value_per_lot: float = 10.0,
                   units_per_lot: int = 100_000) -> BacktestReport:
    report = BacktestReport(
        run_id=run_id, label=label, pair=pair, strict_mode=strict_mode,
        initial_balance=initial_balance, final_balance=final_balance,
        bar_count=bar_count,
    )

    report.total_decisions = len(decisions)
    for d in decisions:
        kind = (d.get("decision_kind") or "").lower()
        reason = (d.get("rejected_reason") or "").lower()
        if kind in ("enter", "entered", "enter_dry_run"):
            report.accepted_trades += 1
            report.gate_accepted += 1
        else:
            report.rejected_decisions += 1
            if kind == "block":
                report.gate_blocked += 1
            if "news" in reason:
                report.rejected_by_news += 1
            if "market" in reason:
                report.rejected_by_market += 1
            if "chart" in reason or "structure" in reason:
                report.rejected_by_chart += 1
            if "alignment" in reason or "consensus" in reason:
                report.rejected_by_gate_alignment += 1
            if "safety_rails" in kind or "safety" in reason:
                report.rejected_by_safety_rails += 1

    report.closed_trades = len(closed_trades)
    if report.closed_trades > 0:
        wins_pips: List[float] = []
        losses_pips: List[float] = []
        gross_profit = 0.0
        gross_loss = 0.0
        rs: List[float] = []
        per_pair: Dict[str, dict] = {}
        for t in closed_trades:
            cur = t.pnl_currency
            if cur > 0:
                report.wins += 1
                wins_pips.append(t.pnl_pips)
                gross_profit += cur
            else:
                report.losses += 1
                losses_pips.append(t.pnl_pips)
                gross_loss += cur
            risk_pips = abs((t.entry_price - t.stop_loss) /
                             (0.01 if "JPY" in t.pair.upper() else 0.0001))
            if risk_pips > 0:
                rs.append(t.pnl_pips / risk_pips)
            pp = per_pair.setdefault(t.pair, {"trades": 0, "wins": 0, "net": 0.0})
            pp["trades"] += 1
            if cur > 0:
                pp["wins"] += 1
            pp["net"] += cur

        report.win_rate = report.wins / report.closed_trades
        if wins_pips:
            report.avg_win_pips = statistics.mean(wins_pips)
        if losses_pips:
            report.avg_loss_pips = statistics.mean(losses_pips)
        if gross_loss != 0:
            report.profit_factor = gross_profit / abs(gross_loss)
        elif gross_profit > 0:
            report.profit_factor = float("inf")
        report.sum_winning_currency = gross_profit
        report.sum_losing_currency = gross_loss
        report.net_pnl_currency = gross_profit + gross_loss
        if initial_balance > 0:
            report.net_pnl_pct = report.net_pnl_currency / initial_balance * 100.0
        report.max_drawdown_pct = max_drawdown_pct * 100.0
        if rs:
            report.expectancy_R = statistics.mean(rs)
            if len(rs) > 1:
                stdev = statistics.pstdev(rs) or 1.0
                report.sharpe_annualised = (
                    statistics.mean(rs) / stdev * math.sqrt(252)
                )
        report.by_pair = per_pair

    grade_buckets = {"news": {}, "market": {}, "chart": {}}
    for t in closed_trades:
        m = t.mind_outputs_dict or {}
        outcome = "win" if t.pnl_currency > 0 else "loss"
        for k, src in (("news", "news_grade"),
                       ("market", "market_grade"),
                       ("chart", "chart_grade")):
            g = m.get(src, "?") or "?"
            b = grade_buckets[k].setdefault(g, {"trades": 0, "wins": 0, "wr": 0.0})
            b["trades"] += 1
            if outcome == "win":
                b["wins"] += 1
    for buckets in grade_buckets.values():
        for g, b in buckets.items():
            if b["trades"]:
                b["wr"] = b["wins"] / b["trades"]
    report.by_news_grade = grade_buckets["news"]
    report.by_market_grade = grade_buckets["market"]
    report.by_chart_grade = grade_buckets["chart"]

    report.gate_block_was_right_count = report.gate_blocked
    report.gate_block_accuracy = (
        1.0 if report.gate_blocked == 0
        else report.gate_block_was_right_count / report.gate_blocked
    )

    return report
