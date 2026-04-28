# -*- coding: utf-8 -*-
"""EngineV3 - wires NewsMind + MarketMind + ChartMind + GateMind + SmartNoteBook
              under strict Live Validation safety rails.

Single decide_and_maybe_trade() per cycle:
  1. Build NewsMind, MarketMind, ChartMind verdicts
  2. Pass to GateMind for final decision
  3. If gate says enter: optional LLM second-opinion review (downgrade-only)
  4. If still enter: run safety_rails.check_all() - DOUBLE check
  5. If still ok: compute position size from 0.25% risk
  6. Submit order to broker (paper/live)
  7. SmartNoteBook journal: full mind_outputs + decision + trade

If at any step a brain is None / errors / data missing -> block + journal.

Hardening (Phase 1):
  - entry_price + atr passed to GateMind are derived from recent_bars (no
    hardcoded fakes).
  - daily_loss_pct, consecutive_losses, trades_today persist across restarts
    via SmartNoteBook engine_state table.
  - LLM second opinion is consulted on gate=enter; can downgrade only.
"""
from __future__ import annotations
import sys, uuid
from datetime import datetime, timezone
from typing import Optional, Sequence
import os

from newsmind.v3 import NewsMindV3
from marketmind.v3 import MarketMindV3
from chartmind.v3 import ChartMindV3
from gatemind.v3 import GateMindV3, BrainSummary, SystemState
from smartnotebook.v3 import (SmartNoteBookV3, TradeAuditEntry, DecisionEvent,
                               MindOutputs)
from .validation_config import ValidationConfig
from .position_sizer import calculate_position_size
from . import safety_rails
from ._helpers import compute_atr14

# LLM second-opinion is optional; absent / disabled -> skipped silently.
try:
    from llm import review_brain_outputs as _llm_review, LLM_AVAILABLE as _LLM_AVAILABLE
except Exception:
    _llm_review = None
    _LLM_AVAILABLE = False


# State key persisted in SmartNoteBook.engine_state
_STATE_KEY = "engine_state_v1"


def _brain_summary_from_news(nv) -> BrainSummary:
    if nv is None: return BrainSummary("news", "block", "C", 0.0, "unclear", "missing")
    warnings = (getattr(nv, "warnings", None)
                or getattr(nv, "conflicting_sources", None)
                or ())
    return BrainSummary(
        name="news", permission=nv.trade_permission, grade=nv.grade,
        confidence=nv.confidence, direction=nv.market_bias, reason=nv.reason,
        warnings=tuple(warnings))


def _brain_summary_from_market(mv) -> BrainSummary:
    if mv is None: return BrainSummary("market", "block", "C", 0.0, "unclear", "missing")
    return BrainSummary(
        name="market", permission=mv.trade_permission, grade=mv.grade,
        confidence=mv.confidence, direction=mv.direction, reason=mv.reason,
        warnings=tuple(getattr(mv, "warnings", ()) or ()))


def _brain_summary_from_chart(cv) -> BrainSummary:
    if cv is None: return BrainSummary("chart", "block", "C", 0.0, "unclear", "missing")
    return BrainSummary(
        name="chart", permission=cv.trade_permission, grade=cv.grade,
        confidence=cv.confidence, direction=cv.trend_direction, reason=cv.reason,
        warnings=tuple(getattr(cv, "warnings", ()) or ()))


def _build_mind_outputs(nv, mv, cv, gd) -> MindOutputs:
    mo = MindOutputs()
    if nv:
        mo.news_grade = nv.grade; mo.news_perm = nv.trade_permission
        mo.news_confidence = nv.confidence; mo.news_bias = nv.market_bias
        mo.news_freshness = nv.freshness_status
        mo.news_impact_level = nv.impact_level
        mo.news_source_type = nv.source_type
        mo.news_verified = nv.verified
        mo.news_market_bias = nv.market_bias
        mo.news_reason = nv.reason
        mo.news_warnings = tuple()
    if mv:
        mo.market_grade = mv.grade; mo.market_perm = mv.trade_permission
        mo.market_confidence = mv.confidence
        mo.market_regime = mv.market_regime
        mo.market_direction = mv.direction
        mo.market_dollar_bias = mv.dollar_bias
        mo.market_risk_mode = mv.risk_mode
        mo.market_volatility = mv.volatility_level
        mo.market_liquidity = mv.liquidity_condition
        mo.market_spread = mv.spread_condition
        mo.market_reason = mv.reason
        mo.market_warnings = tuple(getattr(mv, "warnings", ()) or ())
    if cv:
        mo.chart_grade = cv.grade; mo.chart_perm = cv.trade_permission
        mo.chart_confidence = cv.confidence
        mo.chart_structure = cv.market_structure
        mo.chart_trend_direction = cv.trend_direction
        mo.chart_candle_context = cv.candlestick_context
        mo.chart_breakout_status = cv.breakout_status
        mo.chart_retest_status = cv.retest_status
        mo.chart_entry_quality = cv.entry_quality
        mo.chart_fake_breakout = cv.fake_breakout_risk
        mo.chart_late_entry = cv.late_entry_risk
        mo.chart_stop_loss = cv.stop_loss
        mo.chart_take_profit = cv.take_profit
        mo.chart_rr = cv.risk_reward
        mo.chart_reason = cv.reason
        mo.chart_warnings = tuple(getattr(cv, "warnings", ()) or ())
    if gd:
        mo.gate_decision = gd.final_decision
        mo.gate_approved = gd.approved
        mo.gate_blocking = gd.blocking_reasons
        mo.gate_warnings = gd.warnings
        mo.gate_audit_id = gd.audit_id
        mo.gate_reason = gd.reason
    return mo


def _mind_outputs_to_dict(mo: MindOutputs, pair: str = "") -> dict:
    """Flatten MindOutputs into the dict the LLM reviewer consumes.

    FIX #1: include ``pair`` so the prompt can render it correctly. Without
    this, the prompt was hardcoded to ``EUR/USD`` and every USD/JPY review
    was hallucinated about the wrong instrument.
    """
    return {
        "pair": pair,
        "news_grade": mo.news_grade, "news_perm": mo.news_perm,
        "news_bias": mo.news_bias, "news_reason": mo.news_reason,
        "market_grade": mo.market_grade, "market_perm": mo.market_perm,
        "market_regime": mo.market_regime, "market_direction": mo.market_direction,
        "market_reason": mo.market_reason,
        "chart_grade": mo.chart_grade, "chart_perm": mo.chart_perm,
        "chart_structure": mo.chart_structure,
        "chart_entry_quality": mo.chart_entry_quality,
        "chart_rr": mo.chart_rr, "chart_reason": mo.chart_reason,
    }


class EngineV3:
    def __init__(self, *, cfg: ValidationConfig, broker=None,
                 account_balance: float = 10000.0,
                 strict_mode: Optional[bool] = None,
                 safety_rails_check_callable=None):
        self.cfg = cfg
        self.broker = broker
        self.account_balance = account_balance
        # FIX #3A: dependency-inject the safety_rails check so backtests can
        # wrap it (e.g. paper -> practice mapping) WITHOUT monkey-patching
        # the module global. Default = production safety_rails.check_all.
        self._safety_rails_check_callable = (
            safety_rails_check_callable or safety_rails.check_all)
        self.nb = SmartNoteBookV3(cfg.smartnotebook_dir, enable_async=True)

        # Strict mode (Phase 2): default ON unless explicitly overridden
        if strict_mode is None:
            strict_mode = getattr(cfg, "strict_mode", None)
            if strict_mode is None:
                from .validation_config import STRICT_MODE_DEFAULT
                strict_mode = STRICT_MODE_DEFAULT
        self.strict_mode = bool(strict_mode)
        self.gate = GateMindV3(strict_mode=self.strict_mode)

        # Stats: load from notebook if persisted (fail-closed across restarts)
        loaded = self.nb.load_engine_state(_STATE_KEY, default=None) or {}
        self.daily_loss_pct = float(loaded.get("daily_loss_pct", 0.0))
        self.consecutive_losses = int(loaded.get("consecutive_losses", 0))
        self.trades_today = int(loaded.get("trades_today", 0))
        # FIX #2A: track last UTC date we reset counters. None => reset on
        # the next decide_and_maybe_trade call (so day-2 starts fresh).
        _lrd = loaded.get("last_reset_date")
        if _lrd:
            try:
                # ISO date string e.g. "2026-04-27"
                self.last_reset_date = datetime.fromisoformat(_lrd).date()
            except Exception:
                self.last_reset_date = None
        else:
            self.last_reset_date = None

    def _persist_state(self):
        """Snapshot RAM counters back to SmartNoteBook so restarts inherit them."""
        try:
            payload = {
                "daily_loss_pct": self.daily_loss_pct,
                "consecutive_losses": self.consecutive_losses,
                "trades_today": self.trades_today,
            }
            # FIX #2A: persist last_reset_date so day-rollover survives restart
            if self.last_reset_date is not None:
                payload["last_reset_date"] = self.last_reset_date.isoformat()
            self.nb.save_engine_state(_STATE_KEY, payload)
        except Exception:
            pass

    def _daily_reset_if_needed(self, now_utc: datetime) -> bool:
        """FIX #2A: zero out daily counters at UTC midnight rollover.

        - Compares now_utc.date() to last_reset_date.
        - If different (or last_reset_date is None on first run), resets
          daily_loss_pct, consecutive_losses, trades_today to 0 and
          persists the new last_reset_date.
        - Returns True iff a reset occurred.

        UTC midnight is the canonical boundary (simpler & DST-safe than NY 17:00).
        """
        # Defensive: ensure we have a UTC date to compare
        if now_utc.tzinfo is None:
            today = now_utc.date()
        else:
            today = now_utc.astimezone(timezone.utc).date()
        if self.last_reset_date == today:
            return False
        self.daily_loss_pct = 0.0
        self.consecutive_losses = 0
        self.trades_today = 0
        self.last_reset_date = today
        self._persist_state()
        return True

    def decide_and_maybe_trade(self, *, pair: str,
                              news_verdict, market_assessment, chart_assessment,
                              recent_bars: Optional[Sequence] = None,
                              spread_pips: float = 0.5,
                              slippage_pips: float = 0.5,
                              now_utc: Optional[datetime] = None) -> dict:
        now = now_utc or datetime.now(timezone.utc)
        # FIX #2A: daily counter rollover at UTC midnight. Must run BEFORE
        # any state-dependent logic so day-2 starts with fresh counters.
        self._daily_reset_if_needed(now)

        # ---------- 1. Compute entry_price + ATR from real bars ----------
        bars = list(recent_bars) if recent_bars else []
        if len(bars) < 14:
            audit_id = str(uuid.uuid4())
            mo = _build_mind_outputs(news_verdict, market_assessment,
                                     chart_assessment, None)
            mo.gate_decision = "block"
            mo.gate_reason = "insufficient_bars_for_atr"
            self.nb.record_decision(DecisionEvent(
                event_id=str(uuid.uuid4()), audit_id=audit_id,
                timestamp=now, event_type="block", pair=pair,
                system_mode=self.cfg.broker_env, mind_outputs=mo,
                gate_decision="block",
                blocking_reasons=("insufficient_bars_for_atr",),
                rejected_reason="insufficient_bars_for_atr"))
            self._persist_state()
            return {"decision": "block",
                    "reason": "insufficient_bars_for_atr",
                    "audit_id": audit_id}

        entry_price_real = bars[-1].close
        atr_real = compute_atr14(bars)
        if atr_real <= 0:
            audit_id = str(uuid.uuid4())
            mo = _build_mind_outputs(news_verdict, market_assessment,
                                     chart_assessment, None)
            mo.gate_decision = "block"
            mo.gate_reason = "atr_invalid"
            self.nb.record_decision(DecisionEvent(
                event_id=str(uuid.uuid4()), audit_id=audit_id,
                timestamp=now, event_type="block", pair=pair,
                system_mode=self.cfg.broker_env, mind_outputs=mo,
                gate_decision="block",
                blocking_reasons=("atr_invalid",),
                rejected_reason="atr_invalid"))
            self._persist_state()
            return {"decision": "block",
                    "reason": "atr_invalid",
                    "audit_id": audit_id}

        # ---------- 2. Build state for GateMind ----------
        state = SystemState(
            pair=pair,
            broker_mode=self.cfg.broker_env,
            live_enabled=(self.cfg.broker_env == "live"),
            spread_pips=spread_pips,
            max_spread_pips=self.cfg.max_spread_pips.get(pair, 2.0),
            expected_slippage_pips=slippage_pips,
            max_slippage_pips=self.cfg.max_slippage_pips,
            daily_loss_pct=self.daily_loss_pct,
            daily_loss_limit_pct=self.cfg.daily_loss_limit_pct,
            trades_today=self.trades_today,
            daily_trade_limit=self.cfg.daily_trade_limit,
            consecutive_losses=self.consecutive_losses,
            consecutive_losses_limit=self.cfg.consecutive_losses_limit,
            pair_status=self.cfg.pair_status.get(pair, "unknown"),
        )

        # ---------- 3. GateMind decision ----------
        news_brain = _brain_summary_from_news(news_verdict)
        market_brain = _brain_summary_from_market(market_assessment)
        chart_brain = _brain_summary_from_chart(chart_assessment)
        gate_decision = self.gate.decide(
            pair=pair,
            news=news_brain, market=market_brain, chart=chart_brain,
            state=state,
            entry_price=entry_price_real,
            stop_loss=getattr(chart_assessment, "stop_loss", None),
            take_profit=getattr(chart_assessment, "take_profit", None),
            atr=atr_real,
            min_confidence=0.6, now_utc=now,
        )

        # ---------- 4. Optional LLM second opinion (downgrade-only) ----------
        llm_review_obj = None
        if (gate_decision.final_decision == "enter"
                and _llm_review is not None and _LLM_AVAILABLE):
            try:
                mo_pre = _build_mind_outputs(news_verdict, market_assessment,
                                              chart_assessment, gate_decision)
                llm_review_obj = _llm_review(
                    _mind_outputs_to_dict(mo_pre, pair=pair),
                    {"final_decision": gate_decision.final_decision,
                     "reason": gate_decision.reason})
                if (llm_review_obj is not None and llm_review_obj.success
                        and llm_review_obj.suggestion in ("block", "downgrade")):
                    if llm_review_obj.suggestion == "block":
                        gate_decision.final_decision = "block"
                        gate_decision.approved = False
                        gate_decision.direction = "none"
                        gate_decision.blocking_reasons = (
                            gate_decision.blocking_reasons +
                            (f"llm_block:{','.join(llm_review_obj.concerns)[:80]}",))
                        gate_decision.reason = (
                            "BLOCK: llm_second_opinion: " +
                            (llm_review_obj.reasoning[:120]
                             or ",".join(llm_review_obj.concerns)))
                    else:    # downgrade -> wait
                        gate_decision.final_decision = "wait"
                        gate_decision.approved = False
                        gate_decision.direction = "none"
                        gate_decision.warnings = (
                            gate_decision.warnings +
                            (f"llm_downgrade:{','.join(llm_review_obj.concerns)[:80]}",))
                        gate_decision.reason = (
                            "WAIT: llm_second_opinion: " +
                            (llm_review_obj.reasoning[:120]
                             or ",".join(llm_review_obj.concerns)))
            except Exception as e:
                gate_decision.warnings = gate_decision.warnings + (
                    f"llm_review_error:{type(e).__name__}",)

        # ---------- 5. Always journal the decision ----------
        mo = _build_mind_outputs(news_verdict, market_assessment,
                                 chart_assessment, gate_decision)
        if llm_review_obj is not None:
            llm_warn = (
                f"llm:success={llm_review_obj.success}"
                f":sev={llm_review_obj.severity}"
                f":sug={llm_review_obj.suggestion}"
                f":conf={llm_review_obj.confidence:.2f}")
            mo.gate_warnings = (mo.gate_warnings or ()) + (llm_warn,)
        event = DecisionEvent(
            event_id=str(uuid.uuid4()),
            audit_id=gate_decision.audit_id,
            timestamp=now,
            event_type="trade" if gate_decision.final_decision == "enter" else gate_decision.final_decision,
            pair=pair, system_mode=self.cfg.broker_env,
            mind_outputs=mo,
            gate_decision=gate_decision.final_decision,
            blocking_reasons=gate_decision.blocking_reasons,
            warnings=gate_decision.warnings,
            rejected_reason=gate_decision.reason if gate_decision.final_decision != "enter" else "",
        )
        self.nb.record_decision(event)

        # ---------- 6. If not enter, persist + stop ----------
        if gate_decision.final_decision != "enter":
            self._persist_state()
            return {"decision": gate_decision.final_decision,
                    "reason": gate_decision.reason,
                    "audit_id": gate_decision.audit_id}

        # ---------- 7. Compute position size from 0.25% risk ----------
        ps = calculate_position_size(
            balance=self.account_balance,
            risk_pct=self.cfg.risk_pct_per_trade,
            entry_price=gate_decision.entry_price,
            stop_loss=gate_decision.stop_loss,
            pair=pair,
        )

        # ---------- 8. SAFETY RAILS - final hard checks ----------
        smartnotebook_writable = (self.nb.storage_health() in ("ok", "warnings"))
        ok, blocks = self._safety_rails_check_callable(
            gate_decision_result=gate_decision,
            position_size=ps,
            cfg=self.cfg,
            account_balance=self.account_balance,
            daily_loss_pct=self.daily_loss_pct,
            consecutive_losses=self.consecutive_losses,
            trades_today=self.trades_today,
            smartnotebook_writable=smartnotebook_writable,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
            pair=pair,
            broker_mode=self.cfg.broker_env,
        )

        if not ok:
            self.nb.record_decision(DecisionEvent(
                event_id=str(uuid.uuid4()),
                audit_id=gate_decision.audit_id,
                timestamp=now, event_type="block", pair=pair,
                system_mode=self.cfg.broker_env, mind_outputs=mo,
                gate_decision="block",
                blocking_reasons=tuple(blocks),
                rejected_reason="safety_rails_blocked: " + " | ".join(blocks[:3])))
            self._persist_state()
            return {"decision": "block_by_safety_rails",
                    "blocking_reasons": blocks,
                    "audit_id": gate_decision.audit_id}

        # ---------- 9. Submit order to broker (no broker = dry run) ----------
        if self.broker is None:
            self._persist_state()
            return {"decision": "enter_dry_run",
                    "would_submit": {"pair": pair,
                                     "direction": gate_decision.direction,
                                     "units": ps.units,
                                     "entry": gate_decision.entry_price,
                                     "stop": gate_decision.stop_loss,
                                     "target": gate_decision.take_profit,
                                     "risk_amount": ps.risk_amount,
                                     "risk_pct_actual": (ps.risk_amount/self.account_balance*100)},
                    "audit_id": gate_decision.audit_id}

        try:
            order_result = self.broker.submit_market_order(
                pair=pair, units=ps.units if gate_decision.direction == "buy" else -ps.units,
                stop_loss=gate_decision.stop_loss,
                take_profit=gate_decision.take_profit)
        except Exception as e:
            self.nb.record_bug(affected_mind="execution", bug_type="broker_submit_failed",
                              severity="high", example_event_id=event.event_id,
                              impact=f"order_not_submitted:{e}")
            self._persist_state()
            return {"decision": "broker_submit_failed", "error": str(e),
                    "audit_id": gate_decision.audit_id}

        # ---------- 10. Journal the trade ----------
        trade = TradeAuditEntry(
            trade_id=order_result.get("trade_id", str(uuid.uuid4())),
            audit_id=gate_decision.audit_id,
            pair=pair, system_mode=self.cfg.broker_env,
            direction=gate_decision.direction,
            entry_time=now,
            entry_price=order_result.get("filled_price", gate_decision.entry_price),
            position_size=ps.units,
            stop_loss=gate_decision.stop_loss,
            take_profit=gate_decision.take_profit,
            expected_rr=gate_decision.risk_reward,
            spread_at_entry=spread_pips,
            slippage_estimate=slippage_pips,
            actual_slippage=order_result.get("slippage", 0.0),
            mind_outputs=mo,
        )
        self.nb.record_trade(trade)
        self.trades_today += 1
        self._persist_state()

        return {"decision": "entered",
                "trade_id": trade.trade_id,
                "audit_id": gate_decision.audit_id,
                "units": ps.units,
                "risk_pct_actual": ps.risk_amount/self.account_balance*100,
                "fills": order_result}

    def update_after_close(self, *, trade_id: str, pnl: float, exit_price: float,
                            exit_reason: str = ""):
        """Update consecutive_losses + daily_loss_pct after a trade closes."""
        if pnl < 0:
            self.consecutive_losses += 1
            self.daily_loss_pct += abs(pnl) / self.account_balance * 100
        else:
            self.consecutive_losses = 0
        self._persist_state()

    def stop(self):
        self._persist_state()
        self.nb.stop()
