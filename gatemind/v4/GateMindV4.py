"""GateMind V4 — orchestrator.

Public surface:
    GateMindV4().evaluate(news_out, market_out, chart_out, now_utc, symbol)
        -> GateDecision

Hard rules:
  - Stateless. Same inputs → same outputs, always.
  - No broker SDK imports. No state persistence (no daily_loss etc.).
  - Walks the locked rule ladder; first non-PASS wins.
  - On uncaught exception: fail-CLOSED with a synthetic BLOCK GateDecision.

This file is ≤ 150 lines because every interesting decision lives in
rules.py / consensus_check.py / session_check.py / etc.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from contracts.brain_output import BrainOutput

from gatemind.v4 import audit_log
from gatemind.v4.consensus_check import (
    collect_data_quality,
    collect_decisions,
    collect_grades,
)
from gatemind.v4.gatemind_constants import (
    REASON_SCHEMA_INVALID,
    GATE_NAME,
    MODEL_VERSION,
)
from gatemind.v4.models import (
    GateDecision,
    GateOutcome,
    TradeCandidate,
    TradeDirection,
)
from gatemind.v4.rules import RuleContext, _Verdict, evaluate_rules
from gatemind.v4.session_check import session_status, to_ny
from gatemind.v4.trade_candidate_builder import build_trade_candidate

_log = logging.getLogger("gatemind")


class GateMindV4:
    """Stateless orchestrator. Construction takes no arguments."""

    model_version: str = MODEL_VERSION

    def evaluate(
        self,
        news_out: BrainOutput,
        market_out: BrainOutput,
        chart_out: BrainOutput,
        now_utc: datetime,
        symbol: str = "EUR_USD",
    ) -> GateDecision:
        # Make now_utc tz-aware UTC if caller passed naive (defensive — but raise
        # rather than silently coerce: better an explicit error early).
        if now_utc.tzinfo is None:
            return self._fail_closed(
                now_utc=datetime.now(timezone.utc),
                symbol=symbol,
                blocking_reason="naive_now_utc",
                trail=["orchestrator:naive_now_utc"],
            )

        try:
            ctx = RuleContext(
                news=news_out,
                market=market_out,
                chart=chart_out,
                now_utc=now_utc,
                symbol=symbol,
            )
            result = evaluate_rules(ctx)
        except Exception as exc:
            _log.warning(
                "rule_evaluation_failed symbol=%s error_type=%s error=%s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return self._fail_closed(
                now_utc=now_utc,
                symbol=symbol,
                blocking_reason=f"orchestrator_exception:{type(exc).__name__}",
                trail=[f"orchestrator_exception:{type(exc).__name__}:{exc}"],
            )

        # Collect the snapshot fields. If schema check failed (R1), we cannot
        # safely call .decision/.grade on the brain objects — guard accordingly.
        schema_passed = bool(
            ctx.audit_trail and ctx.audit_trail[0].startswith("R1_schema:PASS")
        )
        votes = grades = quality = {}
        if schema_passed:
            try:
                votes = collect_decisions(news_out, market_out, chart_out)
                grades = collect_grades(news_out, market_out, chart_out)
                quality = collect_data_quality(news_out, market_out, chart_out)
            except Exception as exc:
                _log.warning(
                    "consensus_collect_failed symbol=%s error_type=%s error=%s",
                    symbol,
                    type(exc).__name__,
                    exc,
                )
                votes, grades, quality = {}, {}, {}

        # Build outcome
        if result.verdict == _Verdict.ENTER:
            candidate = build_trade_candidate(
                symbol=symbol,
                direction=result.direction,
                news=news_out,
                market=market_out,
                chart=chart_out,
                warning_flags=list(ctx.warning_flags),
                now_utc=now_utc,
            )
            audit_id = audit_log.make_audit_id(now_utc, symbol, news_out, market_out, chart_out)
            decision = GateDecision(
                gate_name=GATE_NAME,
                audit_id=audit_id,
                timestamp_utc=now_utc,
                timestamp_ny=to_ny(now_utc),
                symbol=symbol,
                gate_decision=GateOutcome.ENTER_CANDIDATE,
                direction=result.direction,
                blocking_reason="",
                approval_reason=result.reason,
                mind_votes=votes,
                mind_grades=grades,
                mind_data_quality=quality,
                consensus_status=ctx.consensus_label,
                grade_status=ctx.grade_status,
                session_status=ctx.session_label,
                risk_flag_status=ctx.risk_status or "clean",
                trade_candidate=candidate,
                audit_trail=list(ctx.audit_trail),
            )
        else:
            outcome = GateOutcome.BLOCK if result.verdict == _Verdict.BLOCK else GateOutcome.WAIT
            # Audit id format is consistent across ALL outcomes: gm-...
            # The "fail-closed at schema" path cannot use the content
            # fingerprint (brain objects may not be valid BrainOutputs), so we
            # fall back to a deterministic schema-fail id that still starts
            # with `gm-`. The outcome itself is communicated via .reason, NOT
            # via the id prefix.
            if schema_passed:
                audit_id = audit_log.make_audit_id(
                    now_utc, symbol, news_out, market_out, chart_out
                )
            else:
                audit_id = self._schema_fail_audit_id(now_utc, symbol)
            decision = GateDecision(
                gate_name=GATE_NAME,
                audit_id=audit_id,
                timestamp_utc=now_utc,
                timestamp_ny=to_ny(now_utc),
                symbol=symbol,
                gate_decision=outcome,
                direction=TradeDirection.NONE,
                blocking_reason=result.reason if outcome == GateOutcome.BLOCK else "",
                approval_reason="",
                mind_votes=votes,
                mind_grades=grades,
                mind_data_quality=quality,
                consensus_status=ctx.consensus_label,
                grade_status=ctx.grade_status,
                session_status=ctx.session_label or session_status(now_utc),
                risk_flag_status=ctx.risk_status or "clean",
                trade_candidate=None,
                audit_trail=list(ctx.audit_trail),
            )

        # Record audit snapshot. Audit failure must never poison a decision;
        # the decision itself is the authoritative artefact returned to the
        # caller. We log the failure so it can be triaged, then continue.
        try:
            audit_log.record_audit(
                decision.audit_id,
                now_utc=now_utc,
                symbol=symbol,
                news=news_out,
                market=market_out,
                chart=chart_out,
                decision=decision,
            )
        except Exception as exc:
            _log.warning(
                "audit_record_failed audit_id=%s symbol=%s error_type=%s error=%s",
                decision.audit_id,
                symbol,
                type(exc).__name__,
                exc,
            )

        return decision

    # ------------------------------------------------------------------
    @staticmethod
    def _schema_fail_audit_id(now_utc: datetime, symbol: str) -> str:
        """Deterministic audit_id for schema-fail / fail-closed paths.

        Uses the same `gm-` prefix as the happy path so callers can rely on
        the prefix for ALL GateMind outcomes. The distinguishing signal is
        the decision's `.blocking_reason`, never the audit_id format.
        """
        ts = now_utc.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%f")[:-3]
        return f"gm-{ts}Z-{symbol}-failclosed"

    # ------------------------------------------------------------------
    def _fail_closed(
        self,
        *,
        now_utc: datetime,
        symbol: str,
        blocking_reason: str,
        trail: list,
    ) -> GateDecision:
        return GateDecision(
            gate_name=GATE_NAME,
            audit_id=self._schema_fail_audit_id(now_utc, symbol),
            timestamp_utc=now_utc,
            timestamp_ny=to_ny(now_utc),
            symbol=symbol,
            gate_decision=GateOutcome.BLOCK,
            direction=TradeDirection.NONE,
            blocking_reason=blocking_reason,
            approval_reason="",
            mind_votes={},
            mind_grades={},
            mind_data_quality={},
            consensus_status="",
            grade_status="",
            session_status="",
            risk_flag_status="kill_active",
            trade_candidate=None,
            audit_trail=list(trail),
        )
