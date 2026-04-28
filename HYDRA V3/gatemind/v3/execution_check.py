# -*- coding: utf-8 -*-
"""Execution / broker safety check.

PAIR_STATUS enforced strictly:
   production → live trading allowed
   monitoring → paper-only (NEVER live)
   disabled   → never any trading

FIX #3B: PAIR_STATUS is now read from engine.v3.validation_config so there
is exactly ONE source of truth for pair status across the codebase.
"""
from __future__ import annotations
from typing import Optional


def _get_pair_status(pair: str) -> str:
    """Read PAIR_STATUS from validation_config (single source of truth).

    Falls back to the historical local mapping if validation_config is
    not importable (defensive — the import should always succeed).
    """
    try:
        from engine.v3 import validation_config as _vc    # type: ignore
        # validation_config exposes pair_status through a default_factory
        # on the dataclass; the canonical attribute is PAIR_STATUS (set
        # at module load below for back-compat) or the dataclass default.
        pair_status_map = getattr(_vc, "PAIR_STATUS", None)
        if pair_status_map is None:
            from engine.v3.validation_config import ValidationConfig
            pair_status_map = ValidationConfig().pair_status
        return pair_status_map.get(pair, "unknown")
    except Exception:
        # Defensive fallback (should never trigger)
        return _LOCAL_FALLBACK.get(pair, "unknown")


# Defensive fallback only — NOT the source of truth
_LOCAL_FALLBACK = {
    "EUR/USD": "production",
    "USD/JPY": "monitoring",
    "GBP/USD": "disabled",
}


def check(*, pair: str, broker_mode: str, live_enabled: bool,
          spread_pips: float, max_spread_pips: float,
          slippage_pips: float, max_slippage_pips: float) -> dict:
    pair_status = _get_pair_status(pair)
    if pair_status == "disabled":
        return {"status": "disabled_pair", "pair_status": "disabled",
                "details": f"pair_{pair}_disabled"}
    if pair_status == "unknown":
        return {"status": "unknown_pair", "pair_status": "unknown",
                "details": f"pair_{pair}_not_in_PAIR_STATUS"}

    # Broker mode validation (FIX #3B: practice == paper, both non-live)
    if broker_mode not in ("practice", "paper", "live", "sandbox"):
        return {"status": "broker_unsafe", "pair_status": pair_status,
                "details": f"broker_mode_unknown:{broker_mode}"}

    # monitoring: live mode is hard-blocked
    if pair_status == "monitoring" and broker_mode == "live" and live_enabled:
        return {"status": "monitoring_pair_live_blocked",
                "pair_status": "monitoring",
                "details": f"pair_monitoring_cannot_go_live"}

    # spread
    if spread_pips is None or spread_pips < 0:
        return {"status": "spread_unknown", "pair_status": pair_status,
                "details": "spread_invalid"}
    if spread_pips > max_spread_pips:
        return {"status": "spread_too_wide", "pair_status": pair_status,
                "details": f"spread={spread_pips:.2f}>max={max_spread_pips:.2f}"}

    # slippage
    if slippage_pips is None or slippage_pips < 0:
        return {"status": "slippage_unknown", "pair_status": pair_status,
                "details": "slippage_invalid"}
    if slippage_pips > max_slippage_pips:
        return {"status": "slippage_too_high", "pair_status": pair_status,
                "details": f"slippage={slippage_pips:.2f}>max={max_slippage_pips:.2f}"}

    return {"status": "ok", "pair_status": pair_status,
            "details": f"pair={pair_status} broker={broker_mode} spread={spread_pips:.2f}"}
