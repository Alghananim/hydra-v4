"""GateMind V4 test fixtures.

All fixtures construct *real* BrainOutput instances (frozen contract) so
contract violations surface during fixture build. No mocking — same code
paths as production.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

# Ensure project root is importable
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from zoneinfo import ZoneInfo

from contracts.brain_output import BrainGrade, BrainOutput

NY_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc


# ---------------------------------------------------------------------------
# BrainOutput factories
# ---------------------------------------------------------------------------
_BRAIN_KEY_MAP = {
    "NewsMind": "newsmind",
    "MarketMind": "marketmind",
    "ChartMind": "chartmind",
}


def _resolve_brain_name(brain_name: str) -> str:
    """Accept 'NewsMind' / 'newsmind' both ways."""
    if brain_name in _BRAIN_KEY_MAP.values():
        return brain_name
    return _BRAIN_KEY_MAP.get(brain_name, brain_name.lower())


def _now_utc() -> datetime:
    return datetime.now(UTC)


def make_brain_output_aplus_buy(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="BUY",
        grade=BrainGrade.A_PLUS,
        reason=f"{brain_name} A+ BUY",
        evidence=[f"{brain_name} signal 1", f"{brain_name} signal 2"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.9,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_a_buy(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="BUY",
        grade=BrainGrade.A,
        reason=f"{brain_name} A BUY",
        evidence=[f"{brain_name} signal A"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.8,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_aplus_sell(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="SELL",
        grade=BrainGrade.A_PLUS,
        reason=f"{brain_name} A+ SELL",
        evidence=[f"{brain_name} bearish signal"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.9,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_a_sell(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="SELL",
        grade=BrainGrade.A,
        reason=f"{brain_name} A SELL",
        evidence=[f"{brain_name} bearish A"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.8,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_a_wait(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="WAIT",
        grade=BrainGrade.A,
        reason=f"{brain_name} A WAIT",
        evidence=[f"{brain_name} neutral"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.7,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_aplus_wait(brain_name: str, *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="WAIT",
        grade=BrainGrade.A_PLUS,
        reason=f"{brain_name} A+ WAIT",
        evidence=[f"{brain_name} neutral hi-conf"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.85,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_block(brain_name: str, reason: str = "fail closed", *, now_utc: Optional[datetime] = None) -> BrainOutput:
    return BrainOutput.fail_closed(
        brain_name=_resolve_brain_name(brain_name),
        reason=reason,
    )


def make_brain_output_b_grade(brain_name: str, *, decision: str = "BUY", now_utc: Optional[datetime] = None) -> BrainOutput:
    """Returns a B-graded BUY output. Should always cause GateMind BLOCK."""
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision=decision,
        grade=BrainGrade.B,
        reason=f"{brain_name} B grade",
        evidence=[f"{brain_name} weakish signal"],
        data_quality="stale",
        should_block=False,
        risk_flags=[],
        confidence=0.55,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_with_kill_flag(brain_name: str, flag: str = "news_blackout",
                                      *, decision: str = "BUY",
                                      grade: BrainGrade = BrainGrade.A_PLUS,
                                      now_utc: Optional[datetime] = None) -> BrainOutput:
    """A+ BUY but carrying a kill-class flag — should BLOCK at R5."""
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision=decision,
        grade=grade,
        reason=f"{brain_name} A+ with kill flag {flag}",
        evidence=[f"{brain_name} signal"],
        data_quality="good",
        should_block=False,
        risk_flags=[flag],
        confidence=0.9,
        timestamp_utc=now_utc or _now_utc(),
    )


def make_brain_output_with_warning_flag(brain_name: str, flag: str = "spread_anomaly",
                                         *, now_utc: Optional[datetime] = None) -> BrainOutput:
    """A+ BUY with a warning flag — should still ENTER (warnings are logged)."""
    return BrainOutput(
        brain_name=_resolve_brain_name(brain_name),
        decision="BUY",
        grade=BrainGrade.A_PLUS,
        reason=f"{brain_name} A+ with warning {flag}",
        evidence=[f"{brain_name} signal w/warning"],
        data_quality="good",
        should_block=False,
        risk_flags=[flag],
        confidence=0.9,
        timestamp_utc=now_utc or _now_utc(),
    )


class _NotABrainOutput:
    """Counterfeit object used to test schema validation rejecting non-BrainOutputs."""
    brain_name = "newsmind"
    decision = "BUY"
    grade = "A+"  # WRONG — should be Enum
    reason = "fake"
    evidence = ["x"]
    data_quality = "good"
    should_block = False
    risk_flags: List[str] = []
    confidence = 0.9
    timestamp_utc = datetime.now(UTC)


def make_brain_output_invalid_schema(brain_name: str = "NewsMind"):
    """Returns a non-BrainOutput object — schema validator must reject."""
    obj = _NotABrainOutput()
    obj.brain_name = _resolve_brain_name(brain_name)
    return obj


# ---------------------------------------------------------------------------
# Time fixtures — NY windows
# ---------------------------------------------------------------------------
def now_in_ny_window(window: int = 1) -> datetime:
    """Return a UTC datetime that maps inside NY window 1 (3-5) or 2 (8-12).

    We anchor on a known summer date (2025-07-15) where NY observes EDT (UTC-4).
    Window 1: pick 04:00 NY → 08:00 UTC
    Window 2: pick 10:00 NY → 14:00 UTC
    """
    if window == 1:
        ny_local = datetime(2025, 7, 15, 4, 0, 0, tzinfo=NY_TZ)
    elif window == 2:
        ny_local = datetime(2025, 7, 15, 10, 0, 0, tzinfo=NY_TZ)
    else:
        raise ValueError("window must be 1 or 2")
    return ny_local.astimezone(UTC)


def now_outside_ny_window() -> datetime:
    """A UTC moment that is firmly outside both windows.

    06:30 NY local on 2025-07-15 → between window 1 (3-5) and window 2 (8-12).
    """
    ny_local = datetime(2025, 7, 15, 6, 30, 0, tzinfo=NY_TZ)
    return ny_local.astimezone(UTC)


def now_dst_spring_forward() -> datetime:
    """A UTC moment near the spring DST transition (March 9 2025, 02:00→03:00 NY).

    We pick 09:00 NY local (window 2, EDT) on the spring-forward day to verify
    that DST is correctly handled.
    """
    ny_local = datetime(2025, 3, 9, 9, 0, 0, tzinfo=NY_TZ)
    return ny_local.astimezone(UTC)


def now_dst_fall_back() -> datetime:
    """A UTC moment on the fall DST transition (November 2 2025).

    We pick 09:00 NY local (window 2, EST) on the fall-back day.
    """
    ny_local = datetime(2025, 11, 2, 9, 0, 0, tzinfo=NY_TZ)
    return ny_local.astimezone(UTC)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def factories():
    """Bundle of factory callables for tests that prefer fixture style."""
    return {
        "aplus_buy": make_brain_output_aplus_buy,
        "a_buy": make_brain_output_a_buy,
        "aplus_sell": make_brain_output_aplus_sell,
        "a_sell": make_brain_output_a_sell,
        "a_wait": make_brain_output_a_wait,
        "aplus_wait": make_brain_output_aplus_wait,
        "block": make_brain_output_block,
        "b_grade": make_brain_output_b_grade,
        "kill_flag": make_brain_output_with_kill_flag,
        "warning_flag": make_brain_output_with_warning_flag,
        "invalid": make_brain_output_invalid_schema,
    }


@pytest.fixture
def in_window_1():
    return now_in_ny_window(1)


@pytest.fixture
def in_window_2():
    return now_in_ny_window(2)


@pytest.fixture
def outside_window():
    return now_outside_ny_window()


@pytest.fixture(autouse=True)
def _wipe_audit_store():
    """Reset audit store between tests for clean reproducibility checks."""
    from gatemind.v4 import audit_log
    audit_log.clear_audit_store()
    yield
    audit_log.clear_audit_store()
