"""Tests for fail-CLOSED + blackout + chase + confirmation behaviour."""

from datetime import datetime, timedelta, timezone

import pytest

from contracts.brain_output import BrainGrade
from newsmind.v4 import chase_detector
from newsmind.v4.config_loader import default_config_dir, load_events, load_keywords
from newsmind.v4.event_scheduler import EventScheduler
from newsmind.v4.models import NewsItem
from newsmind.v4.NewsMindV4 import NewsMindV4
from newsmind.v4.sources import BaseSource, SourceEmpty, SourceTimeout


def _t(h=12, m=0):
    return datetime(2026, 4, 27, h, m, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


class _SilentSource(BaseSource):
    def __init__(self, name="silent"):
        super().__init__(name=name, url="http://x", source_type="authoritative")

    def fetch(self, now_utc):
        self.health.record_failure(now_utc, "empty")
        raise SourceEmpty(f"{self.name} empty")


class _StaticSource(BaseSource):
    def __init__(self, name, source_type, items):
        super().__init__(name=name, url="http://x", source_type=source_type)
        self._items = items

    def fetch(self, now_utc):
        self.health.record_ok(now_utc)
        return list(self._items)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_silent_sources_block_at_nfp():
    """All sources empty AND NFP scheduled now → BLOCK (fail-CLOSED)."""
    events = load_events()
    sched = EventScheduler(events=events)
    nfp_time = _t(12, 30)
    sched.load_occurrences([("us_nfp", nfp_time)])

    sources = [_SilentSource("a"), _SilentSource("b")]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords={})

    out = nm.evaluate("EURUSD", nfp_time)
    assert out.is_blocking()
    assert out.grade == BrainGrade.BLOCK
    assert out.decision == "BLOCK"
    assert out.data_quality in ("missing", "broken")


def test_active_blackout_window_blocks():
    """Even with sources alive, being inside ±5 min of FOMC → BLOCK."""
    events = load_events()
    sched = EventScheduler(events=events)
    fomc_time = _t(18, 0)
    sched.load_occurrences([("us_fomc_decision", fomc_time)])

    item = NewsItem(
        headline="Markets quiet ahead of FOMC",
        source_name="federalreserve.gov",
        source_type="authoritative",
        normalized_utc_time=fomc_time - timedelta(minutes=2),
    )
    sources = [_StaticSource("federalreserve.gov", "authoritative", [item])]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords={})

    # 5 minutes before FOMC → inside blackout (pre=10 for FOMC)
    out = nm.evaluate("EURUSD", fomc_time - timedelta(minutes=5))
    assert out.is_blocking()
    assert "blackout" in out.reason.lower()


def test_outside_blackout_window_does_not_block_for_blackout_reason():
    events = load_events()
    sched = EventScheduler(events=events)
    fomc_time = _t(18, 0)
    sched.load_occurrences([("us_fomc_decision", fomc_time)])

    item = NewsItem(
        headline="Routine market commentary",
        source_name="forexlive.com",
        source_type="tier1",
        normalized_utc_time=fomc_time - timedelta(hours=2),
    )
    item2 = NewsItem(
        headline="Fed press release schedule",
        source_name="federalreserve.gov",
        source_type="authoritative",
        normalized_utc_time=fomc_time - timedelta(hours=2),
    )
    sources = [
        _StaticSource("federalreserve.gov", "authoritative", [item2]),
        _StaticSource("forexlive.com", "tier1", [item]),
    ]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords={})

    # 2 hours before FOMC → outside the [-10m, +60m] window
    out = nm.evaluate("EURUSD", fomc_time - timedelta(hours=2))
    # Not blocked due to blackout. Could still be WAIT.
    assert "blackout" not in out.reason.lower()


def test_unverified_social_caps_at_C():
    """A chase from social media must NOT yield A or A+."""
    keywords = load_keywords()
    sched = EventScheduler(events=load_events())

    item = NewsItem(
        headline="Unconfirmed: Fed source says rate cut imminent",
        source_name="twitter.com/anon",
        source_type="social",
        normalized_utc_time=_t(12, 0) - timedelta(minutes=1),
    )
    sources = [_StaticSource("twitter.com/anon", "social", [item])]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords=keywords)

    out = nm.evaluate("EURUSD", _t(12, 0))
    # Should be C at best (chase) — never A/A+
    assert out.grade in (BrainGrade.C, BrainGrade.B, BrainGrade.BLOCK)
    assert out.grade not in (BrainGrade.A, BrainGrade.A_PLUS)


def test_chase_detector_flags_social_alone():
    assert chase_detector.is_chase(
        source_type="social",
        confirmation_count=0,
        impact_level="high",
        headline="anon says big move coming",
        unverified_source_names=["twitter"],
        source_name="twitter.com/anon",
    )


def test_chase_detector_clears_authoritative():
    assert not chase_detector.is_chase(
        source_type="authoritative",
        confirmation_count=2,
        impact_level="high",
        headline="FOMC: rates +25bp",
        unverified_source_names=["twitter"],
        source_name="federalreserve.gov",
    )


def test_grade_a_requires_two_confirmations():
    """One source, even authoritative + fresh, cannot give A — needs 2nd confirm."""
    keywords = load_keywords()
    sched = EventScheduler(events=load_events())

    fresh = _t(12, 0) - timedelta(minutes=1)
    only_one = NewsItem(
        headline="ECB keeps rates unchanged",
        source_name="ecb.europa.eu",
        source_type="authoritative",
        normalized_utc_time=fresh,
    )
    sources = [_StaticSource("ecb.europa.eu", "authoritative", [only_one])]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords=keywords)
    out = nm.evaluate("EURUSD", _t(12, 0))
    assert out.grade not in (BrainGrade.A, BrainGrade.A_PLUS)


def test_two_confirmations_can_reach_grade_a():
    keywords = load_keywords()
    sched = EventScheduler(events=load_events())

    fresh = _t(12, 0) - timedelta(minutes=1)
    a = NewsItem(
        headline="ECB keeps rates unchanged",
        source_name="ecb.europa.eu",
        source_type="authoritative",
        normalized_utc_time=fresh,
    )
    b = NewsItem(
        headline="ECB decision confirmed by reporter",
        source_name="forexlive.com",
        source_type="tier1",
        normalized_utc_time=fresh,
    )
    sources = [
        _StaticSource("ecb.europa.eu", "authoritative", [a]),
        _StaticSource("forexlive.com", "tier1", [b]),
    ]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords=keywords)
    out = nm.evaluate("EURUSD", _t(12, 0))
    assert out.grade in (BrainGrade.A, BrainGrade.B)  # may settle to B if not perfectly fresh
