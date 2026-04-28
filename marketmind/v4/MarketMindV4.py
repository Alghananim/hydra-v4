"""MarketMind V4 — orchestrator.

Public surface:
    MarketMindV4().evaluate(pair, bars_by_pair, now_utc, news_output=None)
        -> MarketState

Design:
  - Pure rule-based pipeline. No Claude inside MarketMind.
  - Single fail-CLOSED boundary at evaluate(); inner pipeline raises freely.
  - NewsMind output, when given, is RESPECTED — block forces block,
    warning caps at B.
  - All state fields come from named rules in this package; no black box.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional, Sequence

from contracts.brain_output import BrainOutput, BrainGrade

from marketmind.v4 import (
    contradictions as contradictions_mod,
    correlation as correlation_mod,
    currency_strength as cs_mod,
    data_quality as dq_mod,
    indicators,
    liquidity_rule,
    momentum_rule,
    news_integration,
    permission_engine,
    scoring,
    synthetic_dxy,
    trend_rule,
    volatility_rule,
)
from marketmind.v4.models import Bar, MarketState


_log = logging.getLogger("marketmind.v4")


class MarketMindV4:
    BRAIN_NAME = "marketmind"

    def evaluate(
        self,
        pair: str,
        bars_by_pair: Mapping[str, Sequence[Bar]],
        now_utc: datetime,
        news_output: Optional[BrainOutput] = None,
    ) -> MarketState:
        """Single fail-CLOSED boundary."""
        try:
            return self._evaluate_inner(pair, bars_by_pair, now_utc, news_output)
        except Exception as e:  # noqa: BLE001 — fail-CLOSED boundary
            _log.exception("MarketMindV4.evaluate fail-CLOSED")
            return _fail_closed(
                reason=f"orchestrator exception: {type(e).__name__}: {e}",
                evidence=[f"exception_type={type(e).__name__}"],
                now_utc=now_utc,
                news_output=news_output,
            )

    # -------------------------------------------------------------- internal

    def _evaluate_inner(
        self,
        pair: str,
        bars_by_pair: Mapping[str, Sequence[Bar]],
        now_utc: datetime,
        news_output: Optional[BrainOutput],
    ) -> MarketState:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be tz-aware UTC")

        pair_norm = pair.upper().replace("/", "")
        bars = bars_by_pair.get(pair_norm) or bars_by_pair.get(pair) or []
        if not bars:
            return _fail_closed(
                reason=f"no bars for pair {pair_norm!r}",
                evidence=["no_bars"],
                now_utc=now_utc,
                news_output=news_output,
            )

        # 1. Data quality (fail-CLOSED if broken/missing)
        dq_status, dq_warnings = dq_mod.assess(
            bars=bars, expected_interval_min=15, now_utc=now_utc
        )

        # 2. Rules
        trend_state, trend_ev = trend_rule.evaluate(bars)
        momentum_state, mom_ev = momentum_rule.evaluate(bars)
        volatility_state, vol_ev = volatility_rule.evaluate(bars)
        # Hardening M7: pass now_utc so off-session uses wall-clock not stale bar.
        # Hardening M1: pass pair so the absolute spread ceiling and sticky
        # baseline are keyed correctly per instrument.
        liquidity_state, liq_ev = liquidity_rule.evaluate(
            bars, pair=pair_norm, now_utc=now_utc
        )

        # 3. Cross-asset
        bars_eur = bars_by_pair.get("EURUSD") or bars_by_pair.get("EUR/USD")
        bars_jpy = bars_by_pair.get("USDJPY") or bars_by_pair.get("USD/JPY")
        bars_xau = bars_by_pair.get("XAUUSD") or bars_by_pair.get("XAU/USD") or bars_by_pair.get("GOLD")
        bars_spx = bars_by_pair.get("SPX")    or bars_by_pair.get("SPX500")

        dxy = synthetic_dxy.compute(baskets=bars_by_pair, window=20)
        corr = correlation_mod.assess(
            bars_eurusd=bars_eur,
            bars_usdjpy=bars_jpy,
            bars_xau=bars_xau,
            bars_spx=bars_spx,
        )
        strengths = cs_mod.compute(bars_by_pair, window=20)

        # 4. NewsMind context
        news_ctx = news_integration.map_news_output(news_output)

        # 5. Contradictions
        market_dir = (
            "bullish" if trend_state in ("strong_up", "weak_up")
            else ("bearish" if trend_state in ("strong_down", "weak_down")
                  else "neutral")
        )
        news_bias = "unclear"
        news_perm = "allow"
        if news_ctx.news_state == "block":
            news_perm = "block"
        elif news_ctx.news_state == "warning":
            news_perm = "wait"
        cdet = contradictions_mod.detect(
            bars_eurusd=bars_eur,
            bars_usdjpy=bars_jpy,
            bars_xau=bars_xau,
            bars_spx=bars_spx,
            dxy_dir=dxy.direction,
            dxy_strength=dxy.strength,
            risk_mode="unclear",
            news_bias=news_bias,
            news_perm=news_perm,
            market_direction=market_dir,
        )
        contradiction_severity = (
            "critical" if cdet.critical
            else "high" if cdet.high
            else "medium" if cdet.medium
            else None
        )

        # 6. Permission
        perm_inputs = permission_engine.PermissionInputs(
            trend_state=trend_state,
            momentum_state=momentum_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            correlation_status=corr.status,
            news_state=news_ctx.news_state,
            contradiction_severity=contradiction_severity,
            data_quality=dq_status,
        )
        perm = permission_engine.decide(perm_inputs, news_grade_cap=news_ctx.news_grade_cap)

        # 7. Confidence
        confidence = scoring.compute_confidence(
            perm.grade,
            trend_state=trend_state,
            momentum_state=momentum_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            correlation_status=corr.status,
            news_state=news_ctx.news_state,
            contradiction_severity=contradiction_severity,
            data_quality=dq_status,
        )

        # 8. Evidence (concrete facts)
        evidence: List[str] = [
            f"trend={trend_state} hh={trend_ev.get('hh_count')} hl={trend_ev.get('hl_count')} "
            f"slope_atr={trend_ev.get('slope_ratio')}",
            f"momentum={momentum_state} m_last4={mom_ev.get('m_last4')}",
            f"volatility={volatility_state} atr_pct={vol_ev.get('atr_percentile')}",
            f"liquidity={liquidity_state} flags={liq_ev.get('flags')}",
            f"correlation={corr.status} pairs={dict(corr.pairs)}",
            f"dxy={dxy.direction}@{dxy.strength} coverage={dxy.coverage}",
            f"news_state={news_ctx.news_state} news_cap={news_ctx.news_grade_cap.value if news_ctx.news_grade_cap else None}",
            f"contradictions={cdet.labels()}",
            f"data_quality={dq_status} warnings={dq_warnings}",
        ]
        # If data_quality is not 'good', BrainOutput forbids grade A/A+; permission_engine
        # already caps to B. No extra logic needed here.

        # 9. Reason
        reason = perm.reason
        if news_ctx.news_state == "block":
            news_reason = news_output.reason if news_output else "news_block"
            reason = f"NewsMind block: {news_reason} | {reason}"

        # 10. Indicator snapshot (diagnostic)
        snap: Dict[str, object] = {
            "atr": indicators.atr(bars),
            "adx": indicators.adx(bars),
            "ema20": indicators.ema_close(bars, indicators.EMA_PERIOD),
            "atr_pct": indicators.atr_percentile_now(bars),
            "trend_ev": trend_ev,
            "momentum_ev": mom_ev,
            "volatility_ev": vol_ev,
            "liquidity_ev": liq_ev,
        }

        # 11. risk_flags
        risk_flags: List[str] = []
        if dq_status != "good":
            risk_flags.append(f"data_quality:{dq_status}")
        for w in dq_warnings:
            risk_flags.append(f"dq:{w}")
        for label, sev in cdet.items:
            risk_flags.append(f"contradiction:{sev}:{label}")
        if news_ctx.news_state == "block":
            risk_flags.append("news_block")
        elif news_ctx.news_state == "warning":
            risk_flags.append("news_warning")
        if liquidity_state == "off-session":
            risk_flags.append("off_session")
        if volatility_state == "dangerous":
            risk_flags.append("volatility_dangerous")

        return MarketState(
            brain_name=self.BRAIN_NAME,
            decision=perm.decision,
            grade=perm.grade,
            reason=reason,
            evidence=evidence,
            data_quality=dq_status,
            should_block=perm.should_block,
            risk_flags=risk_flags,
            confidence=confidence,
            timestamp_utc=now_utc.astimezone(timezone.utc),
            regime_state=trend_rule.regime_from_trend(trend_state),
            trend_state=trend_state,
            momentum_state=momentum_state,
            volatility_state=volatility_state,
            liquidity_state=liquidity_state,
            currency_strength=strengths,
            news_context_used=news_ctx.snapshot,
            contradictions=cdet.labels(),
            indicator_snapshot=snap,
        )


# ---------------------------------------------------------------------------
# fail-CLOSED constructor
# ---------------------------------------------------------------------------


def _fail_closed(
    *,
    reason: str,
    evidence: List[str],
    now_utc: datetime,
    news_output: Optional[BrainOutput],
) -> MarketState:
    snap = (
        news_integration.map_news_output(news_output).snapshot
        if news_output is not None
        else {"present": False}
    )
    return MarketState(
        brain_name="marketmind",
        decision="BLOCK",
        grade=BrainGrade.BLOCK,
        reason=reason,
        evidence=evidence,
        data_quality="broken",
        should_block=True,
        risk_flags=["fail_closed"],
        confidence=0.0,
        timestamp_utc=(now_utc.astimezone(timezone.utc)
                       if now_utc.tzinfo else datetime.now(timezone.utc)),
        regime_state="transitioning",
        trend_state="none",
        momentum_state="none",
        volatility_state="unknown",
        liquidity_state="unknown",
        currency_strength={},
        news_context_used=snap,
        contradictions=[],
        indicator_snapshot={},
    )
