"""HYDRA V4 — append-only JSONL cache for OANDA candle pages.

Layout on disk:

  cache_root/
    <pair>/
      <granularity>/
        page_<from_iso>__<to_iso>.jsonl   # one candle per line
        merged.jsonl                       # final concatenated file

Hard rules:
  * Every page write is atomic (write to .tmp, fsync, rename).
  * Pages are immutable once written; resume by skipping existing files.
  * Merged file is recreated from pages on demand (deterministic).
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


class CacheCorruptError(RuntimeError):
    """Raised when a cached candle fails schema/timestamp/order validation.
    The file on disk is treated as POISONED — replay must refuse to load it.
    """


# Allow up to 5 minutes of clock skew between writer and reader.
_FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)


def _safe_name(s: str) -> str:
    return s.replace(":", "-").replace("/", "_").replace(" ", "_")


def _parse_iso_time(s: str) -> Optional[datetime]:
    """Parse a candle 'time' string into tz-aware UTC datetime.
    Returns None on parse failure.
    """
    if not isinstance(s, str) or not s:
        return None
    try:
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
        else:
            s2 = s
        # OANDA produces nanosecond-precision strings: "...T00:00:00.000000000+00:00"
        # datetime.fromisoformat in <3.11 doesn't tolerate >6 fractional digits;
        # truncate the fractional component to 6 digits for safety.
        if "." in s2:
            head, tail = s2.split(".", 1)
            # tail looks like "000000000+00:00" — split off the tz part
            tz_idx = max(tail.find("+"), tail.find("-"))
            if tz_idx >= 0:
                frac, tz = tail[:tz_idx], tail[tz_idx:]
            else:
                frac, tz = tail, ""
            frac = frac[:6]
            s2 = f"{head}.{frac}{tz}"
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _validate_cached_candle(
    record: Any,
    page_path: Path,
    line_number: int,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Validate a single cached candle dict from disk.

    Enforces:
      * record is a dict
      * 'time' is ISO 8601 UTC parseable
      * time is NOT in the future (> now + 5min skew tolerance)
      * 'complete' is True (only finalized bars are cached)
      * 'volume' is integer-coercible and >= 0
      * 'mid.c' is finite float
    Raises CacheCorruptError on any violation.
    """
    if not isinstance(record, dict):
        raise CacheCorruptError(
            f"cache poisoned: non-dict record in {page_path.name} line {line_number}"
        )
    t = record.get("time")
    if not isinstance(t, str) or not t:
        raise CacheCorruptError(
            f"cache poisoned: missing/non-string time in {page_path.name} line {line_number}"
        )
    dt = _parse_iso_time(t)
    if dt is None:
        raise CacheCorruptError(
            f"cache poisoned: unparseable time {t!r} in {page_path.name} line {line_number}"
        )
    now = now_utc or datetime.now(timezone.utc)
    if dt > now + _FUTURE_SKEW_TOLERANCE:
        raise CacheCorruptError(
            f"cache poisoned: future-dated candle {t!r} (now={now.isoformat()}) "
            f"in {page_path.name} line {line_number}"
        )
    if record.get("complete") is not True:
        raise CacheCorruptError(
            f"cache poisoned: non-complete candle in {page_path.name} line {line_number}"
        )
    try:
        v = int(record.get("volume", 0))
    except (TypeError, ValueError) as e:
        raise CacheCorruptError(
            f"cache poisoned: bad volume in {page_path.name} line {line_number}: {e}"
        ) from None
    if v < 0:
        raise CacheCorruptError(
            f"cache poisoned: negative volume {v} in {page_path.name} line {line_number}"
        )
    mid = record.get("mid")
    if not isinstance(mid, dict) or "c" not in mid:
        raise CacheCorruptError(
            f"cache poisoned: missing mid.c in {page_path.name} line {line_number}"
        )
    try:
        c_val = float(mid["c"])
    except (TypeError, ValueError) as e:
        raise CacheCorruptError(
            f"cache poisoned: non-numeric mid.c in {page_path.name} line {line_number}: {e}"
        ) from None
    if not math.isfinite(c_val):
        raise CacheCorruptError(
            f"cache poisoned: non-finite mid.c={mid['c']!r} "
            f"in {page_path.name} line {line_number}"
        )
    return record


def _assert_candle_numeric_finite(candle: Any) -> None:
    """H1 cache-write barrier: refuse to persist a candle whose numeric
    fields contain NaN / +-Infinity / non-numeric strings like "NaN" /
    "Infinity". Raises CacheCorruptError so the page never reaches disk.
    """
    if not isinstance(candle, dict):
        raise CacheCorruptError(f"refusing to write non-dict candle: {type(candle).__name__}")
    # Volume — must be finite int-coercible.
    if "volume" in candle:
        v_raw = candle.get("volume")
        try:
            v = float(v_raw)
        except (TypeError, ValueError) as e:
            raise CacheCorruptError(
                f"refusing to write candle with non-numeric volume={v_raw!r}: {e}"
            ) from None
        if not math.isfinite(v):
            raise CacheCorruptError(
                f"refusing to write candle with non-finite volume={v_raw!r} "
                f"(time={candle.get('time')!r})"
            )
    # Numeric OHLC + spread fields, if present, under mid/bid/ask.
    for sub_key in ("mid", "bid", "ask"):
        sub = candle.get(sub_key)
        if not isinstance(sub, dict):
            continue
        for inner in ("o", "h", "l", "c"):
            if inner not in sub:
                continue
            try:
                fv = float(sub[inner])
            except (TypeError, ValueError) as e:
                raise CacheCorruptError(
                    f"refusing to write candle with non-numeric {sub_key}.{inner}="
                    f"{sub[inner]!r}: {e}"
                ) from None
            if not math.isfinite(fv):
                raise CacheCorruptError(
                    f"refusing to write candle with non-finite {sub_key}.{inner}="
                    f"{sub[inner]!r} (time={candle.get('time')!r})"
                )
    # Top-level spread, if any caller adds it.
    if "spread" in candle:
        try:
            sp = float(candle["spread"])
        except (TypeError, ValueError) as e:
            raise CacheCorruptError(
                f"refusing to write candle with non-numeric spread={candle['spread']!r}: {e}"
            ) from None
        if not math.isfinite(sp):
            raise CacheCorruptError(
                f"refusing to write candle with non-finite spread={candle['spread']!r}"
            )


def _assert_chronological_order(
    candles: List[Dict[str, Any]], page_path: Path
) -> None:
    """Raise CacheCorruptError if any candle's time is < the previous one.
    Equal timestamps (duplicates within a page) are also rejected.
    """
    prev: Optional[datetime] = None
    for idx, c in enumerate(candles):
        dt = _parse_iso_time(c.get("time", ""))
        if dt is None:
            # _validate_cached_candle should have caught this; defensive.
            raise CacheCorruptError(
                f"cache poisoned: unparseable time at line {idx + 1} of {page_path.name}"
            )
        if prev is not None and dt <= prev:
            raise CacheCorruptError(
                f"cache poisoned: out-of-order timestamp {c.get('time')!r} "
                f"<= previous {prev.isoformat()} at line {idx + 1} of {page_path.name}"
            )
        prev = dt


class JsonlCache:
    """Append-only JSONL cache. One sub-tree per (pair, granularity)."""

    def __init__(self, cache_root: Path | str) -> None:
        self._root = Path(cache_root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def page_path(self, pair: str, granularity: str, from_iso: str, to_iso: str) -> Path:
        sub = self._root / _safe_name(pair) / _safe_name(granularity)
        sub.mkdir(parents=True, exist_ok=True)
        fname = f"page_{_safe_name(from_iso)}__{_safe_name(to_iso)}.jsonl"
        return sub / fname

    def merged_path(self, pair: str, granularity: str) -> Path:
        sub = self._root / _safe_name(pair) / _safe_name(granularity)
        sub.mkdir(parents=True, exist_ok=True)
        return sub / "merged.jsonl"

    # ------------------------------------------------------------------
    def page_exists(self, pair: str, granularity: str, from_iso: str, to_iso: str) -> bool:
        p = self.page_path(pair, granularity, from_iso, to_iso)
        return p.exists() and p.stat().st_size > 0

    def write_page(
        self,
        pair: str,
        granularity: str,
        from_iso: str,
        to_iso: str,
        candles: Iterable[Dict],
    ) -> Path:
        target = self.page_path(pair, granularity, from_iso, to_iso)
        # Atomic write — temp file in same dir, fsync, rename.
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for c in candles:
                    # H1: refuse non-finite candles BEFORE they hit disk.
                    _assert_candle_numeric_finite(c)
                    f.write(json.dumps(c, ensure_ascii=True))
                    f.write("\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target

    # ------------------------------------------------------------------
    def list_pages(self, pair: str, granularity: str) -> List[Path]:
        sub = self._root / _safe_name(pair) / _safe_name(granularity)
        if not sub.exists():
            return []
        return sorted(sub.glob("page_*.jsonl"))

    def iter_candles(
        self,
        pair: str,
        granularity: str,
        validate: bool = True,
    ) -> Iterator[Dict]:
        """Iterate cached candles across all pages.

        H2: When ``validate=True`` (default), every candle is checked
        against ``_validate_cached_candle`` and each page is asserted
        chronologically ordered. ``CacheCorruptError`` is raised on the
        first violation — the cache is treated as poisoned and replay
        must NOT proceed.
        """
        for page in self.list_pages(pair, granularity):
            page_records: List[Dict[str, Any]] = []
            with page.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as e:
                        if validate:
                            raise CacheCorruptError(
                                f"cache poisoned: malformed JSON in {page.name} "
                                f"line {line_no}: {e}"
                            ) from None
                        continue
                    if validate:
                        _validate_cached_candle(rec, page, line_no)
                    page_records.append(rec)
            if validate:
                _assert_chronological_order(page_records, page)
            for rec in page_records:
                yield rec

    # ------------------------------------------------------------------
    def write_merged(self, pair: str, granularity: str) -> Path:
        """Concatenate all pages into merged.jsonl, sorted + deduped by time."""
        seen = set()
        rows: List[Dict] = []
        for c in self.iter_candles(pair, granularity):
            t = c.get("time")
            if not t or t in seen:
                continue
            seen.add(t)
            rows.append(c)
        rows.sort(key=lambda c: c["time"])

        target = self.merged_path(pair, granularity)
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for c in rows:
                    f.write(json.dumps(c, ensure_ascii=True))
                    f.write("\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target
