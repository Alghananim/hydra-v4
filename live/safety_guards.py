"""HYDRA V4.9 — 16-condition safety gate for controlled live execution.

Every single condition must return True before any order can be placed.
A single False or exception is treated as an abort: NO order is placed,
the cycle is logged with the failing condition, and the run continues
in dry-run mode.

The conditions intentionally overlap with LIVE_ORDER_GUARD's existing
6 layers in the orchestrator. Defence in depth: even if one layer is
mis-configured, the others stop a bad order.

This module is PURE LOGIC. It does NOT place orders. It returns a
verdict object. The caller is responsible for honouring the verdict.
"""
from __future__ import annotations

import os
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GuardResult:
    name: str
    passed: bool
    detail: str = ""

    def __bool__(self) -> bool:
        return self.passed


@dataclass
class GuardVerdict:
    cleared: bool
    reasons: List[GuardResult] = field(default_factory=list)
    failing: List[str] = field(default_factory=list)

    @classmethod
    def from_results(cls, results: List[GuardResult]) -> "GuardVerdict":
        failing = [r.name for r in results if not r.passed]
        return cls(cleared=not failing, reasons=results, failing=failing)


# ---------------------------------------------------------------------------
# Individual guards
# ---------------------------------------------------------------------------

def g01_three_brains_directional(news, market, chart) -> GuardResult:
    """News+Market non-opposing AND Chart directional (V4.7 contract)."""
    if chart.decision not in ("BUY", "SELL"):
        return GuardResult("G01_three_brains_directional", False,
                            f"chart.decision={chart.decision}")
    opposing = "SELL" if chart.decision == "BUY" else "BUY"
    if news.decision == opposing or market.decision == opposing:
        return GuardResult("G01_three_brains_directional", False,
                            "news or market opposing")
    return GuardResult("G01_three_brains_directional", True)


def g02_gate_decision_enter(gate_decision) -> GuardResult:
    """GateMind must have emitted ENTER_CANDIDATE."""
    if gate_decision is None:
        return GuardResult("G02_gate_decision_enter", False,
                            "gate_decision missing")
    val = getattr(gate_decision, "gate_decision", None)
    val_str = getattr(val, "value", str(val))
    if val_str != "ENTER_CANDIDATE":
        return GuardResult("G02_gate_decision_enter", False,
                            f"gate_decision={val_str}")
    return GuardResult("G02_gate_decision_enter", True)


def g03_all_grades_a_or_better(news, market, chart) -> GuardResult:
    for b in (news, market, chart):
        g = b.grade.value if hasattr(b.grade, "value") else str(b.grade)
        if g not in ("A", "A+"):
            return GuardResult("G03_all_grades_a_or_better", False,
                                f"{b.brain_name}={g}")
    return GuardResult("G03_all_grades_a_or_better", True)


def g04_no_grade_b(news, market, chart) -> GuardResult:
    for b in (news, market, chart):
        g = b.grade.value if hasattr(b.grade, "value") else str(b.grade)
        if g == "B":
            return GuardResult("G04_no_grade_b", False, f"{b.brain_name}=B")
    return GuardResult("G04_no_grade_b", True)


def g05_no_should_block(news, market, chart) -> GuardResult:
    for b in (news, market, chart):
        if getattr(b, "should_block", False):
            return GuardResult("G05_no_should_block", False,
                                f"{b.brain_name}.should_block=True")
    return GuardResult("G05_no_should_block", True)


def g06_no_data_quality_issue(news, market, chart) -> GuardResult:
    for b in (news, market, chart):
        dq = getattr(b, "data_quality", "good")
        if dq not in ("good", None):
            return GuardResult("G06_no_data_quality_issue", False,
                                f"{b.brain_name}.dq={dq}")
    return GuardResult("G06_no_data_quality_issue", True)


def g07_inside_ny_window(now_utc: dt.datetime,
                          windows_utc: Tuple[Tuple[int, int], ...] =
                          ((3, 5), (8, 12))) -> GuardResult:
    h = now_utc.astimezone(dt.timezone.utc).hour
    for lo, hi in windows_utc:
        if lo <= h < hi:
            return GuardResult("G07_inside_ny_window", True)
    return GuardResult("G07_inside_ny_window", False, f"hour_utc={h}")


def g08_spread_acceptable(spread_pips: float,
                            max_spread_pips: float = 2.5) -> GuardResult:
    if spread_pips is None:
        return GuardResult("G08_spread_acceptable", False, "spread missing")
    if spread_pips > max_spread_pips:
        return GuardResult("G08_spread_acceptable", False,
                            f"spread={spread_pips:.1f}p > {max_spread_pips}p")
    return GuardResult("G08_spread_acceptable", True)


def g09_data_fresh(last_bar_utc: dt.datetime, now_utc: dt.datetime,
                    bar_interval_sec: int = 900,
                    max_lag_factor: float = 1.5) -> GuardResult:
    if last_bar_utc is None:
        return GuardResult("G09_data_fresh", False, "no last_bar_utc")
    lag = (now_utc - last_bar_utc).total_seconds()
    if lag > bar_interval_sec * max_lag_factor:
        return GuardResult("G09_data_fresh", False,
                            f"lag={lag:.0f}s > {bar_interval_sec * max_lag_factor:.0f}s")
    return GuardResult("G09_data_fresh", True)


def g10_risk_size_micro(risk_pct_of_equity: float) -> GuardResult:
    """Hard cap: 0.25 % of equity per trade in V4.9 controlled phase."""
    cap = 0.25
    if risk_pct_of_equity is None or risk_pct_of_equity <= 0:
        return GuardResult("G10_risk_size_micro", False,
                            f"risk_pct={risk_pct_of_equity}")
    if risk_pct_of_equity > cap:
        return GuardResult("G10_risk_size_micro", False,
                            f"risk_pct={risk_pct_of_equity:.3f} > {cap}")
    return GuardResult("G10_risk_size_micro", True)


def g11_sl_present(trade_candidate) -> GuardResult:
    sl = getattr(trade_candidate, "stop_loss", None) if trade_candidate else None
    if sl is None or sl <= 0:
        return GuardResult("G11_sl_present", False, f"sl={sl}")
    return GuardResult("G11_sl_present", True)


def g12_tp_or_exit_logic(trade_candidate) -> GuardResult:
    tp = getattr(trade_candidate, "take_profit", None) if trade_candidate else None
    exit_logic = getattr(trade_candidate, "exit_logic", None) if trade_candidate else None
    if (tp is None or tp <= 0) and not exit_logic:
        return GuardResult("G12_tp_or_exit_logic", False,
                            "neither TP nor exit_logic set")
    return GuardResult("G12_tp_or_exit_logic", True)


def g13_smartnotebook_ready(smartnotebook) -> GuardResult:
    if smartnotebook is None:
        return GuardResult("G13_smartnotebook_ready", False, "no notebook")
    if not hasattr(smartnotebook, "record_decision_cycle"):
        return GuardResult("G13_smartnotebook_ready", False,
                            "notebook missing record method")
    return GuardResult("G13_smartnotebook_ready", True)


def g14_kill_switch_armed(kill_switch_path: Path) -> GuardResult:
    """Trading STOPS the moment kill_switch file is touched. Existence of
    this file = stop. Absence of the file = OK to consider trading."""
    if kill_switch_path.exists():
        return GuardResult("G14_kill_switch_armed", False,
                            f"kill_switch present: {kill_switch_path}")
    return GuardResult("G14_kill_switch_armed", True)


def g15_max_daily_loss_not_exceeded(today_realised_pl_pct: float,
                                       cap_pct: float = 1.0) -> GuardResult:
    if today_realised_pl_pct is None:
        return GuardResult("G15_max_daily_loss_not_exceeded", False,
                            "today P/L missing")
    if today_realised_pl_pct < -abs(cap_pct):
        return GuardResult("G15_max_daily_loss_not_exceeded", False,
                            f"today_pl={today_realised_pl_pct:.2f}% < -{cap_pct}%")
    return GuardResult("G15_max_daily_loss_not_exceeded", True)


def g16_max_trades_today_not_exceeded(trades_today: int,
                                         cap: int = 4) -> GuardResult:
    if trades_today is None:
        return GuardResult("G16_max_trades_today_not_exceeded", False,
                            "trades_today missing")
    if trades_today >= cap:
        return GuardResult("G16_max_trades_today_not_exceeded", False,
                            f"trades_today={trades_today} >= {cap}")
    return GuardResult("G16_max_trades_today_not_exceeded", True)


# ---------------------------------------------------------------------------
# Composite gate
# ---------------------------------------------------------------------------

def evaluate_all(*,
                   news, market, chart, gate_decision,
                   trade_candidate, smartnotebook,
                   now_utc: dt.datetime,
                   spread_pips: float, last_bar_utc: dt.datetime,
                   risk_pct_of_equity: float,
                   today_realised_pl_pct: float,
                   trades_today: int,
                   kill_switch_path: Path) -> GuardVerdict:
    results = [
        g01_three_brains_directional(news, market, chart),
        g02_gate_decision_enter(gate_decision),
        g03_all_grades_a_or_better(news, market, chart),
        g04_no_grade_b(news, market, chart),
        g05_no_should_block(news, market, chart),
        g06_no_data_quality_issue(news, market, chart),
        g07_inside_ny_window(now_utc),
        g08_spread_acceptable(spread_pips),
        g09_data_fresh(last_bar_utc, now_utc),
        g10_risk_size_micro(risk_pct_of_equity),
        g11_sl_present(trade_candidate),
        g12_tp_or_exit_logic(trade_candidate),
        g13_smartnotebook_ready(smartnotebook),
        g14_kill_switch_armed(kill_switch_path),
        g15_max_daily_loss_not_exceeded(today_realised_pl_pct),
        g16_max_trades_today_not_exceeded(trades_today),
    ]
    return GuardVerdict.from_results(results)
