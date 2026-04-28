"""NewsMind V4 — hardening tests for Red Team findings R1–R7.

Each test corresponds to a documented Red Team break. They all fail-CLOSED
or raise on the original attack vector.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from contracts.brain_output import BrainGrade, BrainOutput
from newsmind.v4.config_loader import load_events, load_keywords
from newsmind.v4.event_scheduler import EventScheduler
from newsmind.v4.models import EventSchedule, NewsItem, _normalize_pair
from newsmind.v4.NewsMindV4 import NewsMindV4, _affects_pair
from newsmind.v4.sources import BaseSource, SourceEmpty


def _t(h=12, m=0):
    return datetime(2026, 4, 27, h, m, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


class _Static(BaseSource):
    def __init__(self, name, source_type, items):
        super().__init__(name=name, url="http://x", source_type=source_type)
        self._items = items

    def fetch(self, now_utc):
        self.health.record_ok(now_utc)
        return list(self._items)


# ---------------------------------------------------------------------------
# R1 — pair-with-slash bypassed blackout
# ---------------------------------------------------------------------------


def _make_event(affected_pairs):
    return EventSchedule(
        id="test_event",
        name="Test Event",
        currency="USD",
        affects=list(affected_pairs),
        blackout_pre_min=5,
        blackout_post_min=30,
        pip_per_sigma={"EURUSD": 10.0},
        tier=1,
    )


def test_eur_usd_with_slash_blackout_works():
    """affects_pair must normalize 'EUR/USD' before comparing to 'EURUSD'."""
    ev = _make_event(["EURUSD"])
    assert ev.affects_pair("EUR/USD") is True
    assert ev.affects_pair("EUR-USD") is True
    assert ev.affects_pair("EUR_USD") is True
    assert ev.affects_pair("eur usd") is True
    assert ev.affects_pair("EURUSD") is True


def test_invalid_pair_raises():
    """Anything that doesn't reduce to ^[A-Z]{6}$ must raise."""
    ev = _make_event(["EURUSD"])
    with pytest.raises(ValueError, match="invalid pair format"):
        ev.affects_pair("EUR_USD_BAD")
    with pytest.raises(ValueError, match="invalid pair format"):
        ev.affects_pair("EUR")
    with pytest.raises(ValueError, match="invalid pair format"):
        ev.affects_pair("EUR/USD/JPY")
    with pytest.raises(ValueError, match="invalid pair format"):
        ev.affects_pair("123456")


def test_normalize_pair_helper_directly():
    assert _normalize_pair("EUR/USD") == "EURUSD"
    assert _normalize_pair("eur-usd") == "EURUSD"
    assert _normalize_pair("USD JPY") == "USDJPY"
    with pytest.raises(ValueError):
        _normalize_pair("xx")


def test_blackout_reaches_through_slash_pair_at_orchestrator():
    """End-to-end re-attack of R1: caller passes 'EUR/USD' to evaluate()
    while inside an active blackout — orchestrator must BLOCK, not let it
    through because the slash sneaked past .upper()."""
    sched = EventScheduler(events=load_events())
    fomc_time = _t(18, 0)
    sched.load_occurrences([("us_fomc_decision", fomc_time)])

    item = NewsItem(
        headline="Markets quiet ahead of FOMC",
        source_name="federalreserve.gov",
        source_type="authoritative",
        normalized_utc_time=fomc_time - timedelta(minutes=2),
    )
    nm = NewsMindV4(
        sources=[_Static("federalreserve.gov", "authoritative", [item])],
        scheduler=sched,
        keywords={},
    )

    # 5 min before FOMC, with slashed pair: previously slipped past blackout.
    out = nm.evaluate("EUR/USD", fomc_time - timedelta(minutes=5))
    assert out.is_blocking()
    assert out.grade == BrainGrade.BLOCK
    assert "blackout" in out.reason.lower()


# ---------------------------------------------------------------------------
# R2 — stale-but-ok leak (data_quality 'good' while items > 6h)
# ---------------------------------------------------------------------------


def test_stale_items_marked_as_stale_not_good():
    """All sources HTTP 200 but every item is >6h old → data_quality='stale',
    NOT 'good'. Permission must NOT be ENTER."""
    sched = EventScheduler(events=load_events())  # no occurrences
    eight_h_ago = _t(12, 0) - timedelta(hours=8)
    items_a = [NewsItem(
        headline="Stale ECB headline",
        source_name="ecb.europa.eu",
        source_type="authoritative",
        normalized_utc_time=eight_h_ago,
    )]
    items_b = [NewsItem(
        headline="Stale forexlive headline",
        source_name="forexlive.com",
        source_type="tier1",
        normalized_utc_time=eight_h_ago,
    )]
    # 5 sources all returning >6h items — feed alive, but nothing in window.
    sources = [
        _Static("ecb.europa.eu", "authoritative", items_a),
        _Static("forexlive.com", "tier1", items_b),
        _Static("federalreserve.gov", "authoritative", []),
        _Static("boj.or.jp", "authoritative", []),
        _Static("faireconomy.com", "calendar", []),
    ]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords={})
    out = nm.evaluate("EURUSD", _t(12, 0))

    assert out.data_quality == "stale", (
        f"expected stale, got {out.data_quality}"
    )
    # grade must NOT be A or A+
    assert out.grade not in (BrainGrade.A, BrainGrade.A_PLUS)
    # decision must NOT be a green-light ENTER (NewsMind never says BUY/SELL,
    # but it MUST be WAIT or BLOCK, never the optimistic path).
    assert out.decision in ("WAIT", "BLOCK")
    # surfaced as a risk flag
    assert "stale_feed_no_recent_items" in out.risk_flags


def test_stale_data_quality_blocks_a_grade_construction():
    """Even if a downstream caller tried to build BrainOutput(A, stale)
    directly, the contract must reject it."""
    with pytest.raises(ValueError, match="data_quality=='good'"):
        BrainOutput(
            brain_name="newsmind",
            decision="WAIT",
            grade=BrainGrade.A,
            reason="x",
            evidence=["headline=foo"],
            data_quality="stale",
            should_block=False,
            risk_flags=[],
            confidence=0.5,
            timestamp_utc=_t(),
        )


# ---------------------------------------------------------------------------
# R3 — empty-string evidence bypassed A+ invariant
# ---------------------------------------------------------------------------


def _valid_kwargs(**overrides):
    base = dict(
        brain_name="newsmind",
        decision="WAIT",
        grade=BrainGrade.A_PLUS,
        reason="ok",
        evidence=["real fact"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.9,
        timestamp_utc=_t(),
    )
    base.update(overrides)
    return base


def test_empty_string_evidence_raises_for_a_plus():
    with pytest.raises(ValueError, match="REQUIRES non-empty evidence"):
        BrainOutput(**_valid_kwargs(evidence=[""]))


def test_whitespace_only_evidence_raises_for_a_plus():
    with pytest.raises(ValueError, match="REQUIRES non-empty evidence"):
        BrainOutput(**_valid_kwargs(evidence=["   "]))
    with pytest.raises(ValueError, match="REQUIRES non-empty evidence"):
        BrainOutput(**_valid_kwargs(evidence=["", "   ", "\t\n"]))


def test_empty_string_evidence_raises_for_a():
    with pytest.raises(ValueError, match="REQUIRES non-empty evidence"):
        BrainOutput(**_valid_kwargs(grade=BrainGrade.A, evidence=[""]))


def test_real_evidence_passes():
    out = BrainOutput(
        **_valid_kwargs(evidence=["headline=FOMC raises 25bp", "  "])
    )
    assert out.grade == BrainGrade.A_PLUS


# ---------------------------------------------------------------------------
# R4 — _affects_pair defaulted True for unknown source_name
# ---------------------------------------------------------------------------


def test_unknown_source_does_not_affect_pair_by_default():
    """An attacker-registered source with an unknown name must NOT be
    treated as relevant for pair-affecting purposes."""
    item = NewsItem(
        headline="Some random headline about cats",
        source_name="evil.attacker.example",  # not in allowlist
        source_type="authoritative",          # claimed authoritative
        normalized_utc_time=_t(12, 0) - timedelta(minutes=1),
    )
    assert _affects_pair("EURUSD", item) is False
    assert _affects_pair("USDJPY", item) is False


def test_unknown_source_with_explicit_affected_assets_works():
    """Path (b): explicit affected_assets allows an unknown source through."""
    # NewsItem has no affected_assets field, so we patch it via a duck-typed
    # subclass to prove the orchestrator honors explicit overrides without
    # requiring a frozen-model migration.
    class _ItemWithAssets(NewsItem):
        pass

    item = _ItemWithAssets(
        headline="Custom feed: EUR moves",
        source_name="evil.attacker.example",
        source_type="authoritative",
        normalized_utc_time=_t(12, 0) - timedelta(minutes=1),
    )
    object.__setattr__(item, "affected_assets", ["EURUSD"])
    assert _affects_pair("EURUSD", item) is True
    # Different pair: not in the explicit list → still False.
    assert _affects_pair("USDJPY", item) is False


def test_known_source_works():
    item = NewsItem(
        headline="FOMC: rates +25bp",
        source_name="federalreserve.gov",
        source_type="authoritative",
        normalized_utc_time=_t(12, 0) - timedelta(minutes=1),
    )
    assert _affects_pair("EURUSD", item) is True
    assert _affects_pair("USDJPY", item) is True


def test_unknown_authoritative_cannot_inflate_to_grade_a():
    """Re-attack R4: attacker plants two off-topic 'authoritative' sources.
    Without allowlist match, _affects_pair returns False so confirmation_count
    cannot reach 2 and grade cannot reach A."""
    sched = EventScheduler(events=load_events())
    fresh = _t(12, 0) - timedelta(minutes=1)
    a = NewsItem(
        headline="Cats announce world domination",
        source_name="cats-news.example",
        source_type="authoritative",
        normalized_utc_time=fresh,
    )
    b = NewsItem(
        headline="Dogs respond to cat threat",
        source_name="dogs-news.example",
        source_type="authoritative",
        normalized_utc_time=fresh,
    )
    sources = [
        _Static("cats-news.example", "authoritative", [a]),
        _Static("dogs-news.example", "authoritative", [b]),
    ]
    nm = NewsMindV4(sources=sources, scheduler=sched, keywords={})
    out = nm.evaluate("EURUSD", _t(12, 0))
    assert out.grade not in (BrainGrade.A, BrainGrade.A_PLUS)


# ---------------------------------------------------------------------------
# R5 — missing keywords.yaml swallowed silently
# ---------------------------------------------------------------------------


def test_missing_keywords_yaml_raises_at_init(tmp_path):
    """If keywords is None and the config file is absent, init must NOT
    silently default to {}. The chase-protection list is safety-critical."""
    empty_dir = tmp_path / "no_yaml_here"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        NewsMindV4(
            sources=[],
            scheduler=EventScheduler(events=load_events()),
            keywords=None,
            config_dir=empty_dir,
        )


def test_explicit_keywords_dict_bypasses_file_load():
    """Passing an explicit keywords dict means we never touch disk."""
    nm = NewsMindV4(
        sources=[],
        scheduler=EventScheduler(events=load_events()),
        keywords={"unverified_sources": []},
    )
    assert nm._keywords == {"unverified_sources": []}


# ---------------------------------------------------------------------------
# R7 — llm_review module remains importable (dead-code stub test)
# ---------------------------------------------------------------------------


def test_llm_review_module_importable():
    """v4.0 leaves llm_review.py dormant. It must still import cleanly so
    v4.1 can wire it without surprise."""
    from newsmind.v4 import llm_review

    assert hasattr(llm_review, "review")
    assert hasattr(llm_review, "build_prompt")
    assert hasattr(llm_review, "LLMReview")
    # The orchestrator MUST NOT import llm_review yet — we just check the
    # module name isn't referenced inside NewsMindV4 source as an import.
    # Note: `from newsmind.v4 import NewsMindV4` resolves to the *class*
    # (re-exported in v4/__init__.py); we want the *module* file, hence
    # using importlib to get the module object directly.
    import importlib

    orch_module = importlib.import_module("newsmind.v4.NewsMindV4")
    src_path = orch_module.__file__
    with open(src_path, "r", encoding="utf-8") as f:
        text = f.read()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # No active import of llm_review in v4.0
        assert "import llm_review" not in stripped
        assert "from newsmind.v4.llm_review" not in stripped
        assert "from newsmind.v4 import llm_review" not in stripped
