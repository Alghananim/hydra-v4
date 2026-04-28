"""HYDRA V4 — Master Integration Orchestrator (the spinal cord).

Wires the 5 frozen brains into a single decision cycle. Every public
method on a brain is invoked via its already-validated signature; the
orchestrator does not reach inside any brain.

Brain ordering is LOCKED:

    cycle_id (mint)
      -> validate inputs
      -> news   = NewsMind.evaluate(pair, now_utc)
      -> market = MarketMind.evaluate(pair, bars_by_pair, now_utc, news_output=news)
      -> chart  = ChartMind.evaluate(pair, bars_by_tf, now_utc,
                                     news_output=news, market_output=market)
      -> gate   = GateMind.evaluate(news, market, chart, now_utc, symbol)
      -> DCR    = SmartNoteBook.record_decision_cycle(...)
      -> GAR    = SmartNoteBook.record_gate_audit(decision_cycle_id=DCR.record_id)
      -> DecisionCycleResult

Hard rules (enforced by code AND tests):

  1) NO live orders / NO broker SDK / NO HTTP / NO sockets — verified
     by `test_no_live_order` (static import scan) and by
     `FORBIDDEN_IMPORTS` in orchestrator_constants.py.

  2) The orchestrator NEVER overrides a GateDecision. Whatever
     GateMind returns is the verdict. We map its outcome to our own
     `final_status` 1-to-1; the only override path is when an
     orchestrator-level error prevents GateMind from running at all,
     in which case `final_status` becomes ORCHESTRATOR_ERROR.

  3) Brain BLOCK outputs are NEVER swallowed. Each brain has its own
     fail-CLOSED boundary that returns a BLOCK BrainOutput. We pass
     that BrainOutput downstream UNCHANGED. The only try/except in
     `run_cycle` catches *unexpected non-BrainOutput exceptions* (e.g.
     a TypeError in a brain's __init__, which is NOT supposed to be
     caught by the brain's own .evaluate try/except).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from contracts.brain_output import BrainOutput

from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.models import ChartAssessment
from gatemind.v4.GateMindV4 import GateMindV4
from gatemind.v4.models import GateDecision, GateOutcome
from marketmind.v4.MarketMindV4 import MarketMindV4
from marketmind.v4.models import Bar, MarketState
from newsmind.v4.NewsMindV4 import NewsMindV4
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4

from orchestrator.v4.cycle_id import mint_cycle_id
from orchestrator.v4.decision_cycle_record import DecisionCycleResult
from orchestrator.v4.orchestrator_constants import (
    BRAIN_KEY_CHART,
    BRAIN_KEY_MARKET,
    BRAIN_KEY_NEWS,
    CLOCK_DRIFT_TOLERANCE_MINUTES,
    EVIDENCE_PER_BRAIN_LIMIT,
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_ORCHESTRATOR_ERROR,
    FINAL_WAIT,
    MS_PER_SECOND,
    ORCHESTRATOR_ERROR_PREFIX,
    SESSION_STATUS_UNKNOWN,
    SMARTNOTEBOOK_RECORD_FAILURE_PREFIX,
    T_CHART,
    T_GATE,
    T_MARKET,
    T_NEWS,
    T_NOTEBOOK,
    T_TOTAL,
)
from orchestrator.v4.orchestrator_errors import (
    BarFeedError,
    MissingBrainOutputError,
    OrchestratorError,
)

_log = logging.getLogger("orchestrator.v4")
_NY_TZ = ZoneInfo("America/New_York")


def _gate_outcome_to_final(outcome: GateOutcome) -> str:
    """Map GateMind's verdict 1:1 to orchestrator final_status. We never
    upgrade or downgrade — this IS the obey-GateMind rule.
    """
    if outcome == GateOutcome.ENTER_CANDIDATE:
        return FINAL_ENTER_CANDIDATE
    if outcome == GateOutcome.WAIT:
        return FINAL_WAIT
    if outcome == GateOutcome.BLOCK:
        return FINAL_BLOCK
    # Defensive — should be unreachable because GateOutcome is a closed enum.
    return FINAL_BLOCK


class HydraOrchestratorV4:
    """The spinal cord. ~250 lines, no live order surface."""

    # ------------------------------------------------------------------
    def __init__(
        self,
        smartnotebook_base_dir: Path | str | None = None,
        *,
        newsmind: Optional[NewsMindV4] = None,
        marketmind: Optional[MarketMindV4] = None,
        chartmind: Optional[ChartMindV4] = None,
        gatemind: Optional[GateMindV4] = None,
        smartnotebook: Optional[SmartNoteBookV4] = None,
        strict: bool = False,
    ) -> None:
        """Build an orchestrator.

        Args:
            smartnotebook_base_dir: ledger root if `smartnotebook` is not
                supplied. One of {smartnotebook, smartnotebook_base_dir}
                MUST be set.
            newsmind / marketmind / chartmind / gatemind / smartnotebook:
                Optional pre-built brains. Tests inject mocks here.
            strict: When True, every brain MUST be supplied — no implicit
                construction of real production brains. Use `strict=True`
                in production wiring; mocks may pass `strict=False`. This
                closes Red Team Bonus (silent-real-brain construction).
        """
        # Either pass a notebook OR a base_dir to build one. Refusing both
        # rules out an undocumented "default disk path" surprise.
        if smartnotebook is None and smartnotebook_base_dir is None:
            raise OrchestratorError(
                "either smartnotebook= or smartnotebook_base_dir= required"
            )
        # Fix O9 — strict mode: refuse to silently construct real brains.
        if strict:
            missing = [
                name
                for name, value in (
                    ("newsmind", newsmind),
                    ("marketmind", marketmind),
                    ("chartmind", chartmind),
                    ("gatemind", gatemind),
                    ("smartnotebook", smartnotebook),
                )
                if value is None
            ]
            if missing:
                raise OrchestratorError(
                    "strict=True requires explicit injection of: "
                    + ", ".join(missing)
                )
        self.newsmind: NewsMindV4 = newsmind if newsmind is not None else NewsMindV4()
        self.marketmind: MarketMindV4 = (
            marketmind if marketmind is not None else MarketMindV4()
        )
        self.chartmind: ChartMindV4 = (
            chartmind if chartmind is not None else ChartMindV4()
        )
        self.gatemind: GateMindV4 = (
            gatemind if gatemind is not None else GateMindV4()
        )
        self.smartnotebook: SmartNoteBookV4 = (
            smartnotebook
            if smartnotebook is not None
            else SmartNoteBookV4(smartnotebook_base_dir)  # type: ignore[arg-type]
        )
        # Fix O2 — guard SmartNoteBook + sequence counter from concurrent
        # run_cycle calls. Reentrant so the same thread can lock again
        # if a future helper recurses.
        self._notebook_lock = threading.RLock()

    # ------------------------------------------------------------------
    def run_cycle(
        self,
        symbol: str,
        now_utc: datetime,
        bars_by_pair: Mapping[str, Sequence[Bar]],
        bars_by_tf: Mapping[str, Sequence[Bar]],
    ) -> DecisionCycleResult:
        """Execute one decision cycle and return a frozen
        DecisionCycleResult.

        Raises BarFeedError only for orchestrator-level input problems
        (naive datetime, empty symbol, None mappings). Brain-level
        failures are NEVER raised — they are propagated as BLOCK
        BrainOutput objects and reach DecisionCycleResult unchanged.
        """
        cycle_start = time.perf_counter()

        # 1) Input validation — these are orchestrator's own responsibility,
        #    not a brain's. Raise loudly.
        self._validate_inputs(symbol, now_utc, bars_by_pair, bars_by_tf)
        symbol = symbol.strip()

        # 2) Mint cycle_id (uses orchestrator clock for the prefix)
        cycle_id = mint_cycle_id(now_utc)

        # 3) Run brains in strict order, time each.
        timings: dict = {}
        errors: list = []
        news_out: Optional[BrainOutput] = None
        market_out: Optional[MarketState] = None
        chart_out: Optional[ChartAssessment] = None
        gate_decision: Optional[GateDecision] = None

        try:
            # NewsMind
            t0 = time.perf_counter()
            news_out = self.newsmind.evaluate(symbol, now_utc)
            timings[T_NEWS] = (time.perf_counter() - t0) * MS_PER_SECOND
            if not isinstance(news_out, BrainOutput):
                raise MissingBrainOutputError(
                    f"NewsMind returned non-BrainOutput: {type(news_out).__name__}"
                )

            # MarketMind — receives news_output (per Phase 1 verified contract)
            t0 = time.perf_counter()
            market_out = self.marketmind.evaluate(
                symbol, bars_by_pair, now_utc, news_output=news_out
            )
            timings[T_MARKET] = (time.perf_counter() - t0) * MS_PER_SECOND
            if not isinstance(market_out, BrainOutput):
                raise MissingBrainOutputError(
                    f"MarketMind returned non-BrainOutput: {type(market_out).__name__}"
                )

            # ChartMind — receives news AND market
            t0 = time.perf_counter()
            chart_out = self.chartmind.evaluate(
                symbol,
                bars_by_tf,
                now_utc,
                news_output=news_out,
                market_output=market_out,
            )
            timings[T_CHART] = (time.perf_counter() - t0) * MS_PER_SECOND
            if not isinstance(chart_out, BrainOutput):
                raise MissingBrainOutputError(
                    f"ChartMind returned non-BrainOutput: {type(chart_out).__name__}"
                )

            # GateMind — verdict is FINAL
            t0 = time.perf_counter()
            gate_decision = self.gatemind.evaluate(
                news_out, market_out, chart_out, now_utc, symbol
            )
            timings[T_GATE] = (time.perf_counter() - t0) * MS_PER_SECOND
            if not isinstance(gate_decision, GateDecision):
                raise MissingBrainOutputError(
                    f"GateMind returned non-GateDecision: "
                    f"{type(gate_decision).__name__}"
                )

        except MissingBrainOutputError:
            # A brain returned None or a wrong type — that's an
            # orchestrator-level integrity failure; propagate so that
            # the call site can know the build is broken.
            raise
        except Exception as exc:  # noqa: BLE001
            # Any UNEXPECTED non-BrainOutput exception from a brain
            # constructor / __init__ / out-of-band call. NOTE: each brain's
            # .evaluate() has its own fail-CLOSED that catches and turns
            # into BLOCK BrainOutput, so reaching this branch means the
            # brain failed in a way it explicitly chose not to handle.
            # We record the error, stamp ORCHESTRATOR_ERROR, and still
            # write a SmartNoteBook record.
            _log.exception(
                "orchestrator.run_cycle unexpected exception cycle_id=%s",
                cycle_id,
            )
            errors.append(f"unexpected:{type(exc).__name__}:{exc}")
            return self._record_orchestrator_error(
                cycle_id=cycle_id,
                symbol=symbol,
                now_utc=now_utc,
                news_out=news_out,
                market_out=market_out,
                chart_out=chart_out,
                gate_decision=gate_decision,
                timings=timings,
                errors=errors,
                cycle_start=cycle_start,
                exc=exc,
            )

        # 4) Map GateMind verdict 1:1 to orchestrator final_status.
        #    THIS is where rule #2 (no override) lives.
        final_status = _gate_outcome_to_final(gate_decision.gate_decision)
        if final_status == FINAL_ENTER_CANDIDATE:
            final_reason = gate_decision.approval_reason or "approved"
        elif final_status == FINAL_BLOCK:
            final_reason = gate_decision.blocking_reason or "blocked"
        else:
            # WAIT — provide whatever audit_trail we have
            final_reason = (
                gate_decision.audit_trail[-1]
                if gate_decision.audit_trail
                else "wait"
            )

        # 5) SmartNoteBook records DECISION_CYCLE + GATE_AUDIT.
        #    Fix O1 — wrap in try/except so a SmartNoteBook write failure
        #    (disk-full, chain corruption) does NOT raise out of run_cycle
        #    and lose the cycle. We surface it as a BLOCK with the failure
        #    string in errors + final_reason.
        t0 = time.perf_counter()
        try:
            decision_cycle_record_id, gate_audit_record_id = (
                self._record_to_smartnotebook(
                    symbol=symbol,
                    news_out=news_out,
                    market_out=market_out,
                    chart_out=chart_out,
                    gate_decision=gate_decision,
                    final_status=final_status,
                    final_reason=final_reason,
                    now_utc=now_utc,
                )
            )
        except Exception as rec_exc:  # noqa: BLE001
            _log.warning(
                "smartnotebook record failure on happy path cycle_id=%s "
                "exc=%s:%s",
                cycle_id,
                type(rec_exc).__name__,
                rec_exc,
            )
            timings[T_NOTEBOOK] = (time.perf_counter() - t0) * MS_PER_SECOND
            timings[T_TOTAL] = (
                time.perf_counter() - cycle_start
            ) * MS_PER_SECOND
            failure_marker = (
                f"{SMARTNOTEBOOK_RECORD_FAILURE_PREFIX}"
                f"{type(rec_exc).__name__}:{rec_exc}"
            )
            errors.append(failure_marker)
            block_result = DecisionCycleResult(
                cycle_id=cycle_id,
                symbol=symbol,
                timestamp_utc=now_utc.astimezone(timezone.utc),
                timestamp_ny=now_utc.astimezone(_NY_TZ),
                session_status=(
                    gate_decision.session_status or SESSION_STATUS_UNKNOWN
                ),
                news_output=news_out,
                market_output=market_out,
                chart_output=chart_out,
                gate_decision=gate_decision,
                decision_cycle_record_id="",
                gate_audit_record_id="",
                final_status=FINAL_BLOCK,
                final_reason=failure_marker,
                errors=errors,
                timings_ms=timings,
            )
            _log.info(
                "cycle_complete cycle_id=%s symbol=%s final=%s reason=%s",
                cycle_id,
                symbol,
                block_result.final_status,
                block_result.final_reason,
            )
            return block_result
        timings[T_NOTEBOOK] = (time.perf_counter() - t0) * MS_PER_SECOND
        timings[T_TOTAL] = (time.perf_counter() - cycle_start) * MS_PER_SECOND

        # 6) Assemble result
        result = DecisionCycleResult(
            cycle_id=cycle_id,
            symbol=symbol,
            timestamp_utc=now_utc.astimezone(timezone.utc),
            timestamp_ny=now_utc.astimezone(_NY_TZ),
            session_status=gate_decision.session_status or SESSION_STATUS_UNKNOWN,
            news_output=news_out,
            market_output=market_out,
            chart_output=chart_out,
            gate_decision=gate_decision,
            decision_cycle_record_id=decision_cycle_record_id,
            gate_audit_record_id=gate_audit_record_id,
            final_status=final_status,
            final_reason=final_reason,
            errors=errors,
            timings_ms=timings,
        )
        # Fix O8 — single INFO log at decision boundary (not per brain).
        _log.info(
            "cycle_complete cycle_id=%s symbol=%s final=%s reason=%s",
            cycle_id,
            symbol,
            result.final_status,
            result.final_reason,
        )
        return result

    # ------------------------------------------------------------------
    # input validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_inputs(
        symbol: str,
        now_utc: datetime,
        bars_by_pair: Mapping[str, Sequence[Bar]],
        bars_by_tf: Mapping[str, Sequence[Bar]],
    ) -> None:
        if symbol is None or not isinstance(symbol, str) or not symbol.strip():
            raise BarFeedError(f"symbol must be a non-empty string, got {symbol!r}")
        if not isinstance(now_utc, datetime):
            raise BarFeedError(f"now_utc must be datetime, got {type(now_utc)!r}")
        if now_utc.tzinfo is None:
            raise BarFeedError("now_utc must be tz-aware UTC")
        # Fix O5 — bound now_utc against host wall clock. Allow a small
        # ±tolerance for clock drift; reject anything beyond as a Bar-Feed
        # input error (so we don't poison cycle_id and SmartNoteBook chain).
        wall_now = datetime.now(timezone.utc)
        drift_window = timedelta(minutes=CLOCK_DRIFT_TOLERANCE_MINUTES)
        if now_utc > wall_now + drift_window:
            raise BarFeedError(
                f"now_utc more than {CLOCK_DRIFT_TOLERANCE_MINUTES} minutes "
                f"in the future (now_utc={now_utc.isoformat()}, "
                f"wall={wall_now.isoformat()})"
            )
        if bars_by_pair is None:
            raise BarFeedError("bars_by_pair must not be None")
        if bars_by_tf is None:
            raise BarFeedError("bars_by_tf must not be None")
        if not hasattr(bars_by_pair, "get") or not hasattr(bars_by_pair, "items"):
            raise BarFeedError("bars_by_pair must be a mapping")
        if not hasattr(bars_by_tf, "get") or not hasattr(bars_by_tf, "items"):
            raise BarFeedError("bars_by_tf must be a mapping")

    # ------------------------------------------------------------------
    # smartnotebook recording
    # ------------------------------------------------------------------
    def _record_to_smartnotebook(
        self,
        *,
        symbol: str,
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
        gate_decision: GateDecision,
        final_status: str,
        final_reason: str,
        now_utc: datetime,
    ) -> tuple:
        """Always record DECISION_CYCLE + GATE_AUDIT, even on BLOCK.

        SmartNoteBook is the only sink the orchestrator writes to. The
        body is guarded by a per-orchestrator RLock (Fix O2) so two
        threads calling run_cycle on the same orchestrator instance
        cannot interleave the SmartNoteBook sequence counter / chain.
        """
        # Fix O2 — serialise SmartNoteBook writes per orchestrator
        # instance so the chain hash + sequence counter stay consistent
        # under concurrent run_cycle().
        with self._notebook_lock:
            # DECISION_CYCLE record
            dcr = self.smartnotebook.record_decision_cycle(
                symbol=symbol,
                news_out=news_out,
                market_out=market_out,
                chart_out=chart_out,
                gate_decision=gate_decision,
                final_status=final_status,
                blocking_reason=final_reason if final_status == FINAL_BLOCK else "",
                evidence_summary=self._collect_evidence_summary(
                    news_out, market_out, chart_out
                ),
                risk_flags=self._collect_risk_flags(
                    news_out, market_out, chart_out
                ),
                data_quality_summary=self._collect_data_quality(
                    news_out, market_out, chart_out
                ),
                model_versions={
                    "gatemind": gate_decision.model_version,
                },
                now_utc=now_utc,
            )
            # GATE_AUDIT record — linked to DCR
            gar = self.smartnotebook.record_gate_audit(
                gate_decision=gate_decision,
                decision_cycle_id=dcr.record_id,
                now_utc=now_utc,
            )
            return dcr.record_id, gar.record_id

    # ------------------------------------------------------------------
    @staticmethod
    def _collect_evidence_summary(
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
    ) -> list:
        out: list = []
        for tag, b in (("news", news_out), ("market", market_out), ("chart", chart_out)):
            if b is None:
                continue
            for ev in b.evidence[:EVIDENCE_PER_BRAIN_LIMIT]:
                out.append(f"{tag}:{ev}")
        return out

    @staticmethod
    def _collect_risk_flags(
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
    ) -> list:
        flags: list = []
        for b in (news_out, market_out, chart_out):
            if b is None:
                continue
            flags.extend(b.risk_flags)
        return flags

    @staticmethod
    def _collect_data_quality(
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
    ) -> dict:
        return {
            BRAIN_KEY_NEWS: news_out.data_quality if news_out else "missing",
            BRAIN_KEY_MARKET: market_out.data_quality if market_out else "missing",
            BRAIN_KEY_CHART: chart_out.data_quality if chart_out else "missing",
        }

    # ------------------------------------------------------------------
    # error path — orchestrator-only failure
    # ------------------------------------------------------------------
    def _record_orchestrator_error(
        self,
        *,
        cycle_id: str,
        symbol: str,
        now_utc: datetime,
        news_out: Optional[BrainOutput],
        market_out: Optional[BrainOutput],
        chart_out: Optional[BrainOutput],
        gate_decision: Optional[GateDecision],
        timings: dict,
        errors: list,
        cycle_start: float,
        exc: Exception,
    ) -> DecisionCycleResult:
        """Stamp an ORCHESTRATOR_ERROR result and try to record it.

        Fix O3 — final_status divergence between ledger and DCR:
            SmartNoteBook's DecisionCycleRecord only accepts final_status
            in {ENTER_CANDIDATE, WAIT, BLOCK} (the V4 ledger contract is
            FROZEN — we cannot extend its enum). The orchestrator's own
            DecisionCycleResult stamps the more-specific
            ORCHESTRATOR_ERROR so callers / dashboards can distinguish a
            real BLOCK from an orchestrator-level failure.

            To make the divergence queryable in the ledger, the
            blocking_reason ALWAYS starts with
            ``ORCHESTRATOR_ERROR_PREFIX`` (``orchestrator_error:``).
            Auditors can grep blocking_reason for that prefix to recover
            every ORCHESTRATOR_ERROR cycle even though final_status reads
            BLOCK in DECISION_CYCLE rows.
        """
        dcr_id = ""
        gar_id = ""
        # Prefix is the same string written to ledger blocking_reason and
        # the DCR final_reason, guaranteeing the two stay in sync.
        error_marker = f"{ORCHESTRATOR_ERROR_PREFIX}{type(exc).__name__}"
        try:
            with self._notebook_lock:
                dcr = self.smartnotebook.record_decision_cycle(
                    symbol=symbol,
                    news_out=news_out,
                    market_out=market_out,
                    chart_out=chart_out,
                    gate_decision=gate_decision,
                    final_status=FINAL_BLOCK,
                    blocking_reason=error_marker,
                    evidence_summary=self._collect_evidence_summary(
                        news_out, market_out, chart_out
                    ),
                    risk_flags=["orchestrator_error"]
                    + self._collect_risk_flags(news_out, market_out, chart_out),
                    data_quality_summary=self._collect_data_quality(
                        news_out, market_out, chart_out
                    ),
                    model_versions={},
                    now_utc=now_utc,
                )
                dcr_id = dcr.record_id
                if gate_decision is not None:
                    gar = self.smartnotebook.record_gate_audit(
                        gate_decision=gate_decision,
                        decision_cycle_id=dcr_id,
                        now_utc=now_utc,
                    )
                    gar_id = gar.record_id
        except Exception as rec_exc:  # noqa: BLE001
            _log.exception("orchestrator failed to record error path")
            errors.append(f"record_failure:{type(rec_exc).__name__}:{rec_exc}")

        timings[T_TOTAL] = (time.perf_counter() - cycle_start) * MS_PER_SECOND

        result = DecisionCycleResult(
            cycle_id=cycle_id,
            symbol=symbol,
            timestamp_utc=now_utc.astimezone(timezone.utc),
            timestamp_ny=now_utc.astimezone(_NY_TZ),
            session_status=(
                gate_decision.session_status
                if gate_decision is not None and gate_decision.session_status
                else SESSION_STATUS_UNKNOWN
            ),
            news_output=news_out,
            market_output=market_out,
            chart_output=chart_out,
            gate_decision=gate_decision,
            decision_cycle_record_id=dcr_id,
            gate_audit_record_id=gar_id,
            final_status=FINAL_ORCHESTRATOR_ERROR,
            final_reason=f"{error_marker}:{exc}",
            errors=errors,
            timings_ms=timings,
        )
        # Fix O8 — single INFO log at decision boundary on the error path.
        _log.info(
            "cycle_complete cycle_id=%s symbol=%s final=%s reason=%s",
            cycle_id,
            symbol,
            result.final_status,
            result.final_reason,
        )
        return result
