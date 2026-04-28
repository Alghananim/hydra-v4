"""HYDRA V4 — 2-year historical data loader.

Pages OANDA's 5000-candle limit by walking the [start, end] window in
fixed time chunks per granularity. Each chunk is cached as a JSONL
page so re-runs resume instantly.

Public surface:
  download_two_years(client, pair, end_date, cache, granularity="M15")
    → Path to merged JSONL + dict quality report

Hard rules:
  * `end_date` must be tz-aware UTC.
  * Pages are deterministic (same window → same filename).
  * If a page already exists, it is skipped (resumability).
  * Quality is computed over the merged file.
  * The quality report is written to disk next to merged.jsonl.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from live_data.data_cache import JsonlCache
from live_data.data_quality_checker import check_quality, is_acceptable
from live_data.oanda_readonly_client import OandaReadOnlyClient

_log = logging.getLogger("live_data.loader")


# Per-granularity, how much wall time fits in 5000 candles (with a
# generous 10% safety margin so we never blow the API limit).
_PAGE_SPAN = {
    "M1":  timedelta(minutes=1 * 4500),
    "M5":  timedelta(minutes=5 * 4500),
    "M15": timedelta(minutes=15 * 4500),
    "M30": timedelta(minutes=30 * 4500),
    "H1":  timedelta(hours=1 * 4500),
    "H4":  timedelta(hours=4 * 4500),
    "D":   timedelta(days=4500),
}


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("datetime must be tz-aware UTC")
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def plan_pages(
    start_utc: datetime,
    end_utc: datetime,
    granularity: str = "M15",
) -> List[Tuple[datetime, datetime]]:
    """Build the deterministic [from, to] pairs for pagination."""
    if granularity not in _PAGE_SPAN:
        raise ValueError(f"granularity {granularity!r} not supported here")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("start_utc, end_utc must be tz-aware UTC")
    if start_utc >= end_utc:
        raise ValueError("start_utc must be < end_utc")

    span = _PAGE_SPAN[granularity]
    pages: List[Tuple[datetime, datetime]] = []
    cur = start_utc
    while cur < end_utc:
        nxt = min(cur + span, end_utc)
        pages.append((cur, nxt))
        cur = nxt
    return pages


def download_two_years(
    client: OandaReadOnlyClient,
    pair: str,
    end_date: datetime,
    cache: JsonlCache,
    granularity: str = "M15",
    price: str = "BAM",
) -> Dict[str, object]:
    """Download a 2-year window ending at `end_date`.

    Returns a dict:
      {
        "pair": str,
        "granularity": str,
        "merged_path": Path,
        "pages_written": int,
        "pages_skipped": int,
        "quality_report": dict,
        "quality_ok": bool,
        "quality_reasons": List[str],
      }
    """
    if end_date.tzinfo is None:
        raise ValueError("end_date must be tz-aware UTC")
    end_utc = end_date.astimezone(timezone.utc)
    start_utc = end_utc - timedelta(days=2 * 365)
    pages = plan_pages(start_utc, end_utc, granularity)

    written = 0
    skipped = 0
    for (a, b) in pages:
        a_iso = _to_iso(a)
        b_iso = _to_iso(b)
        if cache.page_exists(pair, granularity, a_iso, b_iso):
            skipped += 1
            continue
        candles = client.get_candles(
            instrument=pair,
            granularity=granularity,
            from_time=a_iso,
            to_time=b_iso,
            price=price,
        )
        # Filter out incomplete candles (OANDA's last bar is mid-formation in
        # real-time fetches). The cache validator rejects non-complete candles,
        # so we drop them before write — they're not useful for backtest anyway.
        complete_candles = [c for c in candles if c.get("complete", False)]
        dropped_incomplete = len(candles) - len(complete_candles)
        cache.write_page(pair, granularity, a_iso, b_iso, complete_candles)
        written += 1
        _log.info(
            "wrote page pair=%s gran=%s window=%s..%s candles=%d (dropped_incomplete=%d)",
            pair, granularity, a_iso[:10], b_iso[:10], len(complete_candles), dropped_incomplete,
        )

    merged = cache.write_merged(pair, granularity)
    # Read deduped+sorted candles from merged.jsonl (NOT iter_candles, which
    # yields per-page and includes overlap duplicates at page boundaries).
    all_candles: List[Dict[str, object]] = []
    with merged.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            all_candles.append(json.loads(line))
    report = check_quality(all_candles, pair=pair, granularity=granularity)
    ok, reasons = is_acceptable(report)

    # Write the quality report next to merged.jsonl
    qpath = merged.with_name(f"{pair}_{granularity}_quality.json")
    qpath.write_text(
        json.dumps({"report": report, "ok": ok, "reasons": reasons}, indent=2),
        encoding="utf-8",
    )

    return {
        "pair": pair,
        "granularity": granularity,
        "merged_path": merged,
        "pages_written": written,
        "pages_skipped": skipped,
        "quality_report": report,
        "quality_ok": ok,
        "quality_reasons": reasons,
    }
