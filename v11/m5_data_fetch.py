"""HYDRA V11 — M5 cached data fetcher.

Builds a rolling 2-year cache of M5 bars for each pair in v11.pairs.PAIRS.
Output format mirrors data_cache/<PAIR>/M15/merged.jsonl (one JSON per
line, OANDA-shaped: time, complete, volume, bid, mid, ask).

This script does NOT call OANDA from the orchestrator. It is run
manually (or as a one-off CI job) to populate data_cache/<PAIR>/M5/
before V11 backtests. The orchestrator only reads cached files.

Runtime expectation:
  - 2 years × 6 pairs × 288 bars/day = ~1.26 M bars total
  - At ~250 bytes per JSON line = ~315 MB
  - Per-pair cache size: ~52 MB (well under Git LFS limits)

Usage (interactive, on a machine with OANDA practice creds in env):
  python -m v11.m5_data_fetch --output-dir data_cache --days 730
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from v11.pairs import all_pairs


def _build_paginated_endpoint(symbol: str, granularity: str,
                                from_iso: str, to_iso: str) -> str:
    """OANDA v20 candles endpoint shape — practice account."""
    base = "https://api-fxpractice.oanda.com"
    return (f"{base}/v3/instruments/{symbol}/candles"
            f"?granularity={granularity}&price=BMA&from={from_iso}&to={to_iso}")


def fetch_m5_paginated(symbol: str, *, start: datetime, end: datetime,
                        out_dir: Path, page_seconds: int = 4 * 24 * 3600) -> int:
    """Fetch M5 bars in pages of `page_seconds` (default 4 days each).

    Returns total bar count written. Files are saved per page first,
    then a separate `merged.jsonl` is composed at the end.

    Requires OANDA_API_TOKEN and OANDA_ACCOUNT_ID in env. The fetcher
    fails-CLOSED if creds are absent — caller decides what to do.
    """
    token = os.environ.get("OANDA_API_TOKEN")
    if not token:
        raise RuntimeError(
            "OANDA_API_TOKEN not set. M5 fetch requires practice token. "
            "Set the env var and retry."
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    import urllib.request
    import urllib.error

    cur = start
    total_bars = 0
    pages_written = 0
    while cur < end:
        page_end = min(cur + timedelta(seconds=page_seconds), end)
        from_iso = cur.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        to_iso = page_end.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        url = _build_paginated_endpoint(symbol, "M5", from_iso, to_iso)
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept-Datetime-Format": "RFC3339",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = json.loads(r.read().decode("utf-8"))
            candles = payload.get("candles", [])
            page_path = out_dir / f"page_{from_iso.replace(':', '-')}__{to_iso.replace(':', '-')}.jsonl"
            with page_path.open("w", encoding="utf-8") as f:
                for c in candles:
                    f.write(json.dumps(c) + "\n")
            total_bars += len(candles)
            pages_written += 1
            print(f"  {symbol} page {pages_written} {from_iso[:10]}-{to_iso[:10]} "
                  f"bars={len(candles)} cum={total_bars}")
        except urllib.error.HTTPError as e:
            print(f"  HTTPError {e.code} for {symbol} page {from_iso}: {e.reason}",
                  file=sys.stderr)
        time.sleep(0.4)  # polite rate limit
        cur = page_end

    # Build merged.jsonl from all page files, dedup by time, sort.
    seen = set()
    merged_rows = []
    for page in sorted(out_dir.glob("page_*.jsonl")):
        with page.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                t = rec.get("time")
                if t and t not in seen:
                    seen.add(t)
                    merged_rows.append(rec)
    merged_rows.sort(key=lambda r: r["time"])
    merged_path = out_dir / "merged.jsonl"
    with merged_path.open("w", encoding="utf-8") as f:
        for r in merged_rows:
            f.write(json.dumps(r) + "\n")
    print(f"  {symbol}: merged {len(merged_rows)} unique bars -> {merged_path}")
    return len(merged_rows)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=Path("data_cache"))
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--pair", default=None,
                   help="Single pair (default: all 6 V11 pairs)")
    args = p.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)
    pairs = (args.pair,) if args.pair else all_pairs()

    print(f"Fetching M5 for {len(pairs)} pair(s) from "
          f"{start.isoformat()} to {end.isoformat()}")
    grand_total = 0
    for sym in pairs:
        out = args.output_dir / sym / "M5"
        n = fetch_m5_paginated(sym, start=start, end=end, out_dir=out)
        grand_total += n
    print(f"Total bars cached across all pairs: {grand_total}")


if __name__ == "__main__":
    main()
