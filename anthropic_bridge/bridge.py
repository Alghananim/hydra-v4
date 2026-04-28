"""HYDRA V4 — anthropic_bridge / bridge.

The single point of contact with the Anthropic Messages API. Stdlib
HTTP only (no `requests`). Every request:

  1. Loads a named prompt template (no inline prompts).
  2. Renders it with the caller's payload.
  3. Verifies the rendered prompt has NO secrets via
     `secret_redactor.assert_clean_for_anthropic`.
  4. Calls Anthropic with `tool_choice` to FORCE structured output.
  5. Parses the tool_use block.
  6. Validates against the template's `output_schema`.
  7. Logs ONLY redacted prompt + response + sha256 audit hash.
  8. Enforces "no upgrade authority": suggestion ∈ {agree, downgrade,
     block}; anything else raises.
  9. Returns the parsed dict.

Refusal points raise `AnthropicBridgeError`. The audit hash is a
sha256 of `prompt_canonical_json + response_canonical_json` so the
ledger can prove a request was sent and what came back.

Construction:
  AnthropicBridge(api_key, model="claude-3-5-sonnet-20241022", url_opener=None)
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from anthropic_bridge import prompt_templates as _tpl
from anthropic_bridge import response_validator as _rv
from anthropic_bridge import secret_redactor as _redactor

_log = logging.getLogger("anthropic_bridge")

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TIMEOUT_SECONDS = 30.0


class AnthropicBridgeError(RuntimeError):
    """Raised on any bridge-level violation."""


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _canonical_json(o: Any) -> str:
    return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


class AnthropicBridge:
    """Schema-locked, redaction-enforcing wrapper around Anthropic Messages."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        url_opener=None,
        max_tokens: int = 1024,
    ) -> None:
        if not isinstance(api_key, str) or len(api_key) < 16:
            raise ValueError("api_key missing or implausibly short")
        self._api_key = api_key
        self._model = model
        self._url_opener = url_opener or urllib.request.build_opener()
        self._max_tokens = int(max_tokens)

    def __repr__(self) -> str:
        return f"AnthropicBridge(model={self._model!r})"

    # ------------------------------------------------------------------
    def request(
        self,
        prompt_template_name: str,
        payload: Dict[str, Any],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a templated request and return the parsed JSON dict.

        Raises AnthropicBridgeError on:
          * unknown template
          * banned key in payload
          * secret survives redaction
          * non-JSON response from Claude
          * schema validation failure
          * suggestion field with disallowed value (e.g. 'upgrade')
        """
        try:
            tpl = _tpl.get_template(prompt_template_name)
        except KeyError as e:
            raise AnthropicBridgeError(f"unknown template: {e}") from e

        try:
            rendered = _tpl.render(prompt_template_name, payload)
        except ValueError as e:
            raise AnthropicBridgeError(f"render failed: {e}") from e

        # Belt + braces — secret check on the rendered prompt + payload.
        try:
            _redactor.assert_clean_for_anthropic(rendered)
            _redactor.assert_clean_for_anthropic(payload)
        except Exception as e:
            raise AnthropicBridgeError(f"secret leak in prompt: {e}") from e

        out_schema = schema or tpl["output_schema"]
        tool_def = self._schema_to_tool_definition(out_schema)

        body = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": rendered["system"],
            "messages": [{"role": "user", "content": rendered["user"]}],
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": tool_def["name"]},
        }

        raw_response = self._post(body)

        # The model is forced to a tool_use; extract its `input`.
        try:
            content = raw_response.get("content", [])
            tool_use = next(
                (c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"),
                None,
            )
            if tool_use is None:
                raise AnthropicBridgeError("response had no tool_use block (free text)")
            parsed = tool_use.get("input")
            if not isinstance(parsed, dict):
                raise AnthropicBridgeError("tool_use.input was not a JSON object")
        except (KeyError, TypeError) as e:
            raise AnthropicBridgeError(f"malformed Anthropic response: {e}") from e

        # Schema validation
        try:
            _rv.validate(parsed, out_schema)
        except _rv.ValidationError as e:
            raise AnthropicBridgeError(f"schema validation failed: {e}") from e

        # No-upgrade enforcement (defensive — the schema's enum already
        # blocks 'upgrade', but we also reject the literal string here so
        # adversarial schemas can't sneak it in).
        if "suggestion" in parsed:
            if parsed["suggestion"] not in ("agree", "downgrade", "block"):
                raise AnthropicBridgeError(
                    f"disallowed suggestion {parsed['suggestion']!r}"
                )

        # Compute audit hash + log redacted prompt/response.
        prompt_canonical = _canonical_json({
            "template": prompt_template_name,
            "system": rendered["system"],
            "user": rendered["user"],
            "model": self._model,
        })
        response_canonical = _canonical_json(parsed)
        audit_hash = _sha256_hex(prompt_canonical + response_canonical)

        redacted_prompt = _redactor.redact(rendered)
        redacted_response = _redactor.redact(parsed)
        _log.info(
            "anthropic_bridge call template=%s audit_hash=%s",
            prompt_template_name, audit_hash,
        )
        # H6: do NOT return the raw `parsed` dict — callers who log the
        # bridge result would leak secrets that the redactor stripped from
        # `redacted_response`. Expose ONLY the redacted forms by default.
        # Power users who need the unredacted parsed object must explicitly
        # request `unsafe_raw_parsed` (see docstring above) and accept the
        # caller-side responsibility of not logging it.
        return {
            "parsed": redacted_response,        # back-compat key, NOW redacted
            "audit_hash": audit_hash,
            "redacted_prompt": redacted_prompt,
            "redacted_response": redacted_response,
            "template": prompt_template_name,
            # WARNING: contains un-redacted model output. Do NOT log this
            # field. Provided so a downstream consumer that needs the exact
            # tool-use JSON for further validation can reach for it
            # explicitly. Wrapping in a name with "unsafe_" so any
            # log-grepping audit will see it loud and clear.
            "unsafe_raw_parsed": parsed,
        }

    # ------------------------------------------------------------------
    def _schema_to_tool_definition(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": "structured_response",
            "description": "Return ONLY the structured response. No prose.",
            "input_schema": schema,
        }

    # ------------------------------------------------------------------
    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            _ANTHROPIC_URL,
            data=data,
            method="POST",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
        )
        try:
            with self._url_opener.open(req, timeout=_TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # H4: never chain `from e` — the HTTPError holds headers
            # which on some servers echo the x-api-key value back, and a
            # verbose `reason` we do NOT want surfaced into our logs or
            # callers. Log status code only.
            _log.warning("anthropic_bridge HTTP error code=%s", getattr(e, "code", "?"))
            raise AnthropicBridgeError(f"Anthropic HTTP {e.code}") from None
        except urllib.error.URLError as e:
            _log.warning("anthropic_bridge URLError")
            raise AnthropicBridgeError("Anthropic URLError") from None
