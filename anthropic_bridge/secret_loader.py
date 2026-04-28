"""HYDRA V4 — anthropic_bridge / secret_loader.

Reads `ANTHROPIC_API_KEY`, `OANDA_API_TOKEN`, `OANDA_ACCOUNT_ID` from
the environment. Never prints, never logs, never returns to a caller
in a form that's easy to log accidentally.

Usage:
  k = load_anthropic_key()  # raises SecretNotConfiguredError if missing
  t, acc = load_oanda_credentials()

The functions return *plain strings* but are intentionally short — the
contract is that callers immediately hand them to the relevant
client constructor (which keeps them in a private attribute) and never
themselves log them.
"""

from __future__ import annotations

import os


class SecretNotConfiguredError(RuntimeError):
    """Raised when a required secret is missing from the environment."""


def load_anthropic_key() -> str:
    v = os.environ.get("ANTHROPIC_API_KEY", "")
    if not v:
        raise SecretNotConfiguredError(
            "ANTHROPIC_API_KEY env var is not set. Set it in your .env "
            "(loaded out-of-band) before running the bridge."
        )
    return v


def load_oanda_credentials() -> tuple[str, str]:
    t = os.environ.get("OANDA_API_TOKEN", "")
    acc = os.environ.get("OANDA_ACCOUNT_ID", "")
    if not t:
        raise SecretNotConfiguredError("OANDA_API_TOKEN env var is not set.")
    if not acc:
        raise SecretNotConfiguredError("OANDA_ACCOUNT_ID env var is not set.")
    return t, acc


def have_anthropic() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def have_oanda() -> bool:
    return bool(os.environ.get("OANDA_API_TOKEN")) and bool(
        os.environ.get("OANDA_ACCOUNT_ID")
    )
