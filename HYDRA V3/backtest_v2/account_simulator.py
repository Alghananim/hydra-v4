# -*- coding: utf-8 -*-
"""account_simulator — paper account state across the backtest."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class OpenPosition:
    trade_id: str
    audit_id: str
    pair: str
    direction: str
    units: float
    entry_time: datetime
    entry_price: float
    stop_loss: float
    take_profit: float
    expected_rr: float = 0.0
    spread_at_entry: float = 0.0
    slippage_at_entry: float = 0.0
    mind_outputs_dict: dict = field(default_factory=dict)
    mfe: float = 0.0
    mae: float = 0.0


@dataclass
class ClosedTrade:
    trade_id: str
    audit_id: str
    pair: str
    direction: str
    units: float
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    stop_loss: float
    take_profit: float
    expected_rr: float
    pnl_pips: float
    pnl_currency: float
    pnl_pct: float
    exit_reason: str
    hit_target: bool
    hit_stop: bool
    spread_at_entry: float
    slippage_at_entry: float
    mind_outputs_dict: dict = field(default_factory=dict)
    mfe: float = 0.0
    mae: float = 0.0


class AccountSimulator:
    def __init__(self, *, initial_balance: float, pair_pip: float):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.pair_pip = pair_pip
        self.open_positions: List[OpenPosition] = []
        self.closed_trades: List[ClosedTrade] = []
        self.equity_curve: List[tuple] = []
        self.high_water_mark: float = self.balance
        self.max_drawdown_pct: float = 0.0

    def mark_to_market(self, now: datetime, mid_price: float) -> float:
        unreal = 0.0
        for p in self.open_positions:
            if p.direction == "buy":
                unreal += (mid_price - p.entry_price) * p.units
            else:
                unreal += (p.entry_price - mid_price) * p.units
        eq = self.balance + unreal
        self.equity_curve.append((now, eq))
        if eq > self.high_water_mark:
            self.high_water_mark = eq
        if self.high_water_mark > 0:
            dd = (self.high_water_mark - eq) / self.high_water_mark
            if dd > self.max_drawdown_pct:
                self.max_drawdown_pct = dd
        return eq

    def open(self, pos: OpenPosition) -> None:
        self.open_positions.append(pos)

    def close(self, trade: ClosedTrade) -> None:
        self.open_positions = [p for p in self.open_positions
                                if p.trade_id != trade.trade_id]
        self.balance += trade.pnl_currency
        self.closed_trades.append(trade)

    def has_open(self) -> bool:
        return len(self.open_positions) > 0

    def snapshot(self) -> Dict:
        return {
            "balance": self.balance,
            "equity": self.balance,
            "open_positions": tuple(
                {"trade_id": p.trade_id, "pair": p.pair,
                 "direction": p.direction, "units": p.units,
                 "entry": p.entry_price}
                for p in self.open_positions),
            "closed_count": len(self.closed_trades),
            "high_water_mark": self.high_water_mark,
        }
