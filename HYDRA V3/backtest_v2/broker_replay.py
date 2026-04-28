# -*- coding: utf-8 -*-
"""broker_replay — mock broker that fills at next-bar open + spread."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .account_simulator import AccountSimulator, ClosedTrade, OpenPosition


class ReplayBroker:
    def __init__(self, *, account: AccountSimulator, pair: str,
                 pair_pip: float,
                 entry_slippage_pips: float = 0.5,
                 stop_slippage_pips: float = 1.0,
                 target_slippage_pips: float = 0.2,
                 fallback_spread_pips: float = 0.5,
                 commission_per_lot_per_side: float = 0.0,
                 pip_value_per_lot: float = 10.0,
                 units_per_lot: int = 100_000):
        from Backtest.costs import CostModel    # type: ignore
        self.account = account
        self.pair = pair
        self.pair_pip = pair_pip
        self.cost = CostModel(
            pair_pip=pair_pip,
            pip_value_per_lot=pip_value_per_lot,
            units_per_lot=units_per_lot,
            entry_slippage_pips=entry_slippage_pips,
            stop_slippage_pips=stop_slippage_pips,
            fallback_spread_pips=fallback_spread_pips,
            commission_per_lot_per_side=commission_per_lot_per_side,
            target_slippage_pips=target_slippage_pips,
        )
        self.pip_value_per_lot = pip_value_per_lot
        self.units_per_lot = units_per_lot

    def fill_entry_at_next_open(self, *, signal_bar, next_bar,
                                 direction: str, units: float,
                                 stop_loss: float, take_profit: float,
                                 expected_rr: float = 0.0,
                                 mind_outputs_dict: Optional[dict] = None,
                                 trade_id: Optional[str] = None,
                                 audit_id: Optional[str] = None) -> OpenPosition:
        bid_open = getattr(next_bar, "bid_open", None)
        ask_open = getattr(next_bar, "ask_open", None)
        fill = self.cost.simulate_entry(
            direction="long" if direction == "buy" else "short",
            order_type="market",
            requested_price=next_bar.open,
            next_bar_open=next_bar.open,
            next_bar_bid=bid_open,
            next_bar_ask=ask_open,
            lot=units / self.units_per_lot,
            fill_time=next_bar.time,
        )
        pos = OpenPosition(
            trade_id=trade_id or str(uuid.uuid4()),
            audit_id=audit_id or str(uuid.uuid4()),
            pair=self.pair,
            direction=direction,
            units=units,
            entry_time=fill.fill_time,
            entry_price=fill.fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            expected_rr=expected_rr,
            spread_at_entry=fill.spread_paid_pips,
            slippage_at_entry=abs(fill.slippage_pips),
            mind_outputs_dict=dict(mind_outputs_dict or {}),
        )
        self.account.open(pos)
        return pos

    def update_open_positions(self, *, bar) -> list:
        closed_now: list = []
        for p in list(self.account.open_positions):
            if p.direction == "buy":
                fav = bar.high - p.entry_price
                adv = bar.low - p.entry_price
            else:
                fav = p.entry_price - bar.low
                adv = p.entry_price - bar.high
            if fav > p.mfe: p.mfe = fav
            if adv < p.mae: p.mae = adv

            stop_hit, target_hit = self._range_hits(p, bar)
            if not (stop_hit or target_hit):
                continue

            if stop_hit:
                fill = self.cost.simulate_stop_hit(
                    direction="long" if p.direction == "buy" else "short",
                    stop_price=p.stop_loss,
                    bar_high=bar.high, bar_low=bar.low,
                    fill_time=bar.time,
                    lot=p.units / self.units_per_lot)
                exit_reason = "stop"
                hit_target, hit_stop = False, True
            else:
                fill = self.cost.simulate_target_hit(
                    direction="long" if p.direction == "buy" else "short",
                    target_price=p.take_profit,
                    bar_high=bar.high, bar_low=bar.low,
                    fill_time=bar.time,
                    lot=p.units / self.units_per_lot)
                exit_reason = "target"
                hit_target, hit_stop = True, False

            if not fill.filled:
                continue

            pip_move, pnl_currency = self.cost.pnl_currency(
                direction="long" if p.direction == "buy" else "short",
                entry_price=p.entry_price,
                exit_price=fill.fill_price,
                lot=p.units / self.units_per_lot,
            )

            ct = ClosedTrade(
                trade_id=p.trade_id, audit_id=p.audit_id, pair=p.pair,
                direction=p.direction, units=p.units,
                entry_time=p.entry_time, entry_price=p.entry_price,
                exit_time=fill.fill_time, exit_price=fill.fill_price,
                stop_loss=p.stop_loss, take_profit=p.take_profit,
                expected_rr=p.expected_rr,
                pnl_pips=pip_move, pnl_currency=pnl_currency,
                pnl_pct=(pnl_currency / self.account.initial_balance) * 100.0,
                exit_reason=exit_reason,
                hit_target=hit_target, hit_stop=hit_stop,
                spread_at_entry=p.spread_at_entry,
                slippage_at_entry=p.slippage_at_entry,
                mind_outputs_dict=p.mind_outputs_dict,
                mfe=p.mfe, mae=p.mae,
            )
            self.account.close(ct)
            closed_now.append(ct)
        return closed_now

    def _range_hits(self, p: OpenPosition, bar) -> Tuple[bool, bool]:
        if p.direction == "buy":
            stop_hit = bar.low <= p.stop_loss
            tgt_hit = bar.high >= p.take_profit
        else:
            stop_hit = bar.high >= p.stop_loss
            tgt_hit = bar.low <= p.take_profit
        return stop_hit, tgt_hit
