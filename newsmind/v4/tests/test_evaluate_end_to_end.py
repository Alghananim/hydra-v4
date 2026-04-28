"""End-to-end tests for NewsMindV4.evaluate."""

from datetime import datetime, timedelta, timezone

import pytest

from contracts.brain_output import BrainGrade, BrainOutput
from newsmind.v4.config_loader import default_config_dir, load_events, load_keywords
from newsmind.v4.event_scheduler import EventScheduler
from newsmind.v4.models import NewsItem
from newsmind.v4.NewsMindV4 import NewsMindV4
from newsmind.v4.sources import BaseSource, SourceEmpty


def _t(h=12, m=0):
    return datetime(2026, 4, 27, h, m, 0, tzinfo=timezone.utc)


class _Silent(BaseSource):
    def __init__(self, name):
        super().__init__(name=name, url="http://x", source_type="authoritative")

    def fetch(self, now_utc):
        self.health.record_failure(now_utc, "empty")
        raise SourceEmpty(self.name)


class _Static(BaseSource):
    def __init__(self, name, source_type, items):
        super().__init__(name=name, url="http://x", source_type=source_type)
        self._items = items

    def fetch(self, now_utc):
        self.health.record_ok(now_utc)
        return list(self._items)


# ---------------------------------------------------------------------------


def test_no_news_no_calendar_returns_block():
    sched = EventScheduler(events=load_events())  # no occurrences loaded
    nm = NewsMindV4(
        sources=[_Silent("a"), _Silent("b")],
        scheduler=sched,
        keywords={},
    )
    out = nm.evaluate("USDJPY", _t())
    assert out.is_blocking()
    assert out.grade == BrainGrade.BLOCK
    # data_quality must reflect silence — NOT 'good'
    assert out.data_quality in ("missing", "broken")


def test_real_event_loaded_from_yaml():
    """events.yaml MUST actually load 10 curated events."""
    events = load_events()
    ids = {e.id for e in events}
    expected_minimum = {
        "us_nfp",
        "us_cpi",
        "us_fomc_decision",
        "eu_ecb_decision",
        "jp_boj_decision",
    }
    assert expected_minimum.issubset(ids), f"missing: {expected_minimum - ids}"
    assert len(events) >= 10
    # Sanity: pip_per_sigma populated with real numbers
    nfp = next(e for e in events if e.id == "us_nfp")
    assert nfp.pip_per_sigma["EURUSD"] > 0
    assert nfp.pip_per_sigma["USDJPY"] > 0


def test_brain_output_contract_holds():
    """Verdict from a normal-ish run must satisfy BrainOutput __post_init__."""
    keywords = load_keywords()
    sched = EventScheduler(events=load_events())  # no scheduled events → no blackout

    fresh = _t() - timedelta(minutes=1)
    items_a = [
        NewsItem(
            headline="ECB holds rates",
            source_name="ecb.europa.eu",
            source_type="authoritative",
            normalized_utc_time=fresh,
        )
    ]
    items_b = [
        NewsItem(
            headline="ECB decision confirmed",
            source_name="forexlive.com",
            source_type="tier1",
            normalized_utc_time=fresh,
        )
    ]
    nm = NewsMindV4(
        sources=[
            _Static("ecb.europa.eu", "authoritative", items_a),
            _Static("forexlive.com", "tier1", items_b),
        ],
        scheduler=sched,
        keywords=keywords,
    )
    out = nm.evaluate("EURUSD", _t())
    assert isinstance(out, BrainOutput)
    # The construction itself proves __post_init__ passed.
    assert out.brain_name == "newsmind"
    assert out.timestamp_utc.tzinfo is not None
    assert out.confidence >= 0.0
    assert len(out.evidence) >= 1
    # NewsMind never emits BUY/SELL alone:
    assert out.decision in ("WAIT", "BLOCK")


def test_orchestrator_fails_closed_on_unexpected_exception(monkeypatch):
    """If an unexpected exception leaks past the source layer, evaluate must
    return BrainOutput(BLOCK), not crash."""
    sched = EventScheduler(events=load_events())
    nm = NewsMindV4(sources=[_Silent("a")], scheduler=sched, keywords={})

    def boom(self, pair, now_utc, current_bar):
        raise RuntimeError("synthetic boom")

    monkeypatch.setattr(NewsMindV4, "_evaluate_inner", boom)

    out = nm.evaluate("EURUSD", _t())
    assert out.is_blocking()
    assert out.grade == BrainGrade.BLOCK
    assert "synthetic boom" in out.reason
    assert "orchestrator_exception" in out.risk_flags


def test_news_verdict_is_attached_after_evaluate():
    keywords = load_keywords()
    sched = EventScheduler(events=load_events())
    nm = NewsMindV4(sources=[_Silent("a")], scheduler=sched, keywords=keywords)
    nm.evaluate("USDJPY", _t())
    # last_verdict may be None on the early-fail path; in general it's set
    # only when _evaluate_inner reaches the end. With all-silent sources it's
    # set: the flow goes summary → quality=missing → permission BLOCK.
    assert nm.last_verdict is not None
    assert nm.last_verdict.trade_permission in ("BLOCK", "WAIT")
