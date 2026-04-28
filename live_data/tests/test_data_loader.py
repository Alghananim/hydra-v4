"""Tests for the 2-year data loader."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from live_data.data_cache import JsonlCache
from live_data.data_loader import download_two_years, plan_pages


class _FakeClient:
    """A fake OandaReadOnlyClient that returns synthetic candles."""

    def __init__(self, granularity_minutes: int = 15):
        self.calls = 0
        self.gm = granularity_minutes

    def get_candles(self, instrument, granularity, from_time, to_time, price="BAM"):
        self.calls += 1
        # Generate one candle per granularity step inside the window.
        from_dt = _parse(from_time)
        to_dt = _parse(to_time)
        out = []
        cur = from_dt
        step = timedelta(minutes=self.gm)
        i = 0
        while cur < to_dt and i < 4500:
            out.append({
                "time": cur.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                "complete": True,
                "volume": 100,
                "mid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": "1.1005"},
                "bid": {"c": "1.1004"},
                "ask": {"c": "1.1006"},
            })
            cur += step
            i += 1
        return out


def _parse(s):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def test_plan_pages_two_years_m15_count():
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    start = end - timedelta(days=2 * 365)
    pages = plan_pages(start, end, granularity="M15")
    # 2y * 365d * 24h * 60m / 15m = 70080 candles. 4500/page → ~16 pages.
    assert 12 <= len(pages) <= 20


def test_plan_pages_rejects_naive():
    with pytest.raises(ValueError):
        plan_pages(datetime(2024, 1, 1), datetime(2024, 1, 2), "M15")


def test_plan_pages_rejects_inverted():
    a = datetime(2024, 1, 1, tzinfo=timezone.utc)
    b = a - timedelta(days=1)
    with pytest.raises(ValueError):
        plan_pages(a, b, "M15")


def test_download_writes_pages_and_merged(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    client = _FakeClient(granularity_minutes=15)
    end = datetime(2024, 1, 15, tzinfo=timezone.utc)

    result = download_two_years(client, "EUR_USD", end, cache, granularity="M15")

    assert result["quality_report"]["total_bars"] > 0
    merged = result["merged_path"]
    assert merged.exists()
    # Quality report file is written next to merged
    qfile = merged.with_name("EUR_USD_M15_quality.json")
    assert qfile.exists()
    payload = json.loads(qfile.read_text("utf-8"))
    assert "report" in payload


def test_download_resumable(tmp_path: Path):
    """Second call should skip pages that already exist on disk."""
    cache = JsonlCache(tmp_path)
    client1 = _FakeClient()
    end = datetime(2024, 1, 15, tzinfo=timezone.utc)
    r1 = download_two_years(client1, "EUR_USD", end, cache, granularity="M15")
    written_first = r1["pages_written"]

    client2 = _FakeClient()
    r2 = download_two_years(client2, "EUR_USD", end, cache, granularity="M15")
    # Second pass: nothing new written, everything skipped.
    assert r2["pages_written"] == 0
    assert r2["pages_skipped"] == written_first


def test_download_rejects_naive_end_date(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    client = _FakeClient()
    with pytest.raises(ValueError):
        download_two_years(client, "EUR_USD", datetime(2024, 1, 1), cache)


def test_pagination_count(tmp_path: Path):
    """For M15 over 2y, we expect the documented ~16 pages count."""
    cache = JsonlCache(tmp_path)
    client = _FakeClient()
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    r = download_two_years(client, "EUR_USD", end, cache, granularity="M15")
    assert 12 <= (r["pages_written"] + r["pages_skipped"]) <= 20
