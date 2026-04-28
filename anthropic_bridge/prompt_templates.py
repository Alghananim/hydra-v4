"""HYDRA V4 — anthropic_bridge / prompt_templates.

Named, schema-locked prompt templates. Inline prompts are forbidden;
callers reference templates by name. Templates are immutable — they
cannot be edited at runtime via mutation.

Templates currently registered:
  * `gate_review` — given a GateMind-style decision, ask Claude to
    review and return one of {agree, downgrade, block}. Claude has NO
    upgrade authority.

Each template has:
  name: str
  system: str — the system message
  user_template: str — Python str.format() template; placeholders are
    replaced from the payload. Curly braces in the body that aren't
    placeholders must be doubled.
  output_schema: dict — JSON-schema-ish spec of the expected response.
"""

from __future__ import annotations

import string
from typing import Any, Dict


GATE_REVIEW_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["suggestion", "reason"],
    "properties": {
        "suggestion": {
            "type": "string",
            "enum": ["agree", "downgrade", "block"],
        },
        "reason": {"type": "string", "minLength": 4, "maxLength": 800},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 12,
        },
    },
    "additionalProperties": False,
}


_GATE_REVIEW = {
    "name": "gate_review",
    "system": (
        "You are a strict trading-decision auditor. The system has already "
        "decided ENTER, WAIT, or BLOCK using deterministic rules. Your role "
        "is to review the decision and return one of: 'agree' (the system's "
        "verdict stands), 'downgrade' (turn ENTER into WAIT, or WAIT into "
        "BLOCK), or 'block' (force a BLOCK). You CANNOT upgrade — you may "
        "never propose ENTER if the system did not. Reply with valid JSON "
        "matching the provided schema. No prose outside the JSON."
    ),
    "user_template": (
        "Review this decision cycle and respond with the JSON schema only.\n\n"
        "Symbol: {symbol}\n"
        "Session window: {session_window}\n"
        "Final status: {final_status}\n"
        "Brain grades: {grades}\n"
        "Brain decisions: {decisions}\n"
        "Risk flags: {risk_flags}\n"
        "Evidence summary: {evidence_summary}\n"
        "Blocking reason: {blocking_reason}\n"
    ),
    "output_schema": GATE_REVIEW_SCHEMA,
}


# Registry — name → template dict. Read-only via API.
_REGISTRY: Dict[str, Dict[str, Any]] = {
    "gate_review": _GATE_REVIEW,
}


def get_template(name: str) -> Dict[str, Any]:
    if name not in _REGISTRY:
        raise KeyError(f"prompt template {name!r} is not registered")
    # Return a deep-ish copy so callers can't mutate the registry.
    src = _REGISTRY[name]
    return {
        "name": src["name"],
        "system": src["system"],
        "user_template": src["user_template"],
        "output_schema": dict(src["output_schema"]),
    }


def list_templates() -> list[str]:
    return sorted(_REGISTRY.keys())


# Disallowed-key list: payload values may not contain these keys, to
# defend against callers who accidentally bundle a secret into a render
# payload.
_BANNED_PAYLOAD_KEYS = {
    "api_key", "apikey", "api-key",
    "secret", "password", "passwd", "pass", "pwd",
    "access_token", "auth_token",
    "anthropic_api_key", "oanda_api_token", "oanda_token", "token",
    "account_id", "oanda_account_id",
}


def _check_payload_keys(payload: Dict[str, Any]) -> None:
    for k in payload.keys():
        norm = k.lower().replace("-", "_")
        if norm in _BANNED_PAYLOAD_KEYS:
            raise ValueError(
                f"payload key {k!r} is on the banned list (looks like a secret)"
            )


def render(name: str, payload: Dict[str, Any]) -> Dict[str, str]:
    """Return {'system': ..., 'user': ...} ready to send.

    Raises ValueError on banned payload keys or missing template fields.
    """
    tpl = get_template(name)
    _check_payload_keys(payload)
    # Use string.Formatter so missing keys raise KeyError, not silent ''.
    fmt = string.Formatter()
    try:
        user = fmt.vformat(tpl["user_template"], (), payload)
    except KeyError as e:
        raise ValueError(f"prompt template {name!r} missing payload key: {e}") from e
    return {"system": tpl["system"], "user": user}
