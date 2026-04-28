"""NewsMind V4 — source adapters (REBUILT, no feedparser).

Stdlib only:
  - urllib.request  (HTTP)
  - xml.etree.ElementTree (RSS 2.0 parse)
  - json (calendar)
  - email.utils.parsedate_to_datetime (RFC-822 timestamps in RSS pubDate)

Distinct error classes — DO NOT collapse them:
  - SourceTimeout       → network ran out of time. Retry candidate.
  - SourceParseError    → HTTP 200 but XML/JSON malformed. Provider broke schema.
  - SourceEmpty         → HTTP 200, parsed fine, zero items. Could mean
                          'genuinely no news' OR 'feed lying'. Caller must
                          treat as suspicious, NOT as 'all clear'.
  - SourceHTTPError     → 4xx / 5xx. Provider is down.

Each source's fetch():
  - timeout = 5s
  - retries = 0 (one-shot; the orchestrator can call again next tick)
  - returns list[NewsItem] on success
  - raises one of the above on failure

The orchestrator calls fetch() inside a try/except per-source so a single
broken feed does not poison the whole evaluation; instead the source's
SourceHealth records the specific failure mode.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

from newsmind.v4.models import NewsItem, SourceHealth


# ---------------------------------------------------------------------------
# error taxonomy
# ---------------------------------------------------------------------------


class SourceError(Exception):
    """Base for all source-layer errors."""


class SourceTimeout(SourceError):
    """Network timed out."""


class SourceParseError(SourceError):
    """HTTP 200 but body could not be parsed."""


class SourceEmpty(SourceError):
    """HTTP 200, parsed fine, zero items. Suspicious — not 'all clear'."""


class SourceHTTPError(SourceError):
    """HTTP 4xx / 5xx."""


# ---------------------------------------------------------------------------
# base
# ---------------------------------------------------------------------------


_DEFAULT_TIMEOUT = 5.0
_USER_AGENT = "HydraV4-NewsMind/1.0 (+stdlib)"


class BaseSource(ABC):
    def __init__(
        self,
        name: str,
        url: str,
        source_type: str,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.name = name
        self.url = url
        self.source_type = source_type
        self.timeout = timeout
        self.health = SourceHealth(source_name=name)

    @abstractmethod
    def fetch(self, now_utc: datetime) -> List[NewsItem]:
        """Fetch and parse. Raises SourceError subclass on any failure."""

    # ---- shared HTTP -----------------------------------------------------

    def _http_get(self, now_utc: datetime) -> bytes:
        req = urllib.request.Request(self.url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status >= 400:
                    self.health.record_failure(now_utc, "http_error")
                    raise SourceHTTPError(f"{self.name} returned HTTP {resp.status}")
                return resp.read()
        except urllib.error.HTTPError as e:
            self.health.record_failure(now_utc, "http_error")
            raise SourceHTTPError(f"{self.name} HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            # URLError wraps timeouts
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                self.health.record_failure(now_utc, "timeout")
                raise SourceTimeout(f"{self.name} timed out: {reason}") from e
            self.health.record_failure(now_utc, "http_error")
            raise SourceHTTPError(f"{self.name} URL error: {reason}") from e
        except TimeoutError as e:
            self.health.record_failure(now_utc, "timeout")
            raise SourceTimeout(f"{self.name} timed out") from e


# ---------------------------------------------------------------------------
# RSS 2.0 XML
# ---------------------------------------------------------------------------


class RSSXMLSource(BaseSource):
    """RSS 2.0 parser using xml.etree. Handles <item><title><pubDate><link>."""

    def fetch(self, now_utc: datetime) -> List[NewsItem]:
        raw = self._http_get(now_utc)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            self.health.record_failure(now_utc, "parse_error")
            raise SourceParseError(f"{self.name} XML parse error: {e}") from e

        items = self._parse_items(root)
        if not items:
            self.health.record_failure(now_utc, "empty")
            raise SourceEmpty(f"{self.name} returned 0 items")

        self.health.record_ok(now_utc)
        return items

    def _parse_items(self, root: ET.Element) -> List[NewsItem]:
        # RSS 2.0: rss/channel/item   |   Atom: feed/entry
        items: List[NewsItem] = []

        # RSS 2.0
        for item in root.iter("item"):
            ni = self._build_rss_item(item)
            if ni is not None:
                items.append(ni)

        if items:
            return items

        # Atom fallback
        atom_ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.iter(f"{atom_ns}entry"):
            ni = self._build_atom_item(entry, atom_ns)
            if ni is not None:
                items.append(ni)

        return items

    def _build_rss_item(self, item: ET.Element) -> Optional[NewsItem]:
        title_el = item.find("title")
        if title_el is None or not (title_el.text or "").strip():
            return None
        title = title_el.text.strip()

        pub_el = item.find("pubDate")
        published = self._parse_rfc822(pub_el.text if pub_el is not None else None)
        if published is None:
            # Sources without timestamps are not trustworthy enough for V4
            return None

        link_el = item.find("link")
        url = link_el.text.strip() if link_el is not None and link_el.text else None

        desc_el = item.find("description")
        body = desc_el.text.strip() if desc_el is not None and desc_el.text else None

        return NewsItem(
            headline=title,
            source_name=self.name,
            source_type=self.source_type,
            normalized_utc_time=published,
            url=url,
            body=body,
        )

    def _build_atom_item(
        self, entry: ET.Element, ns: str
    ) -> Optional[NewsItem]:
        title_el = entry.find(f"{ns}title")
        if title_el is None or not (title_el.text or "").strip():
            return None
        title = title_el.text.strip()

        pub_el = entry.find(f"{ns}updated") or entry.find(f"{ns}published")
        published = self._parse_iso8601(pub_el.text if pub_el is not None else None)
        if published is None:
            return None

        link_el = entry.find(f"{ns}link")
        url = link_el.get("href") if link_el is not None else None

        return NewsItem(
            headline=title,
            source_name=self.name,
            source_type=self.source_type,
            normalized_utc_time=published,
            url=url,
        )

    @staticmethod
    def _parse_rfc822(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _parse_iso8601(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        s = s.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# JSON economic calendar
# ---------------------------------------------------------------------------


class JSONCalendarSource(BaseSource):
    """FairEconomy ff_calendar_thisweek.json adapter.

    Each entry typically has keys: title, country, date (ISO), impact, forecast,
    previous, actual. We surface entries as NewsItem, with the title used as
    headline. The orchestrator separately uses the calendar to populate
    EventSchedule blackout windows.
    """

    def fetch(self, now_utc: datetime) -> List[NewsItem]:
        raw = self._http_get(now_utc)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.health.record_failure(now_utc, "parse_error")
            raise SourceParseError(f"{self.name} JSON parse error: {e}") from e

        if not isinstance(data, list):
            self.health.record_failure(now_utc, "parse_error")
            raise SourceParseError(f"{self.name} expected JSON array")

        items: List[NewsItem] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            title = row.get("title")
            date_str = row.get("date")
            if not title or not date_str:
                continue
            published = RSSXMLSource._parse_iso8601(date_str)
            if published is None:
                continue
            items.append(
                NewsItem(
                    headline=str(title),
                    source_name=self.name,
                    source_type=self.source_type,
                    normalized_utc_time=published,
                    url=None,
                    body=json.dumps(
                        {
                            k: row.get(k)
                            for k in ("country", "impact", "forecast", "previous", "actual")
                            if k in row
                        }
                    ),
                )
            )

        if not items:
            self.health.record_failure(now_utc, "empty")
            raise SourceEmpty(f"{self.name} produced 0 items")

        self.health.record_ok(now_utc)
        return items


# ---------------------------------------------------------------------------
# default 5-source pack
# ---------------------------------------------------------------------------


def default_sources() -> List[BaseSource]:
    """The 5 sources V4 ships with."""
    return [
        RSSXMLSource(
            name="federalreserve.gov",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            source_type="authoritative",
        ),
        RSSXMLSource(
            name="ecb.europa.eu",
            url="https://www.ecb.europa.eu/rss/press.html",
            source_type="authoritative",
        ),
        RSSXMLSource(
            name="boj.or.jp",
            url="https://www.boj.or.jp/en/rss/whatsnew.xml",
            source_type="authoritative",
        ),
        JSONCalendarSource(
            name="faireconomy.media",
            url="https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            source_type="calendar",
        ),
        RSSXMLSource(
            name="forexlive.com",
            url="https://www.forexlive.com/feed/",
            source_type="tier1",
        ),
    ]
