"""HYDRA V4 — live_data hardening regression tests.

Covers H1, H2, H3, H4, H5 fixes from the multi-reviewer + red-team pass.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from live_data.data_cache import (
    CacheCorruptError,
    JsonlCache,
    _validate_cached_candle,
)
from live_data.data_quality_checker import InvalidCandleError
from live_data.live_order_guard import LiveOrderAttemptError
from live_data.oanda_readonly_client import (
    OandaError,
    OandaForbiddenEndpointError,
    OandaReadOnlyClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ts(i, step_min=15):
    base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    t = base + timedelta(minutes=i * step_min)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")


def _candle(t, *, complete=True, volume=100, mid_c="1.1005"):
    return {
        "time": t,
        "complete": complete,
        "volume": volume,
        "mid": {"o": "1.1000", "h": "1.1010", "l": "1.0990", "c": mid_c},
        "bid": {"c": "1.1004"},
        "ask": {"c": "1.1006"},
    }


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeOpener:
    def __init__(self, payload: dict):
        self._payload = payload

    def open(self, req, timeout=None):
        return _FakeResponse(json.dumps(self._payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# H1: Inf/NaN must be rejected at the cache-write boundary (data_loader path)
# ---------------------------------------------------------------------------
def test_inf_volume_rejected_at_loader(tmp_path: Path):
    """A candle whose volume is 'Infinity' (or any non-finite numeric) must
    be REFUSED before it reaches disk — the cache write path is the loader's
    last barrier between OANDA garbage and replay."""
    cache = JsonlCache(tmp_path)
    bad = _candle(_ts(0))
    bad["volume"] = "Infinity"
    with pytest.raises(CacheCorruptError):
        cache.write_page("EUR_USD", "M15", _ts(0), _ts(1), [bad])


def test_nan_mid_close_rejected_at_loader(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    bad = _candle(_ts(0), mid_c="NaN")
    with pytest.raises(CacheCorruptError):
        cache.write_page("EUR_USD", "M15", _ts(0), _ts(1), [bad])


def test_neg_inf_bid_rejected_at_loader(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    bad = _candle(_ts(0))
    bad["bid"] = {"c": "-Infinity"}
    with pytest.raises(CacheCorruptError):
        cache.write_page("EUR_USD", "M15", _ts(0), _ts(1), [bad])


# ---------------------------------------------------------------------------
# H2: Cache poisoning — JSONL trust hardening
# ---------------------------------------------------------------------------
def _write_raw_page(cache: JsonlCache, pair, gran, from_iso, to_iso, lines):
    """Bypass write_page validation to plant a poisoned page on disk
    (simulates an attacker or buggy upstream that wrote bad JSONL)."""
    p = cache.page_path(pair, gran, from_iso, to_iso)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_cache_rejects_future_dated_candle(tmp_path: Path):
    """A 2099-dated candle planted in cache must raise CacheCorruptError
    on read — replay must NOT proceed with the poisoned data."""
    cache = JsonlCache(tmp_path)
    future_bar = _candle("2099-01-01T00:00:00.000000000Z")
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        [json.dumps(future_bar)],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_out_of_order_candles(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    # Plant two bars where the second precedes the first.
    bar_a = _candle(_ts(5))
    bar_b = _candle(_ts(2))  # earlier than bar_a — out of order!
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(10),
        [json.dumps(bar_a), json.dumps(bar_b)],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_duplicate_within_page(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    bar = _candle(_ts(1))
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(2),
        [json.dumps(bar), json.dumps(bar)],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_non_dict_record(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        ['"a string, not a dict"'],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_malformed_json(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        ['{"time": "2024-01-01T00:00:00Z" not valid json'],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_non_complete_record(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    bar = _candle(_ts(0), complete=False)
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        [json.dumps(bar)],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_rejects_missing_time(tmp_path: Path):
    cache = JsonlCache(tmp_path)
    bar = _candle(_ts(0))
    bar.pop("time")
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        [json.dumps(bar)],
    )
    with pytest.raises(CacheCorruptError):
        list(cache.iter_candles("EUR_USD", "M15"))


def test_cache_validate_false_skips_checks(tmp_path: Path):
    """Power-user opt-out flag: validate=False bypasses the schema/order
    checks. The poisoned candle is yielded as-is. This is a deliberate
    escape hatch for diagnostics, NOT used by the loader."""
    cache = JsonlCache(tmp_path)
    bar = _candle("2099-01-01T00:00:00.000000000Z")
    _write_raw_page(
        cache, "EUR_USD", "M15", _ts(0), _ts(1),
        [json.dumps(bar)],
    )
    out = list(cache.iter_candles("EUR_USD", "M15", validate=False))
    assert len(out) == 1


def test_cache_accepts_clean_data(tmp_path: Path):
    """Sanity — all the new validation must NOT reject good data."""
    cache = JsonlCache(tmp_path)
    bars = [_candle(_ts(i)) for i in range(10)]
    cache.write_page("EUR_USD", "M15", _ts(0), _ts(11), bars)
    out = list(cache.iter_candles("EUR_USD", "M15"))
    assert len(out) == 10


# ---------------------------------------------------------------------------
# H3: Subclass guard bypass
# ---------------------------------------------------------------------------
def test_subclass_cannot_bypass_guard():
    """A subclass overriding submit_order with a no-op MUST still raise
    LiveOrderAttemptError because __init_subclass__ re-wraps it."""

    class Evil(OandaReadOnlyClient):
        def submit_order(self, *args, **kwargs):  # type: ignore[override]
            return "DONE"  # attacker's payload — must NEVER run.

    c = Evil(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.submit_order(units=1_000_000)


def test_subclass_lambda_in_body_also_blocked():
    """A subclass that defines `submit_order = lambda...` in its body —
    a common red-team trick to dodge the override-method-name search —
    must still be re-wrapped by __init_subclass__."""

    class Evil3(OandaReadOnlyClient):
        place_order = lambda self, *a, **k: "BYPASSED"  # noqa: E731

    c = Evil3(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.place_order()


def test_subclass_overriding_all_blocked_methods_still_raises():
    class FullEvil(OandaReadOnlyClient):
        def submit_order(self, *a, **k): return "X"
        def place_order(self, *a, **k): return "X"
        def close_trade(self, *a, **k): return "X"
        def modify_trade(self, *a, **k): return "X"
        def set_take_profit(self, *a, **k): return "X"
        def set_stop_loss(self, *a, **k): return "X"
        def cancel_order(self, *a, **k): return "X"

    c = FullEvil(token="x" * 16, account_id="001-002-12345678-001")
    for m in ("submit_order", "place_order", "close_trade", "modify_trade",
              "set_take_profit", "set_stop_loss", "cancel_order"):
        with pytest.raises(LiveOrderAttemptError):
            getattr(c, m)()


def test_subclass_does_not_break_read_methods():
    """Read methods on subclasses must still work."""

    class GoodSubclass(OandaReadOnlyClient):
        pass

    fake = _FakeOpener({"candles": [{"time": "2024-01-01T00:00:00Z", "complete": True}]})
    c = GoodSubclass(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    out = c.get_candles("EUR_USD", count=1)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# H5: account_id segment validation
# ---------------------------------------------------------------------------
def test_get_rejects_other_account_path():
    """Passing /v3/accounts/<other-account>/instruments must be refused
    even though the path prefix is in the allowlist."""
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    with pytest.raises(OandaError):
        c._get("/v3/accounts/999-999-99999999-999/instruments")


def test_get_allows_own_account_instruments():
    fake = _FakeOpener({"instruments": []})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    # Should NOT raise.
    c._get("/v3/accounts/001-002-12345678-001/instruments")


def test_get_allows_v3_instruments_path_without_account_check():
    """The /v3/instruments/ path has no account segment — the H5 check
    must not fire for it."""
    fake = _FakeOpener({"candles": []})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    c._get("/v3/instruments/EUR_USD/candles", params={"granularity": "M15"})
