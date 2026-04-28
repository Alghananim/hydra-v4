"""HYDRA V4 — anthropic_bridge.

Secure JSON-only conduit to the Anthropic Messages API. Schema-locked
prompts, redacted logs, no upgrade authority.
"""

from __future__ import annotations

__all__ = [
    "bridge",
    "prompt_templates",
    "response_validator",
    "secret_loader",
    "secret_redactor",
]
