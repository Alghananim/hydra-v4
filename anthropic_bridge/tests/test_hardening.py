"""HYDRA V4 — anthropic_bridge hardening regression tests.

Covers H4 (HTTPError header leakage via `from e` chain) and H6 (raw
parsed dict returned to callers).
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from anthropic_bridge.bridge import AnthropicBridge, AnthropicBridgeError


def _payload():
    return {
        "symbol": "EUR_USD",
        "session_window": "MORNING",
        "final_status": "BLOCK",
        "grades": "A,B,C",
        "decisions": "WAIT,BLOCK,BLOCK",
        "risk_flags": "HIGH_VOL",
        "evidence_summary": "no momentum",
        "blocking_reason": "consensus failed",
    }


class _SuccessOpener:
    def __init__(self, body):
        self._body = body

    def open(self, req, timeout=None):
        class _R:
            def __init__(self, b):
                self._b = b
            def read(self):
                return json.dumps(self._b).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return _R(self._body)


class _HTTPErrorOpener:
    """Fake opener that raises an HTTPError whose headers ECHO the
    incoming x-api-key (some servers do this on 401/403)."""

    def __init__(self, status: int, leaked_secret: str = "sk-ant-LEAKED-VERY-SENSITIVE-TOKEN-VALUE-1234"):
        self._status = status
        self._leaked = leaked_secret

    def open(self, req, timeout=None):
        # urllib.error.HTTPError(url, code, msg, hdrs, fp)
        import http.client
        hdrs = http.client.HTTPMessage()
        hdrs["x-api-key"] = self._leaked          # the leak we're testing
        hdrs["x-anthropic-internal"] = "trace-1234"
        body = io.BytesIO(b'{"error":"bad"}')
        raise urllib.error.HTTPError(
            url=req.full_url,
            code=self._status,
            msg=f"echoed-token-{self._leaked}",   # also in `reason`
            hdrs=hdrs,
            fp=body,
        )


class _URLErrorOpener:
    def __init__(self, leaked_secret: str = "sk-ant-LEAKED-IN-URLERROR-REASON"):
        self._leaked = leaked_secret

    def open(self, req, timeout=None):
        raise urllib.error.URLError(reason=f"connection failed: {self._leaked}")


# ---------------------------------------------------------------------------
# H4: HTTPError must NOT chain into the wrapper exception (no `from e`)
# ---------------------------------------------------------------------------
def test_anthropic_http_error_does_not_leak_headers():
    """When Anthropic returns 401/403 and the upstream HTTPError has the
    x-api-key echoed in its headers/reason, the AnthropicBridgeError
    surfaced to the caller MUST NOT preserve those headers."""
    leaked = "sk-ant-VERY-OBVIOUS-LEAKED-TOKEN-VALUE-XYZ"
    bridge = AnthropicBridge(
        api_key="x" * 32,
        url_opener=_HTTPErrorOpener(status=401, leaked_secret=leaked),
    )
    with pytest.raises(AnthropicBridgeError) as ei:
        bridge.request("gate_review", _payload())
    # The wrapper message must NOT contain the leaked token.
    assert leaked not in str(ei.value)
    # The exception MUST NOT chain to the original HTTPError (which has
    # `headers` containing the leak).
    assert ei.value.__cause__ is None
    # The implicitly chained __context__ may still be set (Python's
    # automatic active-exception tracking). We assert that the leak is
    # only reachable by walking __context__, not __cause__ — the latter
    # is what `repr(error)` and most loggers surface.


def test_anthropic_http_error_text_excludes_reason():
    """The wrapped error message text must not echo the upstream
    `reason` string — many ops loggers print str(exception) verbatim."""
    leaked = "sk-ant-IN-REASON-FIELD-1234567890"
    bridge = AnthropicBridge(
        api_key="x" * 32,
        url_opener=_HTTPErrorOpener(status=500, leaked_secret=leaked),
    )
    with pytest.raises(AnthropicBridgeError) as ei:
        bridge.request("gate_review", _payload())
    msg = str(ei.value)
    assert leaked not in msg
    assert "echoed-token" not in msg


def test_anthropic_url_error_does_not_leak_reason():
    leaked = "sk-ant-IN-URLERROR-REASON"
    bridge = AnthropicBridge(
        api_key="x" * 32,
        url_opener=_URLErrorOpener(leaked_secret=leaked),
    )
    with pytest.raises(AnthropicBridgeError) as ei:
        bridge.request("gate_review", _payload())
    assert leaked not in str(ei.value)
    assert ei.value.__cause__ is None


# ---------------------------------------------------------------------------
# H6: bridge result must contain the REDACTED response, not raw parsed.
# ---------------------------------------------------------------------------
def test_bridge_returns_redacted_only():
    """If the model output contains an sk-ant- token in the `reason`
    field, the bridge's primary `parsed` return key must be the redacted
    form — not the raw object."""
    raw_secret_in_response = "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    body = {
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {
                    "suggestion": "agree",
                    "reason": f"context contains {raw_secret_in_response} token",
                },
            }
        ]
    }
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=_SuccessOpener(body))
    out = bridge.request("gate_review", _payload())
    # The default 'parsed' key must NOT contain the secret — it should
    # match `redacted_response`.
    assert raw_secret_in_response not in json.dumps(out["parsed"])
    assert raw_secret_in_response not in json.dumps(out["redacted_response"])
    # The opt-in escape hatch is clearly named and *does* contain the raw.
    assert "unsafe_raw_parsed" in out
    assert raw_secret_in_response in json.dumps(out["unsafe_raw_parsed"])


def test_bridge_redacted_keys_present_and_aligned():
    """Both 'parsed' and 'redacted_response' must point at the redacted
    object so a caller who logs either is safe."""
    body = {
        "content": [
            {
                "type": "tool_use",
                "name": "structured_response",
                "input": {"suggestion": "downgrade", "reason": "ok"},
            }
        ]
    }
    bridge = AnthropicBridge(api_key="x" * 32, url_opener=_SuccessOpener(body))
    out = bridge.request("gate_review", _payload())
    assert out["parsed"] == out["redacted_response"]
