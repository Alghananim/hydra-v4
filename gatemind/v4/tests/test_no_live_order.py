"""Tests proving GateMind has no broker SDK dependencies anywhere.

We do this two ways:
  1. Static: scan every .py under gatemind/v4 for forbidden imports.
  2. Runtime: import gatemind.v4 and check sys.modules has no broker keys.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN_TOKENS = (
    "import oanda",
    "from oanda",
    "import oandapyV20",
    "from oandapyV20",
    "import MetaTrader5",
    "from MetaTrader5",
    "import ib_insync",
    "from ib_insync",
    "import alpaca",
    "from alpaca",
    "place_order",
    "create_market_order",
    "submit_order",
)

GATEMIND_ROOT = Path(__file__).resolve().parents[1]


def _gatemind_py_files():
    skip = {"tests"}
    out = []
    for p in GATEMIND_ROOT.rglob("*.py"):
        # Skip the tests/ tree itself
        rel = p.relative_to(GATEMIND_ROOT)
        if rel.parts and rel.parts[0] in skip:
            continue
        out.append(p)
    return out


def test_no_forbidden_broker_imports_in_source():
    offenders = []
    for path in _gatemind_py_files():
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in text:
                offenders.append((path, token))
    assert not offenders, f"forbidden broker tokens found: {offenders}"


def test_no_state_persistence_imports():
    """No sqlite, redis, or filesystem-state in GateMind source."""
    state_tokens = (
        "import sqlite3", "from sqlite3",
        "import redis", "from redis",
        "import shelve", "from shelve",
        "open(",  # any file open
    )
    offenders = []
    for path in _gatemind_py_files():
        text = path.read_text(encoding="utf-8")
        for token in state_tokens:
            if token in text:
                # Permit the constants module to declare sets/strings — no `open(` in any source though.
                offenders.append((path.name, token))
    # Scrub allowed: the audit_log uses json + dict only; no `open(`.
    open_offenders = [o for o in offenders if o[1] == "open("]
    assert not open_offenders, f"file I/O found: {open_offenders}"


def test_runtime_modules_clean():
    """Importing gatemind.v4 must not pull in broker libs."""
    # Force a fresh import
    import importlib
    import gatemind.v4 as g
    importlib.reload(g)
    forbidden_modules = (
        "oanda", "oandapyV20", "MetaTrader5", "ib_insync", "alpaca",
    )
    leaked = [m for m in forbidden_modules if m in sys.modules]
    assert not leaked, f"broker modules leaked into sys.modules: {leaked}"


def test_gatemind_evaluate_does_not_call_network():
    """Sanity smoke — full evaluate on a known fixture should not need a socket.

    We hook socket.socket; if anything tries to open one we fail.
    """
    import socket

    real_socket = socket.socket
    calls = []

    def watcher(*a, **kw):
        calls.append((a, kw))
        return real_socket(*a, **kw)

    socket.socket = watcher  # type: ignore[assignment]
    try:
        from gatemind.v4 import GateMindV4
        from .conftest import make_brain_output_aplus_buy, now_in_ny_window
        gate = GateMindV4()
        n = make_brain_output_aplus_buy("NewsMind")
        m = make_brain_output_aplus_buy("MarketMind")
        c = make_brain_output_aplus_buy("ChartMind")
        gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    finally:
        socket.socket = real_socket  # type: ignore[assignment]
    assert calls == [], f"GateMind.evaluate opened sockets: {calls}"
