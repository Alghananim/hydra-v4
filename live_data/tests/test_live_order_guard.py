"""Tests for LIVE_ORDER_GUARD.

We are paranoid here on purpose. The guard is the single thing
between this codebase and a real-money order.
"""

from __future__ import annotations

import importlib

import pytest

from live_data import live_order_guard
from live_data.live_order_guard import (
    LIVE_ORDER_GUARD_ACTIVE,
    LiveOrderAttemptError,
    assert_no_live_order,
    is_active,
)


def test_live_order_guard_active_by_default():
    assert LIVE_ORDER_GUARD_ACTIVE is True
    assert is_active() is True


def test_assert_no_live_order_raises():
    with pytest.raises(LiveOrderAttemptError):
        assert_no_live_order("submit_order")


def test_assert_no_live_order_message_includes_op_name():
    with pytest.raises(LiveOrderAttemptError) as ei:
        assert_no_live_order("place_order_for_million_lots")
    assert "place_order_for_million_lots" in str(ei.value)
    assert "LIVE_ORDER_GUARD" in str(ei.value)


def test_guard_cannot_be_disabled_at_runtime():
    """Adversarial: monkey-patch the module global to False; guard MUST still raise."""
    original = live_order_guard.LIVE_ORDER_GUARD_ACTIVE
    try:
        live_order_guard.LIVE_ORDER_GUARD_ACTIVE = False
        # Even with the public flag off, _GUARD_BURNED_IN keeps it active.
        with pytest.raises(LiveOrderAttemptError):
            assert_no_live_order("submit_order")
    finally:
        live_order_guard.LIVE_ORDER_GUARD_ACTIVE = original


def test_guard_cannot_be_disabled_via_setattr():
    """Adversarial: setattr both flags to False — the function must STILL raise."""
    original_active = live_order_guard.LIVE_ORDER_GUARD_ACTIVE
    original_burned = live_order_guard._GUARD_BURNED_IN
    try:
        setattr(live_order_guard, "LIVE_ORDER_GUARD_ACTIVE", False)
        setattr(live_order_guard, "_GUARD_BURNED_IN", False)
        # Even with BOTH module flags off, we expect the guard to raise per
        # the function body which always raises in this phase.
        with pytest.raises(LiveOrderAttemptError):
            assert_no_live_order("submit_order")
    finally:
        live_order_guard.LIVE_ORDER_GUARD_ACTIVE = original_active
        live_order_guard._GUARD_BURNED_IN = original_burned


def test_reimport_resets_flag_to_true():
    importlib.reload(live_order_guard)
    assert live_order_guard.LIVE_ORDER_GUARD_ACTIVE is True
    assert live_order_guard._GUARD_BURNED_IN is True


def test_submit_order_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.submit_order(units=1)


def test_place_order_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.place_order(side="BUY", units=10)


def test_close_trade_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.close_trade(trade_id="abc")


def test_modify_trade_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.modify_trade(trade_id="abc", new_sl=1.0)


def test_set_take_profit_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.set_take_profit(trade_id="abc", price=1.2345)


def test_set_stop_loss_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.set_stop_loss(trade_id="abc", price=1.2345)


def test_cancel_order_via_client_raises():
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    c = OandaReadOnlyClient(token="x" * 16, account_id="001-002-12345678-001")
    with pytest.raises(LiveOrderAttemptError):
        c.cancel_order(order_id="abc")


def test_blocked_methods_listed():
    """The list of blocked methods is enumerable for audits."""
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    blocked = OandaReadOnlyClient.list_blocked_methods()
    for needed in ("submit_order", "place_order", "close_trade", "modify_trade"):
        assert needed in blocked, f"{needed} must be in the blocked-method list"


def test_read_methods_only_two():
    """The whitelist of read methods is short and known."""
    from live_data.oanda_readonly_client import OandaReadOnlyClient
    reads = OandaReadOnlyClient.list_read_methods()
    assert sorted(reads) == ["get_candles", "list_instruments"]
