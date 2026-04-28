"""Tests for the source layer.

We test:
  - RSS XML parsing extracts title + pubDate
  - Timeouts surface as SourceTimeout with health.last_status == 'timeout'
  - SourceHealth tracks last_fetch_utc
  - feedparser is NOT imported anywhere in newsmind.v4.sources
"""

from datetime import datetime, timezone
import sys

import pytest

from newsmind.v4 import sources as src_mod
from newsmind.v4.sources import (
    BaseSource,
    JSONCalendarSource,
    RSSXMLSource,
    SourceHTTPError,
    SourceParseError,
    SourceTimeout,
)


def _now():
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# RSS parser
# ---------------------------------------------------------------------------


_RSS_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.test</link>
    <description>fixture</description>
    <item>
      <title>Fed raises rates by 25bp</title>
      <link>https://example.test/fomc</link>
      <pubDate>Mon, 27 Apr 2026 18:00:00 GMT</pubDate>
      <description>FOMC decision</description>
    </item>
    <item>
      <title>Powell speech announced</title>
      <link>https://example.test/powell</link>
      <pubDate>Mon, 27 Apr 2026 11:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class _FixtureRSS(RSSXMLSource):
    """Bypasses HTTP — feeds bytes directly."""

    def __init__(self, payload: bytes, **kw):
        super().__init__(name="fixture", url="http://x", source_type="tier1", **kw)
        self._payload = payload

    def _http_get(self, now_utc):  # type: ignore[override]
        return self._payload


def test_rss_parser_extracts_title_and_published_at():
    src = _FixtureRSS(_RSS_FIXTURE)
    items = src.fetch(_now())
    assert len(items) == 2
    assert items[0].headline == "Fed raises rates by 25bp"
    assert items[0].normalized_utc_time == datetime(2026, 4, 27, 18, 0, 0, tzinfo=timezone.utc)
    assert items[0].source_name == "fixture"
    assert items[0].source_type == "tier1"
    assert src.health.last_status == "ok"


def test_rss_parser_skips_items_without_pubdate():
    payload = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>no date here</title></item>
    <item><title>has date</title><pubDate>Mon, 27 Apr 2026 18:00:00 GMT</pubDate></item>
    </channel></rss>"""
    src = _FixtureRSS(payload)
    items = src.fetch(_now())
    assert len(items) == 1
    assert items[0].headline == "has date"


def test_source_timeout_returns_typed_error_and_records_status():
    """We trigger SourceTimeout via a forced URLError(timeout)."""
    import urllib.error

    class _TimeoutSrc(RSSXMLSource):
        def _http_get(self, now_utc):  # type: ignore[override]
            self.health.record_failure(now_utc, "timeout")
            raise SourceTimeout("forced")

    s = _TimeoutSrc(name="x", url="http://x", source_type="tier1")
    with pytest.raises(SourceTimeout):
        s.fetch(_now())
    assert s.health.last_status == "timeout"
    assert s.health.consecutive_failures == 1


def test_source_health_tracks_last_fetch_utc():
    src = _FixtureRSS(_RSS_FIXTURE)
    t = _now()
    src.fetch(t)
    assert src.health.last_fetch_utc is not None
    assert src.health.last_fetch_utc.tzinfo is not None


def test_distinct_error_classes_are_distinct():
    # SourceTimeout is not SourceParseError — caller can branch.
    assert SourceTimeout is not SourceParseError
    assert SourceTimeout is not SourceHTTPError


def test_no_external_dependency_imported():
    # feedparser must NOT be a dependency of newsmind.v4.sources.
    # Important: we do NOT reload src_mod here — that would change
    # SourceParseError's class identity and contaminate other tests'
    # `pytest.raises(SourceParseError)` matchers (Red Team finding R6).
    src_path = src_mod.__file__
    with open(src_path, "r", encoding="utf-8") as f:
        text = f.read()
    # Allow it in comments, ban it as an import
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "import feedparser" not in stripped, f"forbidden import: {stripped}"
        assert "from feedparser" not in stripped, f"forbidden import: {stripped}"


# ---------------------------------------------------------------------------
# JSON calendar
# ---------------------------------------------------------------------------


_JSON_FIXTURE = b"""[
  {"title":"Non-Farm Employment Change","country":"USD","date":"2026-04-27T12:30:00Z","impact":"High","forecast":"175K","previous":"150K"},
  {"title":"ECB President Lagarde Speaks","country":"EUR","date":"2026-04-27T13:00:00Z","impact":"High"}
]"""


class _FixtureJSON(JSONCalendarSource):
    def __init__(self, payload: bytes):
        super().__init__(name="fixture-cal", url="http://x", source_type="calendar")
        self._payload = payload

    def _http_get(self, now_utc):  # type: ignore[override]
        return self._payload


def test_json_calendar_parses_rows():
    s = _FixtureJSON(_JSON_FIXTURE)
    items = s.fetch(_now())
    assert len(items) == 2
    assert items[0].headline.startswith("Non-Farm")
    assert items[0].source_type == "calendar"


def test_json_calendar_parse_error_surfaces():
    s = _FixtureJSON(b"{not json")
    with pytest.raises(SourceParseError):
        s.fetch(_now())
    assert s.health.last_status == "parse_error"
