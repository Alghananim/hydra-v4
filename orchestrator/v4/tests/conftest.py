"""HYDRA V4 — Orchestrator test fixtures.

We provide:
  * tmpdir_storage - a fresh SmartNoteBook base_dir per test
  * make_brain_output - real BrainOutput factories
  * make_market_state / make_chart_assessment - real MarketState / ChartAssessment
  * make_synthetic_bars - Bar list valid for all brains
  * now_in_ny_window / now_outside_ny_window - tz-aware UTC anchors
  * make_real_orchestrator - HydraOrchestratorV4 with real brains
  * make_mock_orchestrator - HydraOrchestratorV4 with mock brains for fast tests

All BrainOutput / MarketState / ChartAssessment objects are constructed
through their REAL frozen contracts — no monkeypatching the post_init.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Ensure project root importable
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from zoneinfo import ZoneInfo

from contracts.brain_output import BrainGrade, BrainOutput

from chartmind.v4.models import ChartAssessment
from gatemind.v4.models import (
    GateDecision,
    GateOutcome,
    TradeCandidate,
    TradeDirection,
)
from marketmind.v4.models import Bar, MarketState
from smartnotebook.v4 import time_integrity
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4

from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def now_in_ny_window(window: int = 1) -> datetime:
    """UTC anchor inside NY window 1 (3-5) or 2 (8-12) — EDT day 2025-07-15."""
    if window == 1:
        ny_local = datetime(2025, 7, 15, 4, 0, 0, tzinfo=NY)
    elif window == 2:
        ny_local = datetime(2025, 7, 15, 10, 0, 0, tzinfo=NY)
    else:
        raise ValueError("window must be 1 or 2")
    return ny_local.astimezone(UTC)


def now_outside_ny_window() -> datetime:
    ny_local = datetime(2025, 7, 15, 6, 30, 0, tzinfo=NY)
    return ny_local.astimezone(UTC)


@pytest.fixture
def in_window_1() -> datetime:
    return now_in_ny_window(1)


@pytest.fixture
def in_window_2() -> datetime:
    return now_in_ny_window(2)


@pytest.fixture
def outside_window() -> datetime:
    return now_outside_ny_window()


# ---------------------------------------------------------------------------
# Storage / SmartNoteBook fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def tmpdir_storage(tmp_path: Path) -> Path:
    time_integrity.reset_sequence_counter(0)
    return tmp_path / "ledger"


@pytest.fixture
def smartnotebook(tmpdir_storage) -> SmartNoteBookV4:
    return SmartNoteBookV4(tmpdir_storage)


# ---------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------
def make_synthetic_bars(
    n: int = 80,
    *,
    start_price: float = 1.1000,
    drift: float = 0.0001,
    base_ts: Optional[datetime] = None,
    minutes: int = 15,
) -> List[Bar]:
    """Synthetic bullish bars suitable for ChartMind/MarketMind smoke runs.

    n=80 ensures ATR/ADX/EMA windows are populated. Anchors at base_ts so
    the LAST bar lands at base_ts + (n-1)*minutes.
    """
    base = base_ts or datetime(2025, 7, 15, 12, 0, tzinfo=UTC)
    bars: List[Bar] = []
    p = start_price
    for i in range(n):
        # gentle uptrend
        nxt = p + drift
        hi = nxt + drift * 0.4
        lo = p - drift * 0.05
        bars.append(
            Bar(
                timestamp=base + timedelta(minutes=minutes * i),
                open=p,
                high=max(hi, nxt, p),
                low=min(lo, p, nxt),
                close=nxt,
                volume=1500.0,
                spread_pips=0.5,
            )
        )
        p = nxt
    return bars


@pytest.fixture
def synthetic_bars_m15() -> List[Bar]:
    return make_synthetic_bars(n=80)


# ---------------------------------------------------------------------------
# BrainOutput factories
# ---------------------------------------------------------------------------
def make_brain_output(
    brain_name: str,
    *,
    decision: str = "BUY",
    grade: BrainGrade = BrainGrade.A_PLUS,
    risk_flags: Optional[List[str]] = None,
    data_quality: str = "good",
    should_block: bool = False,
    confidence: float = 0.9,
    when: Optional[datetime] = None,
    evidence: Optional[List[str]] = None,
) -> BrainOutput:
    """Real frozen-contract BrainOutput. brain_name accepts the full
    'newsmind'/'marketmind'/'chartmind' value."""
    if grade == BrainGrade.BLOCK:
        decision = "BLOCK"
        should_block = True
        data_quality = data_quality if data_quality != "good" else "broken"
    return BrainOutput(
        brain_name=brain_name,
        decision=decision,
        grade=grade,
        reason=f"{brain_name} {grade.value} {decision}",
        evidence=evidence or [f"{brain_name}_evidence_1", f"{brain_name}_evidence_2"],
        data_quality=data_quality,
        should_block=should_block,
        risk_flags=list(risk_flags or []),
        confidence=confidence,
        timestamp_utc=when or datetime.now(UTC),
    )


def make_market_state(
    *,
    decision: str = "BUY",
    grade: BrainGrade = BrainGrade.A_PLUS,
    when: Optional[datetime] = None,
    risk_flags: Optional[List[str]] = None,
    data_quality: str = "good",
    should_block: bool = False,
) -> MarketState:
    """Real MarketState — must satisfy BrainOutput AND MarketState invariants."""
    if grade == BrainGrade.BLOCK:
        decision = "BLOCK"
        should_block = True
        data_quality = "broken" if data_quality == "good" else data_quality
    return MarketState(
        brain_name="marketmind",
        decision=decision,
        grade=grade,
        reason=f"marketmind {grade.value} {decision}",
        evidence=["trend=strong_up hh=4 hl=4", "atr_pct=50"],
        data_quality=data_quality,
        should_block=should_block,
        risk_flags=list(risk_flags or []),
        confidence=0.9,
        timestamp_utc=when or datetime.now(UTC),
        regime_state="trending",
        trend_state="strong_up" if decision == "BUY" else
                    ("strong_down" if decision == "SELL" else "range"),
        momentum_state="accelerating",
        volatility_state="normal",
        liquidity_state="good",
        currency_strength={},
        news_context_used={"present": False},
        contradictions=[],
        indicator_snapshot={},
    )


def make_chart_assessment(
    *,
    decision: str = "BUY",
    grade: BrainGrade = BrainGrade.A_PLUS,
    when: Optional[datetime] = None,
    risk_flags: Optional[List[str]] = None,
    data_quality: str = "good",
    should_block: bool = False,
) -> ChartAssessment:
    """Real ChartAssessment — must satisfy BrainOutput AND C1..C10 invariants."""
    if grade == BrainGrade.BLOCK:
        decision = "BLOCK"
        should_block = True
        data_quality = "broken" if data_quality == "good" else data_quality
    # Build a real BAND for BUY/SELL (C10) — width must be > 0.
    if decision == "BUY":
        entry = {"low": 1.1000, "high": 1.1010}
        invalidation = 1.0980
        target = 1.1050
    elif decision == "SELL":
        entry = {"low": 1.0990, "high": 1.1000}
        invalidation = 1.1020
        target = 1.0950
    else:
        entry = {"low": 1.0995, "high": 1.1005}
        invalidation = 1.0995
        target = None
    return ChartAssessment(
        brain_name="chartmind",
        decision=decision,
        grade=grade,
        reason=f"chartmind {grade.value} {decision}",
        evidence=["trend=bullish_strong", "setup=breakout"],
        data_quality=data_quality,
        should_block=should_block,
        risk_flags=list(risk_flags or []),
        confidence=0.9,
        timestamp_utc=when or datetime.now(UTC),
        trend_structure="bullish_strong",
        volatility_state="normal",
        atr_value=0.0010,
        key_levels=[],
        setup_type="breakout" if decision != "WAIT" else "no_setup",
        entry_zone=entry,
        invalidation_level=invalidation,
        stop_reference=invalidation,
        target_reference=target,
        chart_warnings=[],
        indicator_snapshot={},
        news_context_used=None,
        market_context_used=None,
    )


# ---------------------------------------------------------------------------
# Mock brains (fast — bypass real bar pipelines)
# ---------------------------------------------------------------------------
class MockNewsMind:
    """Returns a pre-built BrainOutput. Emulates NewsMindV4.evaluate signature."""

    def __init__(self, output: BrainOutput, *, record_calls: bool = True):
        self._output = output
        self.calls: List[Dict[str, Any]] = []
        self._record_calls = record_calls

    def evaluate(self, pair: str, now_utc: datetime,
                 current_bar: Optional[Dict[str, Any]] = None) -> BrainOutput:
        if self._record_calls:
            self.calls.append({
                "pair": pair,
                "now_utc": now_utc,
                "current_bar": current_bar,
            })
        # restamp timestamp_utc to now_utc to satisfy any consumer that
        # checks freshness; preserve all other fields.
        return _restamp(self._output, now_utc)


class MockMarketMind:
    def __init__(self, output: MarketState, *, record_calls: bool = True):
        self._output = output
        self.calls: List[Dict[str, Any]] = []
        self._record_calls = record_calls

    def evaluate(self, pair, bars_by_pair, now_utc, news_output=None):
        if self._record_calls:
            self.calls.append({
                "pair": pair,
                "bars_by_pair_keys": list(bars_by_pair.keys()) if bars_by_pair else [],
                "now_utc": now_utc,
                "news_output_passed": news_output is not None,
                "news_output_id": id(news_output) if news_output is not None else None,
            })
        return _restamp_marketstate(self._output, now_utc)


class MockChartMind:
    def __init__(self, output: ChartAssessment, *, record_calls: bool = True):
        self._output = output
        self.calls: List[Dict[str, Any]] = []
        self._record_calls = record_calls

    def evaluate(self, pair, bars_by_tf, now_utc,
                 news_output=None, market_output=None):
        if self._record_calls:
            self.calls.append({
                "pair": pair,
                "bars_by_tf_keys": list(bars_by_tf.keys()) if bars_by_tf else [],
                "now_utc": now_utc,
                "news_output_passed": news_output is not None,
                "market_output_passed": market_output is not None,
                "news_output_id": id(news_output) if news_output is not None else None,
                "market_output_id": id(market_output) if market_output is not None else None,
            })
        return _restamp_chartassessment(self._output, now_utc)


def _restamp(b: BrainOutput, when: datetime) -> BrainOutput:
    return BrainOutput(
        brain_name=b.brain_name,
        decision=b.decision,
        grade=b.grade,
        reason=b.reason,
        evidence=list(b.evidence),
        data_quality=b.data_quality,
        should_block=b.should_block,
        risk_flags=list(b.risk_flags),
        confidence=b.confidence,
        timestamp_utc=when,
    )


def _restamp_marketstate(m: MarketState, when: datetime) -> MarketState:
    return MarketState(
        brain_name=m.brain_name,
        decision=m.decision,
        grade=m.grade,
        reason=m.reason,
        evidence=list(m.evidence),
        data_quality=m.data_quality,
        should_block=m.should_block,
        risk_flags=list(m.risk_flags),
        confidence=m.confidence,
        timestamp_utc=when,
        regime_state=m.regime_state,
        trend_state=m.trend_state,
        momentum_state=m.momentum_state,
        volatility_state=m.volatility_state,
        liquidity_state=m.liquidity_state,
        currency_strength=dict(m.currency_strength),
        news_context_used=dict(m.news_context_used),
        contradictions=list(m.contradictions),
        indicator_snapshot=dict(m.indicator_snapshot),
    )


def _restamp_chartassessment(c: ChartAssessment, when: datetime) -> ChartAssessment:
    return ChartAssessment(
        brain_name=c.brain_name,
        decision=c.decision,
        grade=c.grade,
        reason=c.reason,
        evidence=list(c.evidence),
        data_quality=c.data_quality,
        should_block=c.should_block,
        risk_flags=list(c.risk_flags),
        confidence=c.confidence,
        timestamp_utc=when,
        trend_structure=c.trend_structure,
        volatility_state=c.volatility_state,
        atr_value=c.atr_value,
        key_levels=list(c.key_levels),
        setup_type=c.setup_type,
        entry_zone=dict(c.entry_zone),
        invalidation_level=c.invalidation_level,
        stop_reference=c.stop_reference,
        target_reference=c.target_reference,
        chart_warnings=list(c.chart_warnings),
        indicator_snapshot=dict(c.indicator_snapshot),
        news_context_used=c.news_context_used,
        market_context_used=c.market_context_used,
    )


# ---------------------------------------------------------------------------
# Mock orchestrator builder (NO real brains — fast)
# ---------------------------------------------------------------------------
def make_mock_orchestrator(
    tmp_path: Path,
    *,
    news_out: BrainOutput,
    market_out: MarketState,
    chart_out: ChartAssessment,
) -> tuple:
    """Returns (orchestrator, mock_news, mock_market, mock_chart). Real
    GateMind and SmartNoteBook are used so the whole gate-rule ladder
    and the chain hash are exercised."""
    mock_news = MockNewsMind(news_out)
    mock_market = MockMarketMind(market_out)
    mock_chart = MockChartMind(chart_out)
    nb = SmartNoteBookV4(tmp_path / "ledger")
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=mock_news,
        marketmind=mock_market,
        chartmind=mock_chart,
        smartnotebook=nb,
    )
    return orch, mock_news, mock_market, mock_chart


# ---------------------------------------------------------------------------
# Aggregate factory fixture (used widely)
# ---------------------------------------------------------------------------
@pytest.fixture
def factories():
    return {
        "brain_output": make_brain_output,
        "market_state": make_market_state,
        "chart_assessment": make_chart_assessment,
        "synthetic_bars": make_synthetic_bars,
    }


# ---------------------------------------------------------------------------
# Convenience aliases used directly by tests
# ---------------------------------------------------------------------------
@pytest.fixture
def make_brain_output_fn():
    return make_brain_output


@pytest.fixture
def make_market_state_fn():
    return make_market_state


@pytest.fixture
def make_chart_assessment_fn():
    return make_chart_assessment


@pytest.fixture
def make_synthetic_bars_fn():
    return make_synthetic_bars


@pytest.fixture
def make_mock_orchestrator_fn():
    return make_mock_orchestrator


# ---------------------------------------------------------------------------
# All-A+ BUY happy bundle for integration tests
# ---------------------------------------------------------------------------
@pytest.fixture
def bundle_aplus_buy(in_window_1):
    # GateMind R8 requires all 3 decisions == BUY for unanimous_buy. The
    # production NewsMind never emits BUY (it routes ENTER → WAIT), but
    # for orchestrator-level integration tests we inject a BUY-graded
    # news fixture directly via the mock so we can prove ENTER_CANDIDATE
    # propagates through the orchestrator end-to-end.
    n = make_brain_output("newsmind", decision="BUY", grade=BrainGrade.A_PLUS,
                           when=in_window_1)
    m = make_market_state(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_1)
    c = make_chart_assessment(decision="BUY", grade=BrainGrade.A_PLUS, when=in_window_1)
    return {"news": n, "market": m, "chart": c, "now_utc": in_window_1}


@pytest.fixture
def bars_input(synthetic_bars_m15):
    return {
        "bars_by_pair": {"EUR_USD": synthetic_bars_m15, "EURUSD": synthetic_bars_m15},
        "bars_by_tf": {"M15": synthetic_bars_m15},
    }
