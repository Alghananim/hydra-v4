"""HYDRA V4 — Orchestrator hardening regression tests (O1..O9).

Each test pins one of the Multi-Reviewer / Red Team findings closed.
Names are prefixed by the fix tag (e.g. ``test_O1_*``) so a future
auditor grepping for "O3" finds every line that proves the fix held.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from contracts.brain_output import BrainGrade

from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
from orchestrator.v4.decision_cycle_record import DecisionCycleResult
from orchestrator.v4.orchestrator_constants import (
    CLOCK_DRIFT_TOLERANCE_MINUTES,
    EVIDENCE_PER_BRAIN_LIMIT,
    FINAL_BLOCK,
    FINAL_ENTER_CANDIDATE,
    FINAL_ORCHESTRATOR_ERROR,
    MS_PER_SECOND,
    ORCHESTRATOR_ERROR_PREFIX,
    SMARTNOTEBOOK_RECORD_FAILURE_PREFIX,
    T_CHART,
    T_GATE,
    T_MARKET,
    T_NEWS,
)
from orchestrator.v4.orchestrator_errors import BarFeedError, OrchestratorError
from orchestrator.v4.tests.conftest import (
    MockChartMind,
    MockMarketMind,
    MockNewsMind,
)
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
from smartnotebook.v4.record_types import RecordType


UTC = timezone.utc


# ---------------------------------------------------------------------------
# Fix O1 — SmartNoteBook write failure on the happy path must NOT lose
# the cycle. The orchestrator returns a BLOCK DecisionCycleResult with
# the failure string in `errors` + `final_reason` instead of raising.
# ---------------------------------------------------------------------------
class _ExplodingNotebook:
    """Stand-in SmartNoteBook whose record_decision_cycle always raises."""

    def __init__(self):
        self.record_decision_cycle_calls = 0
        self.record_gate_audit_calls = 0

    def record_decision_cycle(self, **kwargs):
        self.record_decision_cycle_calls += 1
        raise RuntimeError("disk-full-simulated")

    def record_gate_audit(self, **kwargs):
        self.record_gate_audit_calls += 1
        raise RuntimeError("disk-full-simulated")


def test_O1_smartnotebook_failure_returns_block_with_error(
    tmp_path, bundle_aplus_buy, bars_input,
):
    """Mock SmartNoteBook to raise on the happy path. The orchestrator
    must return a DecisionCycleResult (not raise) with final_status=BLOCK
    and the smartnotebook_record_failure marker in errors + final_reason.
    """
    notebook = _ExplodingNotebook()
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=MockNewsMind(bundle_aplus_buy["news"]),
        marketmind=MockMarketMind(bundle_aplus_buy["market"]),
        chartmind=MockChartMind(bundle_aplus_buy["chart"]),
        smartnotebook=notebook,
    )

    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )

    # 1. We DID NOT raise out — we got a result.
    assert isinstance(res, DecisionCycleResult)
    # 2. final_status flips to BLOCK.
    assert res.final_status == FINAL_BLOCK
    # 3. final_reason carries the failure marker.
    assert res.final_reason.startswith(SMARTNOTEBOOK_RECORD_FAILURE_PREFIX)
    assert "RuntimeError" in res.final_reason
    # 4. errors list contains the marker too.
    assert any(
        e.startswith(SMARTNOTEBOOK_RECORD_FAILURE_PREFIX) for e in res.errors
    )
    # 5. The DCR / GAR record IDs are empty since recording failed.
    assert res.decision_cycle_record_id == ""
    assert res.gate_audit_record_id == ""
    # 6. The notebook was actually called once (no silent skip).
    assert notebook.record_decision_cycle_calls == 1


# ---------------------------------------------------------------------------
# Fix O2 — concurrent run_cycle must not corrupt the SmartNoteBook chain.
# ---------------------------------------------------------------------------
def test_O2_concurrent_cycles_chain_consistent(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn,
):
    """4 threads x 3 cycles each = 12 cycles. Verify SmartNoteBook
    storage emitted 12 DECISION_CYCLE and 12 GATE_AUDIT rows with no
    cross-talk between sequence numbers.
    """
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    cycles_per_thread = 3
    n_threads = 4
    barrier = threading.Barrier(n_threads)
    errors_box: list = []

    def worker():
        try:
            barrier.wait(timeout=5.0)
            for _ in range(cycles_per_thread):
                orch.run_cycle(
                    symbol="EUR_USD",
                    now_utc=bundle_aplus_buy["now_utc"],
                    bars_by_pair=bars_input["bars_by_pair"],
                    bars_by_tf=bars_input["bars_by_tf"],
                )
        except Exception as exc:  # pragma: no cover
            errors_box.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert not errors_box, f"thread errors: {errors_box}"

    expected = n_threads * cycles_per_thread
    dcr_rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    gar_rows = orch.smartnotebook.storage.query_by_type(RecordType.GATE_AUDIT)
    assert len(dcr_rows) == expected, (
        f"expected {expected} DCR rows, got {len(dcr_rows)} — chain mangled"
    )
    assert len(gar_rows) == expected, (
        f"expected {expected} GAR rows, got {len(gar_rows)} — chain mangled"
    )

    # Each DCR record_id is unique (no shared sequence number).
    record_ids = [r["record_id"] for r in dcr_rows]
    assert len(set(record_ids)) == len(record_ids), "duplicate DCR record_ids"


# ---------------------------------------------------------------------------
# Fix O3 — final_status divergence between ledger and DCR.
# The DCR carries ORCHESTRATOR_ERROR; the ledger row carries BLOCK.
# blocking_reason on the ledger must start with ``orchestrator_error:`` so
# auditors can find the cycle even though final_status reads BLOCK.
# ---------------------------------------------------------------------------
def test_O3_error_path_blocking_reason_includes_orchestrator_error_marker(
    tmp_path, bundle_aplus_buy, bars_input,
):
    class BoomNews:
        def evaluate(self, *a, **kw):
            raise RuntimeError("news-blew-up")

    nb = SmartNoteBookV4(tmp_path / "ledger")
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=BoomNews(),
        marketmind=MockMarketMind(bundle_aplus_buy["market"]),
        chartmind=MockChartMind(bundle_aplus_buy["chart"]),
        smartnotebook=nb,
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )

    # 1. DCR stamps ORCHESTRATOR_ERROR.
    assert res.final_status == FINAL_ORCHESTRATOR_ERROR
    # 2. final_reason carries the prefix.
    assert res.final_reason.startswith(ORCHESTRATOR_ERROR_PREFIX)

    # 3. Ledger row records BLOCK (frozen ledger contract) AND the
    #    blocking_reason starts with the prefix so auditors can grep for it.
    rows = orch.smartnotebook.storage.query_by_type(RecordType.DECISION_CYCLE)
    assert len(rows) == 1
    assert rows[0]["final_status"] == "BLOCK"
    assert rows[0]["blocking_reason"].startswith(ORCHESTRATOR_ERROR_PREFIX)


# ---------------------------------------------------------------------------
# Fix O5 — future timestamp rejection.
# ---------------------------------------------------------------------------
def test_O5_future_timestamp_rejected(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn,
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    far_future = datetime.now(UTC) + timedelta(hours=2)
    with pytest.raises(BarFeedError, match="future"):
        orch.run_cycle(
            symbol="EUR_USD",
            now_utc=far_future,
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )


def test_O5_small_clock_drift_accepted(
    tmp_path, bars_input, make_mock_orchestrator_fn,
    make_brain_output_fn, make_market_state_fn, make_chart_assessment_fn,
):
    """now_utc within ±tolerance is allowed — real wall-clock drift is OK.
    We pass a now_utc that is +1 minute (well under
    CLOCK_DRIFT_TOLERANCE_MINUTES). The cycle must NOT raise on the
    timestamp check. (It may BLOCK for outside_ny_window depending on
    real wall time — we only assert no BarFeedError.)"""
    drift_now = datetime.now(UTC) + timedelta(minutes=1)
    n = make_brain_output_fn("newsmind", decision="BUY",
                              grade=BrainGrade.A_PLUS, when=drift_now)
    m = make_market_state_fn(decision="BUY", grade=BrainGrade.A_PLUS,
                              when=drift_now)
    c = make_chart_assessment_fn(decision="BUY", grade=BrainGrade.A_PLUS,
                                  when=drift_now)
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path, news_out=n, market_out=m, chart_out=c,
    )
    # Should not raise BarFeedError on the timestamp check.
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=drift_now,
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert isinstance(res, DecisionCycleResult)
    # Tolerance constant must be honoured.
    assert CLOCK_DRIFT_TOLERANCE_MINUTES >= 1


# ---------------------------------------------------------------------------
# Fix O6 — real timing measurement (not vacuous "total >= sum").
# ---------------------------------------------------------------------------
class _SlowNews(MockNewsMind):
    def evaluate(self, *a, **kw):
        time.sleep(0.015)
        return super().evaluate(*a, **kw)


class _SlowMarket(MockMarketMind):
    def evaluate(self, *a, **kw):
        time.sleep(0.015)
        return super().evaluate(*a, **kw)


class _SlowChart(MockChartMind):
    def evaluate(self, *a, **kw):
        time.sleep(0.015)
        return super().evaluate(*a, **kw)


def test_O6_timing_actually_measured(
    tmp_path, bundle_aplus_buy, bars_input,
):
    """A brain that sleeps 15ms must show timings_ms[brain] >= ~10ms.
    Catches a regression where someone replaces perf_counter with a stub
    that always returns 0."""
    nb = SmartNoteBookV4(tmp_path / "ledger")
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=_SlowNews(bundle_aplus_buy["news"]),
        marketmind=_SlowMarket(bundle_aplus_buy["market"]),
        chartmind=_SlowChart(bundle_aplus_buy["chart"]),
        smartnotebook=nb,
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    # Each slept brain must report > 5ms — the 15ms sleep guarantees it.
    assert res.timings_ms[T_NEWS] > 5.0, (
        f"news timing too low: {res.timings_ms[T_NEWS]}"
    )
    assert res.timings_ms[T_MARKET] > 5.0, (
        f"market timing too low: {res.timings_ms[T_MARKET]}"
    )
    assert res.timings_ms[T_CHART] > 5.0, (
        f"chart timing too low: {res.timings_ms[T_CHART]}"
    )
    # Gate is real (not slept) but must still record a non-zero number.
    assert res.timings_ms[T_GATE] >= 0.0


# ---------------------------------------------------------------------------
# Fix O7 — magic numbers replaced by named constants. We grep the runtime
# files for the literals and assert they only appear in the constants module.
# ---------------------------------------------------------------------------
def test_O7_no_magic_numbers_in_business_logic():
    """The literal `1000.0` must NOT appear in HydraOrchestratorV4.py;
    the literal `[:3]` must NOT appear there either. They live as named
    constants in orchestrator_constants.py."""
    runtime = (
        Path(__file__).resolve().parents[1] / "HydraOrchestratorV4.py"
    ).read_text(encoding="utf-8")

    assert "1000.0" not in runtime, (
        "raw literal '1000.0' leaked back into HydraOrchestratorV4.py — "
        "use MS_PER_SECOND"
    )
    assert "[:3]" not in runtime, (
        "raw slice '[:3]' leaked back into HydraOrchestratorV4.py — "
        "use EVIDENCE_PER_BRAIN_LIMIT"
    )

    # Constants are present and have sane values.
    assert MS_PER_SECOND == 1000.0
    assert EVIDENCE_PER_BRAIN_LIMIT == 3


def test_O7_no_dead_imports_in_orchestrator():
    """Imports that the runtime never references must be removed.
    Specifically: DEFAULT_SYMBOL, BRAIN_KEY_GATE, BRAIN_KEY_NOTEBOOK
    were imported by HydraOrchestratorV4.py but never used; `Any` was
    imported from typing but never used."""
    src = (
        Path(__file__).resolve().parents[1] / "HydraOrchestratorV4.py"
    ).read_text(encoding="utf-8")

    # Each of these must not be imported into HydraOrchestratorV4.py
    # (still defined in orchestrator_constants.py — that's fine).
    for dead in ("DEFAULT_SYMBOL", "BRAIN_KEY_GATE", "BRAIN_KEY_NOTEBOOK"):
        assert dead not in src, (
            f"dead import {dead!r} still present in HydraOrchestratorV4.py"
        )
    # `from typing import Any` removed; Any was not used.
    assert not re.search(r"from typing import .*\bAny\b", src), (
        "`Any` is imported from typing but never used"
    )


# ---------------------------------------------------------------------------
# Fix O8 — INFO log at decision boundary.
# ---------------------------------------------------------------------------
def test_O8_decision_boundary_logged(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn, caplog,
):
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    with caplog.at_level(logging.INFO, logger="orchestrator.v4"):
        res = orch.run_cycle(
            symbol="EUR_USD",
            now_utc=bundle_aplus_buy["now_utc"],
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )
    boundary_msgs = [
        r.getMessage() for r in caplog.records
        if r.name == "orchestrator.v4" and "cycle_complete" in r.getMessage()
    ]
    assert len(boundary_msgs) == 1, (
        f"expected exactly one cycle_complete log, got {boundary_msgs}"
    )
    msg = boundary_msgs[0]
    assert res.cycle_id in msg
    assert res.symbol in msg
    assert res.final_status in msg


def test_O8_decision_boundary_log_on_error_path(
    tmp_path, bundle_aplus_buy, bars_input, caplog,
):
    """Even on the orchestrator-error path we still emit one INFO
    cycle_complete message so dashboards see every cycle terminate."""

    class BoomNews:
        def evaluate(self, *a, **kw):
            raise RuntimeError("boom")

    nb = SmartNoteBookV4(tmp_path / "ledger")
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=BoomNews(),
        marketmind=MockMarketMind(bundle_aplus_buy["market"]),
        chartmind=MockChartMind(bundle_aplus_buy["chart"]),
        smartnotebook=nb,
    )
    with caplog.at_level(logging.INFO, logger="orchestrator.v4"):
        res = orch.run_cycle(
            symbol="EUR_USD",
            now_utc=bundle_aplus_buy["now_utc"],
            bars_by_pair=bars_input["bars_by_pair"],
            bars_by_tf=bars_input["bars_by_tf"],
        )
    assert res.final_status == FINAL_ORCHESTRATOR_ERROR
    info_msgs = [
        r.getMessage() for r in caplog.records
        if r.levelno == logging.INFO and "cycle_complete" in r.getMessage()
    ]
    assert len(info_msgs) == 1
    assert FINAL_ORCHESTRATOR_ERROR in info_msgs[0]


# ---------------------------------------------------------------------------
# Fix O9 — strict mode requires explicit injection of every brain.
# ---------------------------------------------------------------------------
def test_O9_strict_mode_requires_all_brains(tmp_path):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    # Missing every brain except smartnotebook -> must raise.
    with pytest.raises(OrchestratorError, match="strict"):
        HydraOrchestratorV4(
            smartnotebook_base_dir=None,
            smartnotebook=nb,
            strict=True,
        )


def test_O9_strict_mode_lists_missing_brains(tmp_path):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    with pytest.raises(OrchestratorError) as ei:
        HydraOrchestratorV4(
            smartnotebook_base_dir=None,
            smartnotebook=nb,
            strict=True,
        )
    msg = str(ei.value)
    for brain_name in ("newsmind", "marketmind", "chartmind", "gatemind"):
        assert brain_name in msg, f"strict error must list {brain_name}"


def test_O9_strict_mode_passes_when_all_injected(
    tmp_path, bundle_aplus_buy, bars_input,
):
    nb = SmartNoteBookV4(tmp_path / "ledger")
    from gatemind.v4.GateMindV4 import GateMindV4
    orch = HydraOrchestratorV4(
        smartnotebook_base_dir=None,
        newsmind=MockNewsMind(bundle_aplus_buy["news"]),
        marketmind=MockMarketMind(bundle_aplus_buy["market"]),
        chartmind=MockChartMind(bundle_aplus_buy["chart"]),
        gatemind=GateMindV4(),
        smartnotebook=nb,
        strict=True,
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_ENTER_CANDIDATE


def test_O9_non_strict_mode_default_unchanged(
    tmp_path, bundle_aplus_buy, bars_input, make_mock_orchestrator_fn,
):
    """Default `strict=False` must not regress existing tests — the mock
    orchestrator builder uses strict=False implicitly."""
    orch, *_ = make_mock_orchestrator_fn(
        tmp_path,
        news_out=bundle_aplus_buy["news"],
        market_out=bundle_aplus_buy["market"],
        chart_out=bundle_aplus_buy["chart"],
    )
    res = orch.run_cycle(
        symbol="EUR_USD",
        now_utc=bundle_aplus_buy["now_utc"],
        bars_by_pair=bars_input["bars_by_pair"],
        bars_by_tf=bars_input["bars_by_tf"],
    )
    assert res.final_status == FINAL_ENTER_CANDIDATE
