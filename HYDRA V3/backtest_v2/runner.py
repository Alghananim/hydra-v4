# -*- coding: utf-8 -*-
"""runner — the bar-by-bar event loop.

Loop schema (lookahead-safe by construction)
--------------------------------------------
    for i in range(WARMUP, N):
        # SIGNAL PHASE — Engine sees bar[0..i] inclusive only
        recent = leak_safe_bars[: i+1]
        chart  = ChartMindV3.assess(recent_m15=recent)
        market = MarketMindV3.assess(baskets={pair: recent}, ...)
        news   = calendar_replay.at(bar_i.time)
        decision = engine.decide_and_maybe_trade(
            pair=cfg.pair,
            news_verdict=news, market_assessment=market,
            chart_assessment=chart, recent_bars=recent,
            now_utc=bar_i.time, ...)

        # FILL PHASE — only if engine said enter
        if decision in ('enter_dry_run', 'entered'):
            next_bar = bars[i+1]
            broker.fill_entry_at_next_open(...)

        # POSITION UPDATE — on the SAME next bar
        if i+1 < N:
            broker.update_open_positions(bar=bars[i+1])
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .account_simulator import AccountSimulator
from .broker_replay import ReplayBroker
from .config import BacktestConfig
from .leak_detector import LeakSafeBars, LookaheadLeakError
from .metrics import compute_report, BacktestReport
from .per_brain_attribution import attribute_per_brain
from .replay_clock import ReplayClock


WARMUP_BARS = 30


class _BacktestNotebookProxy:
    """Wraps SmartNoteBookV3, mutating system_mode -> 'backtest'."""

    def __init__(self, real_nb):
        self._nb = real_nb

    def record_decision(self, e, *, async_=None):
        e.system_mode = "backtest"
        return self._nb.record_decision(e, async_=async_)

    def record_trade(self, t):
        t.system_mode = "backtest"
        return self._nb.record_trade(t)

    def record_bug(self, **kw):
        return self._nb.record_bug(**kw)

    def storage_health(self):
        return self._nb.storage_health()

    def save_engine_state(self, key, value):
        return self._nb.save_engine_state(key, value)

    def load_engine_state(self, key, default=None):
        return self._nb.load_engine_state(key, default=default)

    def stop(self):
        return self._nb.stop()

    def __getattr__(self, item):
        return getattr(self._nb, item)


@dataclass
class RunOutcome:
    config: BacktestConfig
    report: BacktestReport
    decisions: list = field(default_factory=list)
    closed_trades: list = field(default_factory=list)
    leak_events: list = field(default_factory=list)


class BacktestRunner:
    def __init__(self, *, cfg: BacktestConfig, bars: List,
                 calendar_replay, companion_bars: Optional[List] = None,
                 logger=None):
        self.cfg = cfg
        self.cfg.stamp_run_id()
        self._bars = list(bars)
        self._companion = list(companion_bars or [])
        self._calendar = calendar_replay
        self._log = logger or _stdout_logger()
        self._account = AccountSimulator(
            initial_balance=cfg.initial_balance,
            pair_pip=cfg.pair_pip)
        self._broker = ReplayBroker(
            account=self._account, pair=cfg.pair,
            pair_pip=cfg.pair_pip,
            entry_slippage_pips=cfg.entry_slippage_pips,
            stop_slippage_pips=cfg.stop_slippage_pips,
            target_slippage_pips=cfg.target_slippage_pips,
            fallback_spread_pips=cfg.fallback_spread_pips,
            commission_per_lot_per_side=cfg.commission_per_lot_per_side,
            pip_value_per_lot=cfg.pip_value_per_lot,
            units_per_lot=cfg.units_per_lot,
        )
        self._engine = self._build_engine()
        self._chart = self._build_chartmind()
        self._market = self._build_marketmind()

        self._decisions: list = []
        self._leaks: list = []

    @classmethod
    def from_config(cls, cfg: BacktestConfig, *, logger=None
                    ) -> "BacktestRunner":
        from .data_provider import OandaDataProvider
        from .cross_asset_provider import CrossAssetProvider
        from .calendar_provider import CalendarReplay

        log = logger or _stdout_logger()
        log("info", f"backtest_v2: loading bars for {cfg.pair} "
                    f"{cfg.start_utc} .. {cfg.end_utc}")

        prov = OandaDataProvider(cache_dir=cfg.cache_dir, pair=cfg.pair,
                                  granularity=cfg.granularity)
        bars = prov.load_bars(start=cfg.start_utc, end=cfg.end_utc)
        log("info", f"backtest_v2: {len(bars)} bars loaded")

        cross = CrossAssetProvider(cache_dir=cfg.cache_dir,
                                    primary_pair=cfg.pair)
        comp = cross.load_companion(start=cfg.start_utc, end=cfg.end_utc)
        if comp:
            log("info", f"backtest_v2: companion bars {len(comp)} loaded")

        cal = CalendarReplay(start=cfg.start_utc, end=cfg.end_utc,
                              pair=cfg.pair)
        return cls(cfg=cfg, bars=bars, calendar_replay=cal,
                   companion_bars=comp, logger=log)

    def _build_engine(self):
        from engine.v3 import EngineV3, ValidationConfig    # type: ignore
        from engine.v3 import safety_rails as _sr           # type: ignore

        # Background: validation_config.validate_or_die and
        # safety_rails.check_all historically only accepted
        # ("practice","live"); GateMind.execution_check expects
        # ("paper","live","sandbox"). To run a backtest without changing
        # production semantics, we:
        #   1) Validate with broker_env="practice".
        #   2) Swap to "paper" so GateMind's execution_check passes.
        #   3) FIX #3A: dependency-inject a process-LOCAL safety_rails
        #      wrapper into this Engine instance ONLY (no module mutation),
        #      so a live engine created later in the same process is not
        #      affected.
        vc = ValidationConfig()
        vc.broker_env = "practice"
        vc.smartnotebook_dir = str(self.cfg.smartnotebook_dir)
        vc.risk_pct_per_trade = self.cfg.risk_pct_per_trade * 100.0
        if self.cfg.pair in vc.pair_status:
            if vc.pair_status[self.cfg.pair] == "disabled":
                vc.pair_status[self.cfg.pair] = "monitoring"
        else:
            vc.pair_status[self.cfg.pair] = "monitoring"
        vc.validate_or_die()
        vc.broker_env = "paper"   # for GateMind execution_check

        # Local wrapper: paper -> practice mapping for the production
        # safety_rails.check_all. Captures the function reference at this
        # point in time; does NOT mutate the module.
        _orig_check_all = _sr.check_all

        def _paper_safety_rails(**kw):
            if kw.get("broker_mode") == "paper":
                kw = dict(kw); kw["broker_mode"] = "practice"
            return _orig_check_all(**kw)

        eng = EngineV3(cfg=vc, broker=None,
                       account_balance=self.cfg.initial_balance,
                       strict_mode=self.cfg.strict_mode,
                       safety_rails_check_callable=_paper_safety_rails)
        eng.nb = _BacktestNotebookProxy(eng.nb)
        return eng

    def _build_chartmind(self):
        from chartmind.v3 import ChartMindV3   # type: ignore
        return ChartMindV3()

    def _build_marketmind(self):
        from marketmind.v3 import MarketMindV3 # type: ignore
        return MarketMindV3()

    def run(self) -> RunOutcome:
        bars = self._bars
        if len(bars) <= WARMUP_BARS:
            self._log("warn", f"only {len(bars)} bars - need > {WARMUP_BARS}")
            report = compute_report(
                run_id=self.cfg.run_id, label=self.cfg.label,
                pair=self.cfg.pair, strict_mode=self.cfg.strict_mode,
                initial_balance=self.cfg.initial_balance,
                final_balance=self._account.balance,
                bar_count=len(bars), decisions=[], closed_trades=[],
                max_drawdown_pct=0.0)
            return RunOutcome(config=self.cfg, report=report,
                              decisions=[], closed_trades=[])

        self._log("info", f"backtest_v2 RUN start: {self.cfg.run_id} "
                          f"strict={self.cfg.strict_mode} bars={len(bars)}")

        leak_safe = LeakSafeBars(bars, cursor=WARMUP_BARS - 1,
                                  pair=self.cfg.pair)
        clock = ReplayClock(total_bars=len(bars), cursor=WARMUP_BARS - 1)

        cap = self.cfg.max_bars or len(bars)
        last_i = min(len(bars) - 1, cap - 1)

        for i in range(WARMUP_BARS, last_i + 1):
            bar_t = bars[i]
            leak_safe.set_cursor(i)
            clock.cursor = i

            try:
                visible = leak_safe.visible()
            except LookaheadLeakError as e:
                self._leaks.append(str(e))
                if self.cfg.fail_fast_on_leak:
                    raise
                continue

            decision = self._signal_phase(bar_t=bar_t, visible_bars=visible)

            kind = decision.get("decision", "")
            if kind in ("enter_dry_run", "entered") and i + 1 < len(bars):
                next_bar = bars[i + 1]
                self._open_at_next_bar(decision=decision,
                                        signal_bar=bar_t,
                                        next_bar=next_bar)

            if i + 1 < len(bars):
                next_bar = bars[i + 1]
                closed = self._broker.update_open_positions(bar=next_bar)
                for ct in closed:
                    self._engine.update_after_close(
                        trade_id=ct.trade_id, pnl=ct.pnl_currency,
                        exit_price=ct.exit_price, exit_reason=ct.exit_reason)
                mid = (next_bar.high + next_bar.low) / 2.0
                self._account.mark_to_market(next_bar.time, mid)

        if self._account.has_open():
            self._flatten_open_positions(last_bar=bars[last_i])

        try:
            self._engine.stop()
        except Exception:
            pass

        report = compute_report(
            run_id=self.cfg.run_id, label=self.cfg.label,
            pair=self.cfg.pair, strict_mode=self.cfg.strict_mode,
            initial_balance=self.cfg.initial_balance,
            final_balance=self._account.balance,
            bar_count=len(bars),
            decisions=self._decisions,
            closed_trades=self._account.closed_trades,
            max_drawdown_pct=self._account.max_drawdown_pct,
            pip_value_per_lot=self.cfg.pip_value_per_lot,
            units_per_lot=self.cfg.units_per_lot,
        )
        report.brain_accuracy = attribute_per_brain(self._account.closed_trades)

        try:
            self.cfg.output_dir.mkdir(parents=True, exist_ok=True)
            (self.cfg.output_dir / f"{self.cfg.run_id}.json").write_text(
                report.to_json(), encoding="utf-8")
        except Exception as e:
            self._log("warn", f"could not write report json: {e}")

        self._log("info", f"backtest_v2 RUN end: {self.cfg.run_id} "
                          f"trades={report.closed_trades} "
                          f"WR={report.win_rate*100:.1f}% "
                          f"PF={report.profit_factor:.2f} "
                          f"net={report.net_pnl_pct:.2f}% "
                          f"DD={report.max_drawdown_pct:.2f}%")

        return RunOutcome(config=self.cfg, report=report,
                          decisions=list(self._decisions),
                          closed_trades=list(self._account.closed_trades),
                          leak_events=list(self._leaks))

    def _signal_phase(self, *, bar_t, visible_bars) -> dict:
        now = bar_t.time
        try:
            news_verdict = self._calendar.at(now)
        except Exception as e:
            news_verdict = None
            self._log("warn", f"calendar.at failed: {e}")

        try:
            chart_assess = self._chart.assess(
                pair=self.cfg.pair,
                bars_m15=visible_bars, bars_m5=None, bars_m1=None,
                now_utc=now)
        except Exception as e:
            self._log("warn", f"chart.assess failed: {e}")
            chart_assess = None

        try:
            companion_visible = []
            if self._companion:
                companion_visible = [b for b in self._companion
                                      if b.time <= now]
            baskets = {self.cfg.pair: visible_bars}
            if companion_visible:
                comp_pair = "USD/JPY" if self.cfg.pair != "USD/JPY" else "EUR/USD"
                baskets[comp_pair] = companion_visible
            market_assess = self._market.assess(
                pair=self.cfg.pair, baskets=baskets,
                bars_xau=None, bars_spx=None,
                news_verdict=news_verdict, now_utc=now)
        except Exception as e:
            self._log("warn", f"market.assess failed: {e}")
            market_assess = None

        spread = float(getattr(bar_t, "spread_pips", self.cfg.fallback_spread_pips))
        try:
            decision = self._engine.decide_and_maybe_trade(
                pair=self.cfg.pair,
                news_verdict=news_verdict,
                market_assessment=market_assess,
                chart_assessment=chart_assess,
                recent_bars=visible_bars,
                spread_pips=spread,
                slippage_pips=self.cfg.entry_slippage_pips,
                now_utc=now,
            )
        except Exception as e:
            decision = {"decision": "engine_error", "error": str(e),
                         "audit_id": str(uuid.uuid4())}
            self._log("warn", f"engine error at {now}: {e}")

        d_meta = {
            "time": now.isoformat() if hasattr(now, "isoformat") else str(now),
            "decision_kind": decision.get("decision", "unknown"),
            "rejected_reason": decision.get("reason", "")
                                or " ".join(decision.get("blocking_reasons", []) or ()),
            "audit_id": decision.get("audit_id", ""),
            "news_grade": getattr(news_verdict, "grade", "?") if news_verdict else "?",
            "market_grade": getattr(market_assess, "grade", "?") if market_assess else "?",
            "chart_grade": getattr(chart_assess, "grade", "?") if chart_assess else "?",
        }
        if d_meta["decision_kind"] in ("enter_dry_run", "entered"):
            ws = decision.get("would_submit") or {}
            d_meta["plan"] = ws
            d_meta["chart_assess"] = chart_assess
            d_meta["market_assess"] = market_assess
            d_meta["news_verdict"] = news_verdict
        self._decisions.append(d_meta)
        return decision

    def _open_at_next_bar(self, *, decision: dict, signal_bar, next_bar):
        ws = decision.get("would_submit", {}) or {}
        direction = ws.get("direction", "buy")
        units = float(ws.get("units", 0.0))
        sl = float(ws.get("stop") or 0.0)
        tp = float(ws.get("target") or 0.0)
        if units <= 0 or sl <= 0 or tp <= 0:
            return
        meta = self._decisions[-1] if self._decisions else {}
        ca = meta.get("chart_assess")
        ma = meta.get("market_assess")
        nv = meta.get("news_verdict")
        mind_dict = {
            "news_grade": getattr(nv, "grade", "?") if nv else "?",
            "news_bias":  getattr(nv, "market_bias", "?") if nv else "?",
            "market_grade": getattr(ma, "grade", "?") if ma else "?",
            "market_direction": getattr(ma, "direction", "?") if ma else "?",
            "chart_grade": getattr(ca, "grade", "?") if ca else "?",
            "chart_trend_direction": getattr(ca, "trend_direction", "?") if ca else "?",
        }
        self._broker.fill_entry_at_next_open(
            signal_bar=signal_bar, next_bar=next_bar,
            direction=direction, units=units,
            stop_loss=sl, take_profit=tp,
            expected_rr=ws.get("risk_pct_actual", 0.0),
            mind_outputs_dict=mind_dict,
            audit_id=decision.get("audit_id"),
        )

    def _flatten_open_positions(self, *, last_bar):
        from .account_simulator import ClosedTrade
        for p in list(self._account.open_positions):
            exit_price = last_bar.close
            if p.direction == "buy":
                pip_move = (exit_price - p.entry_price) / self.cfg.pair_pip
            else:
                pip_move = (p.entry_price - exit_price) / self.cfg.pair_pip
            pnl_currency = pip_move * (p.units / self.cfg.units_per_lot) \
                            * self.cfg.pip_value_per_lot
            ct = ClosedTrade(
                trade_id=p.trade_id, audit_id=p.audit_id, pair=p.pair,
                direction=p.direction, units=p.units,
                entry_time=p.entry_time, entry_price=p.entry_price,
                exit_time=last_bar.time, exit_price=exit_price,
                stop_loss=p.stop_loss, take_profit=p.take_profit,
                expected_rr=p.expected_rr,
                pnl_pips=pip_move, pnl_currency=pnl_currency,
                pnl_pct=(pnl_currency / self._account.initial_balance) * 100.0,
                exit_reason="time", hit_target=False, hit_stop=False,
                spread_at_entry=p.spread_at_entry,
                slippage_at_entry=p.slippage_at_entry,
                mind_outputs_dict=p.mind_outputs_dict,
                mfe=p.mfe, mae=p.mae,
            )
            self._account.close(ct)


def _stdout_logger():
    def _log(level: str, msg: str):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{ts}][{level.upper():4s}] {msg}")
    return _log
