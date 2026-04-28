"""ChartMind V4 — orchestrator.

Pipeline:
    1. Validate price data (fail-CLOSED on missing/broken/stale).
    2. Compute ATR / ADX / EMA via shared marketmind.v4.indicators.
    3. Diagnose trend structure on M15.
    4. Detect key levels (clustered swings).
    5. Detect setup (breakout / retest / pullback).
    6. Detect candle confirmation, MTF alignment, liquidity sweep.
    7. Build references (entry_zone BAND, invalidation, target).
    8. Integrate NewsMind+MarketMind upstream verdicts.
    9. Score evidence and grade via additive permission engine.
    10. Emit ChartAssessment.

Single fail-CLOSED boundary at evaluate(); inner pipeline raises freely.
No magic numbers — all from chart_thresholds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional, Sequence

from contracts.brain_output import BrainGrade, BrainOutput

from marketmind.v4 import indicators
from marketmind.v4.models import Bar

from chartmind.v4 import (
    breakout_detector,
    candle_confirmation,
    liquidity_sweep,
    market_structure,
    multi_timeframe,
    news_market_integration,
    permission_engine,
    price_data_validator,
    pullback_detector,
    references as refs_mod,
    retest_detector,
    setups_v2,
    support_resistance,
)
from chartmind.v4.chart_thresholds import (
    ENTRY_BAND_BREAKOUT_ATR,
    EVIDENCE_KEYS,
    VOL_COMPRESSED_PCT_MAX,
    VOL_DANGEROUS_PCT_MIN,
    VOL_EXPANDED_PCT_MIN,
)
from chartmind.v4.models import ChartAssessment, Level


_log = logging.getLogger("chartmind.v4")


class ChartMindV4:
    BRAIN_NAME = "chartmind"

    def evaluate(
        self,
        pair: str,
        bars_by_tf: Mapping[str, Sequence[Bar]],
        now_utc: datetime,
        news_output: Optional[BrainOutput] = None,
        market_output: Optional[BrainOutput] = None,
    ) -> ChartAssessment:
        """Single fail-CLOSED boundary."""
        try:
            return self._evaluate_inner(pair, bars_by_tf, now_utc,
                                        news_output, market_output)
        except Exception as e:  # noqa: BLE001
            _log.exception("ChartMindV4.evaluate fail-CLOSED")
            return _fail_closed(
                reason=f"orchestrator exception: {type(e).__name__}: {e}",
                evidence=[f"exception_type={type(e).__name__}"],
                now_utc=now_utc,
            )

    # ----------------------------------------------------------------- inner

    def _evaluate_inner(self,
                        pair: str,
                        bars_by_tf: Mapping[str, Sequence[Bar]],
                        now_utc: datetime,
                        news_output: Optional[BrainOutput],
                        market_output: Optional[BrainOutput]) -> ChartAssessment:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be tz-aware UTC")

        # 1) Bars
        bars: Sequence[Bar] = (bars_by_tf.get("M15") or bars_by_tf.get("15") or [])
        if not bars:
            return _fail_closed(
                reason=f"no M15 bars for pair {pair!r}",
                evidence=["no_m15_bars"],
                now_utc=now_utc,
            )

        # 2) Data quality
        dq_status, dq_warnings = price_data_validator.assess(bars, now_utc=now_utc)
        if dq_status in ("missing", "broken"):
            return _fail_closed(
                reason=f"price data {dq_status}: {dq_warnings}",
                evidence=[f"dq:{w}" for w in dq_warnings] or [f"dq:{dq_status}"],
                now_utc=now_utc,
                data_quality=dq_status,
            )

        # 3) Indicators (REAL values from shared module — never hardcoded)
        atr_value = indicators.atr(bars)
        adx_value = indicators.adx(bars)
        ema20 = indicators.ema_close(bars)
        atr_pct = indicators.atr_percentile_now(bars)
        if atr_value <= 0:
            return _fail_closed(
                reason="ATR computed as 0; insufficient bar history",
                evidence=[f"bars={len(bars)}"],
                now_utc=now_utc,
                data_quality="missing",
            )

        volatility_state = self._classify_volatility(atr_pct)

        # 4) Trend
        trend = market_structure.diagnose_trend(bars)

        # 5) Key levels
        levels: List[Level] = support_resistance.detect_levels(
            bars, atr_value=atr_value,
        )

        # 6) Setup detection — try in priority: retest > breakout > pullback
        setup_type = "no_setup"
        chart_dir = "none"
        setup_evidence: Dict[str, bool] = {k: False for k in EVIDENCE_KEYS}
        setup_reason: List[str] = []
        chosen_level_price: Optional[float] = None
        breakout_idx: Optional[int] = None

        # Determine candidate side from trend
        trend_dir = (
            "long" if trend.label.startswith("bullish")
            else ("short" if trend.label.startswith("bearish") else "none")
        )

        # Try breakout against most recent same-side level (for trending bars)
        last_close_price = bars[-1].close
        if trend_dir == "long":
            # Resistance below last close = the most-recently broken level
            below = [L for L in levels if L.type == "resistance" and L.price <= last_close_price]
            target_lvl = max(below, key=lambda L: L.price) if below else None
        elif trend_dir == "short":
            above = [L for L in levels if L.type == "support" and L.price >= last_close_price]
            target_lvl = min(above, key=lambda L: L.price) if above else None
        else:
            target_lvl = None

        if target_lvl and trend_dir != "none":
            br = breakout_detector.find_recent_breakout(
                bars, level=target_lvl.price, atr_value=atr_value, side=trend_dir,
            )
            if br.is_breakout and not br.is_fake:
                setup_type = "breakout"
                chart_dir = trend_dir
                chosen_level_price = target_lvl.price
                breakout_idx = br.bar_index
                setup_evidence["real_breakout"] = True
                setup_reason.append(f"breakout@{target_lvl.price:.5f}")
                # Retest check
                rt = retest_detector.detect_retest(
                    bars, breakout_index=breakout_idx,
                    level=target_lvl.price, atr_value=atr_value, side=trend_dir,
                )
                if rt.is_retest:
                    setup_type = "retest"
                    setup_evidence["successful_retest"] = True
                    setup_reason.append(f"retest@{rt.bar_index}")
            elif br.is_breakout and br.is_fake:
                setup_reason.append("fake_breakout_rejected")

        # If no breakout setup, try pullback
        if setup_type == "no_setup" and trend_dir != "none":
            pb = pullback_detector.detect_pullback(
                bars, atr_value=atr_value, trend_label=trend.label,
            )
            if pb.is_pullback:
                setup_type = "pullback_in_trend"
                chart_dir = pb.direction
                setup_reason.append(
                    f"pullback depth_atr={pb.depth_atr:.2f}"
                )

        # V2-W1: 5 additional setup detectors. They populate evidence
        # flags AND, when V5's primary setup is no_setup, become the
        # primary setup themselves so chart_dir lights up.
        v2_levels_prices = [L.price for L in levels]

        ib = setups_v2.detect_inside_bar(
            bars, atr_value=atr_value, trend_label=trend.label,
        )
        if ib.is_setup:
            setup_evidence["inside_bar_breakout"] = True

        rb = setups_v2.detect_range_break(
            bars, atr_value=atr_value, lookback=30,
        )
        if rb.is_setup:
            setup_evidence["range_break"] = True

        mr = setups_v2.detect_mean_reversion(
            bars, atr_value=atr_value,
            levels_prices=v2_levels_prices,
            atr_percentile_now=atr_pct,
        )
        if mr.is_setup:
            setup_evidence["mean_reversion_at_level"] = True

        mt = setups_v2.detect_momentum_thrust(
            bars, atr_value=atr_value, trend_label=trend.label,
        )
        if mt.is_setup:
            setup_evidence["momentum_thrust"] = True

        orb = setups_v2.detect_opening_range_break(
            bars, atr_value=atr_value,
            now_utc_hour=now_utc.hour,
        )
        # ORB is windowed; we expose it through setup_reason but no
        # dedicated evidence flag (would crowd the 13-flag ladder).
        # ORB + any directional V2 setup still gives chart_dir below.

        # If V5 primaries said no_setup, promote the highest-priority
        # V2 setup to primary so chart_dir gets a direction.
        # Priority order (highest first): momentum_thrust, range_break,
        # opening_range_break, inside_bar, mean_reversion (counter-trend
        # last to avoid collisions with strong_trend evidence).
        if setup_type == "no_setup":
            for cand_name, cand in (
                ("momentum_thrust", mt),
                ("range_break", rb),
                ("opening_range_break", orb),
                ("inside_bar_breakout", ib),
                ("mean_reversion_at_level", mr),
            ):
                if cand.is_setup and cand.direction in ("long", "short"):
                    setup_type = cand_name
                    chart_dir = cand.direction
                    setup_reason.append(
                        f"{cand_name}({cand.reason})@idx={cand.bar_index}"
                    )
                    break

        # 7) Evidence flags
        if trend.label in ("bullish_strong", "bearish_strong"):
            setup_evidence["strong_trend"] = True

        # Key-level confluence: any strong (>=3) level near current price (within 1×ATR)
        last_close = bars[-1].close
        for L in levels:
            if L.strength >= 3 and abs(L.price - last_close) <= atr_value:
                setup_evidence["key_level_confluence"] = True
                break

        # In-context candle
        candle_signals = candle_confirmation.detect_in_context_candles(
            bars, atr_value=atr_value,
            levels_prices=[L.price for L in levels],
        )
        if any(c.in_context for c in candle_signals):
            setup_evidence["in_context_candle"] = True

        # MTF alignment
        mtf = multi_timeframe.assess(bars_by_tf)
        if mtf.aligned:
            setup_evidence["mtf_aligned"] = True

        # Volatility normal
        if volatility_state == "normal":
            setup_evidence["volatility_normal"] = True

        # Liquidity sweep (presence = bad => no_liquidity_sweep evidence flips off)
        sweep = liquidity_sweep.detect_recent_sweep(bars, levels)
        if not sweep.has_sweep:
            setup_evidence["no_liquidity_sweep"] = True

        # 8) References (BAND entry, invalidation, target)
        if setup_type == "breakout" and chosen_level_price is not None:
            references = refs_mod.for_breakout(
                bars, atr_value=atr_value, levels=levels, side=chart_dir,
            )
        elif setup_type == "retest" and chosen_level_price is not None:
            references = refs_mod.for_retest(
                bars, atr_value=atr_value, level_price=chosen_level_price,
                levels=levels, side=chart_dir,
            )
        elif setup_type == "pullback_in_trend":
            references = refs_mod.for_pullback(
                bars, atr_value=atr_value, levels=levels, side=chart_dir,
            )
        # V2-W1 setup references — use the breakout-style band (anchored
        # on last close) for trend-continuation patterns, and retest-style
        # (anchored on the touched level) for mean-reversion.
        elif setup_type in ("momentum_thrust", "range_break",
                            "opening_range_break", "inside_bar_breakout"):
            references = refs_mod.for_breakout(
                bars, atr_value=atr_value, levels=levels, side=chart_dir,
            )
        elif setup_type == "mean_reversion_at_level":
            mr_level = mr.bar_index  # not used directly; pick nearest level price
            nearest_level = (
                min(v2_levels_prices, key=lambda p: abs(bars[-1].close - p))
                if v2_levels_prices else float(bars[-1].close)
            )
            references = refs_mod.for_retest(
                bars, atr_value=atr_value, level_price=nearest_level,
                levels=levels, side=chart_dir,
            )
        else:
            # No setup — emit a benign band centered at last close so contract C6
            # is satisfied (we still report the assessment).
            half = ENTRY_BAND_BREAKOUT_ATR * atr_value
            references = refs_mod.References(
                entry_zone={"low": float(last_close - half),
                            "high": float(last_close + half)},
                invalidation_level=float(last_close),
                target_reference=None,
                setup_anchor=float(last_close),
            )

        # 9) Upstream integration
        intg = news_market_integration.integrate(
            news=news_output, market=market_output, chart_direction=chart_dir,
        )
        # V2-W4: surface market_directional_alignment as evidence flag.
        if intg.market_directional_alignment:
            setup_evidence["market_directional_alignment"] = True

        # 10) Permission
        perm = permission_engine.decide(permission_engine.PermissionInputs(
            evidence=setup_evidence,
            data_quality=dq_status,
            direction=chart_dir,
            upstream_block=intg.upstream_block,
            upstream_cap=intg.upstream_cap,
            setup_present=(setup_type != "no_setup"),
        ))

        # 11) Confidence proxy = score / 8 with floor 0
        confidence = float(perm.score) / float(len(EVIDENCE_KEYS))
        confidence = max(0.0, min(1.0, confidence))

        # 12) Evidence list (concrete strings — required for A/A+ by BrainOutput)
        evidence_str: List[str] = [
            f"trend={trend.label} hh={trend.hh_swings} hl={trend.hl_swings} "
            f"lh={trend.lh_swings} ll={trend.ll_swings} ema_slope={trend.ema_slope:.6f} "
            f"adx={trend.adx_value:.2f}",
            f"atr={atr_value:.6f} atr_pct={atr_pct:.1f} vol={volatility_state}",
            f"levels={[L.to_public() for L in levels[:6]]}",
            f"setup={setup_type} dir={chart_dir} reason={setup_reason or 'none'}",
            f"candles={[c.name for c in candle_signals]}",
            f"mtf={mtf.reason} m15={mtf.m15_trend}",
            f"sweep={sweep.has_sweep} dir={sweep.direction}",
            f"score={perm.score}/{len(EVIDENCE_KEYS)} ev={setup_evidence}",
            f"upstream:news={intg.news_snapshot} market={intg.market_snapshot}",
        ]

        risk_flags: List[str] = []
        if dq_status != "good":
            risk_flags.append(f"dq:{dq_status}")
        for w in dq_warnings:
            risk_flags.append(f"dq_w:{w}")
        if sweep.has_sweep:
            risk_flags.append(f"liquidity_sweep:{sweep.direction}")
        if volatility_state == "dangerous":
            risk_flags.append("volatility_dangerous")
        if intg.upstream_block:
            risk_flags.append("upstream_block")
        if intg.upstream_cap is not None:
            risk_flags.append(f"upstream_cap:{intg.upstream_cap.value}")

        reason = perm.reason
        if intg.reason_bits:
            reason = f"{reason}; integration={intg.reason_bits}"

        # 13) BrainOutput contract requires data_quality=='good' for A/A+.
        # Permission engine already caps at B for stale, but if some other
        # path slips by, enforce here.
        final_grade = perm.grade
        if final_grade in (BrainGrade.A, BrainGrade.A_PLUS) and dq_status != "good":
            final_grade = BrainGrade.B

        # If we have BUY/SELL but the references band is degenerate (dx==0),
        # the model invariant C10 will reject construction. Defensive fallback
        # to WAIT in that case so we never fail-CLOSED on a contract bug.
        decision = perm.decision
        if decision in ("BUY", "SELL"):
            ez = references.entry_zone
            if ez["high"] <= ez["low"]:
                decision = "WAIT"
                final_grade = BrainGrade.B if final_grade in (BrainGrade.A, BrainGrade.A_PLUS) else final_grade

        snapshot = {
            "atr": atr_value,
            "adx": adx_value,
            "ema20": ema20,
            "atr_pct": atr_pct,
            "swing_k": market_structure.SWING_K,
            "trend_via": trend.via,
        }

        return ChartAssessment(
            brain_name=self.BRAIN_NAME,
            decision=decision,
            grade=final_grade,
            reason=reason,
            evidence=evidence_str,
            data_quality=dq_status,
            should_block=(decision == "BLOCK"),
            risk_flags=risk_flags,
            confidence=confidence,
            timestamp_utc=now_utc.astimezone(timezone.utc),
            trend_structure=trend.label if trend.label != "none" else "transitioning",
            volatility_state=volatility_state,
            atr_value=float(atr_value),
            key_levels=[L.to_public() for L in levels],
            setup_type=setup_type,
            entry_zone=references.entry_zone,
            invalidation_level=float(references.invalidation_level),
            stop_reference=float(references.invalidation_level),
            target_reference=(float(references.target_reference)
                              if references.target_reference is not None else None),
            chart_warnings=list(dq_warnings),
            indicator_snapshot=snapshot,
            news_context_used=intg.news_snapshot,
            market_context_used=intg.market_snapshot,
        )

    # ------------------------------------------------------------- helpers

    def _classify_volatility(self, atr_pct: float) -> str:
        if atr_pct >= VOL_DANGEROUS_PCT_MIN:
            return "dangerous"
        if atr_pct >= VOL_EXPANDED_PCT_MIN:
            return "expanded"
        if atr_pct <= VOL_COMPRESSED_PCT_MAX:
            return "compressed"
        return "normal"


# ---------------------------------------------------------------------------
# fail-CLOSED constructor
# ---------------------------------------------------------------------------


def _fail_closed(*,
                 reason: str,
                 evidence: List[str],
                 now_utc: datetime,
                 data_quality: str = "broken") -> ChartAssessment:
    return ChartAssessment(
        brain_name="chartmind",
        decision="BLOCK",
        grade=BrainGrade.BLOCK,
        reason=reason,
        evidence=evidence,
        data_quality=data_quality,
        should_block=True,
        risk_flags=["fail_closed"],
        confidence=0.0,
        timestamp_utc=(now_utc.astimezone(timezone.utc)
                       if now_utc.tzinfo else datetime.now(timezone.utc)),
        trend_structure="transitioning",
        volatility_state="unknown",
        atr_value=0.0,
        key_levels=[],
        setup_type="no_setup",
        entry_zone={"low": 0.0, "high": 0.0},
        invalidation_level=0.0,
        stop_reference=0.0,
        target_reference=None,
        chart_warnings=[],
        indicator_snapshot={},
        news_context_used=None,
        market_context_used=None,
    )
