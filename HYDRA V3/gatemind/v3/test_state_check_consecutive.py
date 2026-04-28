# -*- coding: utf-8 -*-
"""FIX #2B — state_check honours configurable consecutive_losses_limit.

Before this fix, state_check.check hardcoded ``>= 3`` while
ValidationConfig.consecutive_losses_limit defaulted to 2 → two sources of
truth.  Now the limit is a parameter (default 3 for back-compat) and
GateMindV3 reads it from SystemState.consecutive_losses_limit.
"""
from __future__ import annotations
import sys, pathlib
from datetime import datetime, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gatemind.v3 import SystemState
from gatemind.v3 import state_check


NOW = datetime(2026, 4, 27, 13, 30, 0, tzinfo=timezone.utc)


def _state(*, consecutive_losses: int, limit: int = 3):
    return SystemState(
        pair="EUR/USD", broker_mode="paper", live_enabled=False,
        spread_pips=0.5, max_spread_pips=2.0,
        expected_slippage_pips=0.3, max_slippage_pips=2.0,
        daily_loss_pct=0.0, daily_loss_limit_pct=2.0,
        trades_today=0, daily_trade_limit=5,
        consecutive_losses=consecutive_losses,
        consecutive_losses_limit=limit,
        pair_status="production",
    )


def test_limit_2_blocks_at_2_losses():
    s = _state(consecutive_losses=2, limit=2)
    out = state_check.check(s, NOW, consecutive_losses_limit=2)
    assert "cooldown" in out["position_state"], f"got {out}"
    assert "2" in out["details"]


def test_limit_2_allows_at_1_loss():
    s = _state(consecutive_losses=1, limit=2)
    out = state_check.check(s, NOW, consecutive_losses_limit=2)
    # 1 < 2, so we fall through to flat
    assert out["position_state"] == "flat", f"got {out}"


def test_limit_3_does_not_block_at_2_losses():
    """Old default behaviour: 3 = legacy hardcoded threshold."""
    s = _state(consecutive_losses=2, limit=3)
    out = state_check.check(s, NOW, consecutive_losses_limit=3)
    assert out["position_state"] == "flat", f"got {out}"


def test_limit_3_blocks_at_3_losses():
    s = _state(consecutive_losses=3, limit=3)
    out = state_check.check(s, NOW, consecutive_losses_limit=3)
    assert "cooldown" in out["position_state"]
    assert "3" in out["details"]


def test_default_param_is_3_for_backcompat():
    """Callers that don't pass consecutive_losses_limit must still see
    the legacy ``>= 3`` behaviour."""
    s = _state(consecutive_losses=2, limit=2)    # state limit ignored
    out = state_check.check(s, NOW)              # no kwarg => default 3
    assert out["position_state"] == "flat"

    s2 = _state(consecutive_losses=3, limit=2)
    out2 = state_check.check(s2, NOW)
    assert "cooldown" in out2["position_state"]


def test_gatemind_propagates_state_limit():
    """GateMindV3 should pass state.consecutive_losses_limit through.

    Smoke test: with limit=2 and consecutive_losses=2, the state-check
    stage should mark position_state as a cooldown variant (not flat).
    """
    from gatemind.v3 import GateMindV3, BrainSummary

    state = _state(consecutive_losses=2, limit=2)
    gm = GateMindV3(strict_mode=True)
    news = BrainSummary("news", "allow", "A", 0.9, "bullish", "x")
    market = BrainSummary("market", "allow", "A", 0.9, "long", "x")
    chart = BrainSummary("chart", "allow", "A", 0.9, "uptrend", "x")
    d = gm.decide(
        pair="EUR/USD", news=news, market=market, chart=chart,
        state=state,
        entry_price=1.10, stop_loss=1.099, take_profit=1.102,
        atr=0.0005, now_utc=NOW,
    )
    # With 2 consecutive losses and limit=2 (cooldown active), position
    # state must NOT be flat.
    assert d.position_state_status != "flat", (
        f"GateMind ignored the configured limit; status={d.position_state_status}")


if __name__ == "__main__":
    for fn in (test_limit_2_blocks_at_2_losses,
               test_limit_2_allows_at_1_loss,
               test_limit_3_does_not_block_at_2_losses,
               test_limit_3_blocks_at_3_losses,
               test_default_param_is_3_for_backcompat,
               test_gatemind_propagates_state_limit):
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}"); sys.exit(1)
    print("ALL PASS")
