"""HYDRA V4 — anthropic_bridge / secret_redactor.

Thin wrapper around the SmartNoteBook V4 redactor + extra patterns:
  * OANDA account-id pattern: \\d{3}-\\d{3}-\\d{8}-\\d{3}
  * sk-ant-* (Anthropic-style) — already covered by sk- pattern but
    we ensure full token is replaced (not partial).

We delegate to `smartnotebook.v4.secret_redactor.redact` for the bulk
of patterns and add the OANDA account-id stripper on top so callers
do not accidentally embed account IDs into Anthropic prompts.
"""

from __future__ import annotations

import re

from smartnotebook.v4 import secret_redactor as _sn_redactor


_OANDA_ACCOUNT_RE = re.compile(r"\b\d{3}-\d{3}-\d{8}-\d{3}\b")
# Anthropic key form. The base sk- catches it; this is belt+braces.
_SK_ANT_RE = re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")

# Bearer header pattern (re-declared here for tests that import this module
# directly rather than the SN one).
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=:+/]{6,}")

_PLACEHOLDER = "[REDACTED]"


def redact(value):
    """Redact a Python object (dict/list/str). Defers to SN redactor first."""
    out = _sn_redactor.redact(value)
    # Then walk again to strip the Anthropic / OANDA account patterns
    # that the SN redactor may not handle (account ID specifically).
    return _post_redact(out)


def _post_redact(value):
    if isinstance(value, str):
        v = _OANDA_ACCOUNT_RE.sub(_PLACEHOLDER, value)
        v = _SK_ANT_RE.sub(_PLACEHOLDER, v)
        v = _BEARER_RE.sub(f"Bearer {_PLACEHOLDER}", v)
        return v
    if isinstance(value, dict):
        return {k: _post_redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_post_redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_post_redact(v) for v in value)
    return value


def assert_clean_for_anthropic(value) -> None:
    """Raise if any known secret pattern survives. Used as a final boundary
    check before the bridge sends `value` to the Anthropic API."""
    findings = []

    def walk(v):
        if isinstance(v, str):
            for rx, name in (
                (_OANDA_ACCOUNT_RE, "oanda_account"),
                (_SK_ANT_RE, "sk_ant"),
                (_BEARER_RE, "bearer"),
            ):
                if rx.search(v):
                    findings.append(name)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k in ("chain_hash", "prev_hash"):
                    continue
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    # Also defer to SN's stricter assertion
    _sn_redactor.assert_clean(value)
    if findings:
        raise RuntimeError(
            f"anthropic_bridge: secret patterns survived redaction: {findings}"
        )
