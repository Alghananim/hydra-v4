"""Mock-based tests for OandaReadOnlyClient.

We never call the real API. We inject a fake `url_opener` that returns
canned JSON.
"""

from __future__ import annotations

import io
import json
from contextlib import contextmanager

import pytest

from live_data.oanda_readonly_client import (
    OandaError,
    OandaForbiddenEndpointError,
    OandaReadOnlyClient,
)


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
    def __init__(self, payload: dict, recorder=None):
        self._payload = payload
        self._recorder = recorder if recorder is not None else []

    def open(self, req, timeout=None):
        self._recorder.append({"url": req.full_url, "headers": dict(req.headers)})
        return _FakeResponse(json.dumps(self._payload).encode("utf-8"))


def test_constructor_rejects_bad_token():
    with pytest.raises(ValueError):
        OandaReadOnlyClient(token="short", account_id="001-002-12345678-001")


def test_constructor_rejects_bad_account():
    with pytest.raises(ValueError):
        OandaReadOnlyClient(token="x" * 16, account_id="abc")


def test_repr_does_not_leak_token():
    c = OandaReadOnlyClient(token="SECRET_TOKEN_VALUE_x" * 2, account_id="001-002-12345678-001")
    r = repr(c)
    assert "SECRET_TOKEN_VALUE" not in r
    assert "001*" in r or "001-002" not in r  # masked, not full


def test_get_candles_uses_correct_endpoint():
    rec = []
    fake = _FakeOpener({"candles": [{"time": "2024-01-01T00:00:00Z", "complete": True}]}, rec)
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    out = c.get_candles("EUR_USD", granularity="M15", count=5)
    assert len(out) == 1
    assert "/v3/instruments/EUR_USD/candles" in rec[0]["url"]
    assert "granularity=M15" in rec[0]["url"]


def test_list_instruments_endpoint():
    rec = []
    fake = _FakeOpener({"instruments": [{"name": "EUR_USD"}, {"name": "USD_JPY"}]}, rec)
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    out = c.list_instruments()
    assert {i["name"] for i in out} == {"EUR_USD", "USD_JPY"}
    assert "/v3/accounts/001-002-12345678-001/instruments" in rec[0]["url"]


def test_orders_endpoint_blocked():
    """Even via the underlying _get path, account/orders is forbidden."""
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    with pytest.raises(OandaForbiddenEndpointError):
        c._get("/v3/accounts/001-002-12345678-001/orders")


def test_trades_endpoint_blocked():
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    with pytest.raises(OandaForbiddenEndpointError):
        c._get("/v3/accounts/001-002-12345678-001/trades")


def test_random_endpoint_blocked():
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(
        token="x" * 16,
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    with pytest.raises(OandaForbiddenEndpointError):
        c._get("/v3/something/totally/bogus")


def test_authorization_header_present():
    rec = []
    fake = _FakeOpener({"candles": []}, rec)
    c = OandaReadOnlyClient(
        token="MY_TOKEN_VAL_xxxxxxxxx",
        account_id="001-002-12345678-001",
        url_opener=fake,
    )
    c.get_candles("EUR_USD", count=1)
    auth = rec[0]["headers"].get("Authorization", "")
    assert auth.startswith("Bearer ")


def test_invalid_granularity():
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001", url_opener=fake)
    with pytest.raises(ValueError):
        c.get_candles("EUR_USD", granularity="ZZZ")


def test_price_param_validation():
    fake = _FakeOpener({})
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001", url_opener=fake)
    with pytest.raises(ValueError):
        c.get_candles("EUR_USD", price="XYZ")
