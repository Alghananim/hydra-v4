"""HYDRA V4 — read-only OANDA client.

Stdlib-only HTTP wrapper around the OANDA v20 REST API. Exposes ONLY
endpoints we need to read historical bars + instrument metadata.

CRITICAL — this client never places, modifies, or closes a trade.
Every order-shaped method (`submit_order`, `place_order`, `close_trade`,
`modify_trade`, `set_take_profit`, `set_stop_loss`) calls
`assert_no_live_order(...)` from `live_order_guard` and raises.

Why we built this from stdlib:
  * `oanda_v20` SDK includes order methods. Importing it gives an
    attacker / future-naive contributor a path to live trading.
  * We use only `urllib.request` (no `requests` dependency) so the
    surface is auditable.

Construction:
  OandaReadOnlyClient(token, account_id, env="practice")

The token is held in `self._token` (a private string). `__repr__`
deliberately does NOT include the token. Logging emits only the env
+ account_id-prefix (first 3 chars + asterisks).
"""

from __future__ import annotations

import functools
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from live_data.live_order_guard import assert_no_live_order

# H3: any method named here is wrapped with assert_no_live_order via
# __init_subclass__ — even if a subclass overrides one of these names,
# the wrapper is re-applied AFTER class creation. There is no caller-
# side bypass.
_BLOCKED_ORDER_METHODS = (
    "submit_order",
    "place_order",
    "close_trade",
    "modify_trade",
    "set_take_profit",
    "set_stop_loss",
    "cancel_order",
)


def _wrap_with_guard(method_name: str, original):
    """Wrap a callable so it always raises via assert_no_live_order
    BEFORE the original body runs."""

    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        assert_no_live_order(method_name)
        # Unreachable — assert_no_live_order ALWAYS raises in this phase.
        return original(self, *args, **kwargs)

    wrapper.__wrapped_by_live_order_guard__ = True  # marker for tests
    return wrapper

_log = logging.getLogger("live_data.oanda")

# Endpoint allowlist — anything else raises.
_ALLOWED_GET_PATTERNS = (
    "/v3/instruments/",       # /v3/instruments/{instrument}/candles
    "/v3/accounts/",          # only sub-paths /instruments and /summary
)

# Base URLs — practice vs live read endpoints. Live reads are required
# because the user runs against their real account's data feed.
_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

_TIMEOUT_SECONDS = 5.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds


class OandaError(RuntimeError):
    """Generic OANDA API failure."""


class OandaForbiddenEndpointError(RuntimeError):
    """Raised when caller tries to hit an endpoint outside the allowlist."""


def _short_account(account_id: str) -> str:
    if not account_id or len(account_id) < 4:
        return "***"
    return account_id[:3] + "*" * (len(account_id) - 3)


class OandaReadOnlyClient:
    """Read-only OANDA REST client.

    Public methods (READ ONLY):
      list_instruments() — /v3/accounts/{account_id}/instruments
      get_candles(instrument, granularity, count, from_time, to_time, price)
        → /v3/instruments/{instrument}/candles

    Order-shaped methods exist purely so adversarial code that tries
    them gets a loud, tested failure — they all raise via
    `assert_no_live_order`.
    """

    # Order-shaped method names we DELIBERATELY trap.
    _BLOCKED_METHODS = (
        "submit_order",
        "place_order",
        "close_trade",
        "modify_trade",
        "cancel_order",
        "set_take_profit",
        "set_stop_loss",
    )

    # Public alias used by the __init_subclass__ enforcer. Centralized so
    # red-team subclasses cannot bypass the wrapper by overriding only one.
    _BLOCKED_ORDER_METHODS = _BLOCKED_ORDER_METHODS

    def __init_subclass__(cls, **kwargs):
        """H3: re-wrap every blocked-order method on every subclass after
        class body executes. Even if a subclass binds
        ``submit_order = lambda self: 'DONE'``, this hook replaces that
        attribute with a wrapper that ALWAYS calls ``assert_no_live_order``
        first — and ``assert_no_live_order`` always raises in this phase.
        """
        super().__init_subclass__(**kwargs)
        for name in _BLOCKED_ORDER_METHODS:
            attr = cls.__dict__.get(name, None)
            if attr is None:
                # Not overridden in this subclass — the base method already
                # routes through assert_no_live_order; nothing to do.
                continue
            # Already wrapped? Skip.
            if getattr(attr, "__wrapped_by_live_order_guard__", False):
                continue
            if not callable(attr):
                # Non-callable override of a blocked name is itself suspicious;
                # replace with a guard that raises.
                setattr(cls, name, _wrap_with_guard(name, lambda self, *a, **k: None))
                continue
            setattr(cls, name, _wrap_with_guard(name, attr))

    def __init__(
        self,
        token: str,
        account_id: str,
        env: str = "practice",
        url_opener=None,
    ) -> None:
        if not isinstance(token, str) or len(token) < 8:
            raise ValueError("OANDA token missing or implausibly short")
        if not isinstance(account_id, str) or len(account_id) < 6:
            raise ValueError("OANDA account_id missing or implausibly short")
        if env not in _BASE_URLS:
            raise ValueError(f"env must be one of {list(_BASE_URLS)}")

        # Stored privately; never returned, never logged.
        self._token = token
        self._account_id = account_id
        self._env = env
        self._base_url = _BASE_URLS[env]
        # Allow tests to inject a fake opener.
        self._url_opener = url_opener or urllib.request.build_opener()
        _log.info(
            "OandaReadOnlyClient initialized env=%s account=%s",
            env,
            _short_account(account_id),
        )

    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"OandaReadOnlyClient(env={self._env!r}, "
            f"account={_short_account(self._account_id)!r})"
        )

    # ------------------------------------------------------------------
    # READ — instruments metadata
    def list_instruments(self) -> List[Dict[str, Any]]:
        path = f"/v3/accounts/{self._account_id}/instruments"
        data = self._get(path)
        return list(data.get("instruments", []))

    # ------------------------------------------------------------------
    # READ — candles (the bread and butter)
    def get_candles(
        self,
        instrument: str,
        granularity: str = "M15",
        count: Optional[int] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        price: str = "BAM",  # bid + ask + mid
    ) -> List[Dict[str, Any]]:
        """Fetch up to `count` candles, or a [from, to] range.

        The OANDA API caps a single response at 5000 candles. The
        higher-level data_loader handles pagination.
        """
        if not instrument:
            raise ValueError("instrument required")
        if granularity not in (
            "S5", "S10", "S15", "S30",
            "M1", "M2", "M4", "M5", "M10", "M15", "M30",
            "H1", "H2", "H3", "H4", "H6", "H8", "H12",
            "D", "W", "M",
        ):
            raise ValueError(f"granularity {granularity!r} not recognized")
        if price and not set(price).issubset(set("BAM")):
            raise ValueError("price must be a subset of {B, A, M}")

        params: Dict[str, str] = {
            "granularity": granularity,
            "price": price,
        }
        if count is not None:
            params["count"] = str(int(count))
        if from_time is not None:
            params["from"] = from_time
        if to_time is not None:
            params["to"] = to_time

        path = f"/v3/instruments/{instrument}/candles"
        data = self._get(path, params=params)
        return list(data.get("candles", []))

    # ------------------------------------------------------------------
    # All order-shaped methods refuse loudly.
    def submit_order(self, *args, **kwargs):
        assert_no_live_order("submit_order")

    def place_order(self, *args, **kwargs):
        assert_no_live_order("place_order")

    def close_trade(self, *args, **kwargs):
        assert_no_live_order("close_trade")

    def modify_trade(self, *args, **kwargs):
        assert_no_live_order("modify_trade")

    def cancel_order(self, *args, **kwargs):
        assert_no_live_order("cancel_order")

    def set_take_profit(self, *args, **kwargs):
        assert_no_live_order("set_take_profit")

    def set_stop_loss(self, *args, **kwargs):
        assert_no_live_order("set_stop_loss")

    # ------------------------------------------------------------------
    @classmethod
    def list_blocked_methods(cls) -> List[str]:
        return list(cls._BLOCKED_METHODS)

    @classmethod
    def list_read_methods(cls) -> List[str]:
        return ["list_instruments", "get_candles"]

    # ------------------------------------------------------------------
    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if not any(path.startswith(p) for p in _ALLOWED_GET_PATTERNS):
            raise OandaForbiddenEndpointError(
                f"endpoint {path!r} is outside the read-only allowlist"
            )
        # Forbid any account sub-path that's NOT /instruments or /summary —
        # specifically the trade/order sub-paths leak risk.
        if path.startswith("/v3/accounts/"):
            tail = path.split("/v3/accounts/", 1)[1]
            # tail looks like "{accountId}/instruments" or "{accountId}/orders"
            parts = tail.split("/", 2)
            # H5: enforce that the account_id segment matches the configured
            # account. Any other id (typo, attacker, buggy caller) is refused.
            if len(parts) >= 1 and parts[0] != self._account_id:
                raise OandaError(
                    f"account_id mismatch in path: expected configured id, got {parts[0]!r}"
                )
            if len(parts) >= 2 and parts[1] not in ("instruments", "summary"):
                raise OandaForbiddenEndpointError(
                    f"account sub-path {parts[1]!r} is forbidden"
                )

        qs = ""
        if params:
            qs = "?" + urllib.parse.urlencode(params)
        url = f"{self._base_url}{path}{qs}"

        # Last-ditch defense: bearer token only goes into Authorization header,
        # never into the URL. Header is purely outbound.
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept-Datetime-Format": "RFC3339",
                "Content-Type": "application/json",
            },
        )

        last_err: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                with self._url_opener.open(req, timeout=_TIMEOUT_SECONDS) as resp:
                    body = resp.read()
                    return json.loads(body.decode("utf-8"))
            except urllib.error.HTTPError as e:
                # 429 = rate limited → exponential backoff
                if e.code == 429 and attempt < _MAX_RETRIES - 1:
                    sleep_s = _BACKOFF_BASE * (2 ** attempt)
                    _log.warning(
                        "OANDA 429 rate-limit; retrying in %.2fs (attempt %d)",
                        sleep_s, attempt + 1,
                    )
                    time.sleep(sleep_s)
                    last_err = e
                    continue
                # 5xx → backoff once, then give up
                if 500 <= e.code < 600 and attempt < _MAX_RETRIES - 1:
                    sleep_s = _BACKOFF_BASE * (2 ** attempt)
                    time.sleep(sleep_s)
                    last_err = e
                    continue
                # H4: do NOT chain via `from e` — the original HTTPError
                # carries headers (potentially echoing x-api-key / token) and
                # a verbose reason string. Log only the integer status.
                _log.warning("OANDA HTTP error path=%s code=%s", path, getattr(e, "code", "?"))
                raise OandaError(f"HTTP {e.code} for {path}") from None
            except urllib.error.URLError as e:
                last_err = e
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue
                # H4: drop e.reason from the exception text — it can echo
                # request URL/headers in some error paths.
                _log.warning("OANDA URLError path=%s", path)
                raise OandaError(f"URLError for {path}") from None
        # Defensive — exhausted retries
        raise OandaError(f"exhausted retries for {path}: {last_err!r}")
