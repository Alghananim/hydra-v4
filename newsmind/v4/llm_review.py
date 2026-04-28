"""NewsMind V4 — Claude downgrade-only reviewer.

OPTIONAL: not wired in v4.0; will be enabled in v4.1.
The orchestrator (NewsMindV4.evaluate) does not import or call this module
in v4.0 — see the TODO inside evaluate() for the planned hook site.
This is acceptable per spec: Claude is downgrade-only, so leaving the
reviewer dormant only loses a redundant safety layer; it never inflates a
verdict. Tests verify this module remains importable.

Hard rules:
  - The LLM has DOWNGRADE-ONLY authority. The caller's enum is
    ("agree", "downgrade", "block"). There is no "upgrade" enum value.
  - tool_choice / structured-output schema enforces the enum at the API
    level. Caller-side enum clamp is the belt-and-suspenders second layer:
    if the API ever returns something off-enum, it is silently re-mapped
    to "block" (fail-CLOSED).
  - audit_hash = sha256(prompt + response)[:16] is recorded for every call.

If ANTHROPIC_API_KEY is not set OR the `anthropic` SDK is not installed,
review() returns a deterministic stub with severity="unknown" and
suggestion="agree" — i.e. the LLM is treated as absent (no-op). The
orchestrator therefore behaves correctly even in an air-gapped CI.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_ALLOWED_SUGGESTIONS = ("agree", "downgrade", "block")


@dataclass
class LLMReview:
    suggestion: str            # always one of _ALLOWED_SUGGESTIONS
    severity: str              # "info" | "minor" | "major" | "critical" | "unknown"
    rationale: str
    audit_hash: str
    raw_model: Optional[str] = None
    risk_flags: List[str] = field(default_factory=list)


_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "review_verdict",
    "description": (
        "Review a NewsMind verdict. You may DOWNGRADE quality or BLOCK, "
        "but you MAY NOT upgrade. You MUST cite at least one concrete fact "
        "from the provided evidence list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "suggestion": {
                "type": "string",
                "enum": list(_ALLOWED_SUGGESTIONS),  # 'upgrade' deliberately absent
            },
            "severity": {
                "type": "string",
                "enum": ["info", "minor", "major", "critical"],
            },
            "rationale": {"type": "string", "minLength": 1},
            "risk_flags": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
        },
        "required": ["suggestion", "severity", "rationale"],
        "additionalProperties": False,
    },
}


def _audit_hash(prompt: str, response: str) -> str:
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\n---\n")
    h.update(response.encode("utf-8"))
    return h.hexdigest()[:16]


def _clamp_suggestion(value: str) -> str:
    """Belt-and-suspenders: if the API returned something off-enum, fail-CLOSED."""
    v = (value or "").strip().lower()
    if v in _ALLOWED_SUGGESTIONS:
        return v
    # Anything else — including "upgrade", "enter", "approve" — collapses to block.
    return "block"


def build_prompt(
    pair: str,
    headline: Optional[str],
    grade: str,
    decision: str,
    evidence: List[str],
    blackout_reason: Optional[str],
) -> str:
    return (
        f"NewsMind V4 verdict for {pair}:\n"
        f"  decision     : {decision}\n"
        f"  grade        : {grade}\n"
        f"  headline     : {headline or '(none)'}\n"
        f"  blackout     : {blackout_reason or '(none)'}\n"
        f"  evidence     :\n"
        + "\n".join(f"    - {e}" for e in evidence)
        + "\n\nReview this. You MAY downgrade or block. You MAY NOT upgrade.\n"
    )


def review(
    pair: str,
    headline: Optional[str],
    grade: str,
    decision: str,
    evidence: List[str],
    blackout_reason: Optional[str] = None,
    *,
    model: str = "claude-sonnet-4-5",
    timeout_s: float = 8.0,
) -> LLMReview:
    """Run Claude review. Falls back to a no-op stub when API unavailable."""
    prompt = build_prompt(pair, headline, grade, decision, evidence, blackout_reason)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _stub_review(prompt, reason="ANTHROPIC_API_KEY not set")

    try:
        import anthropic  # type: ignore
    except ImportError:
        return _stub_review(prompt, reason="anthropic SDK not installed")

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "review_verdict"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:  # noqa: BLE001 — explicit fail-CLOSED at boundary
        return LLMReview(
            suggestion="block",
            severity="critical",
            rationale=f"LLM call failed: {type(e).__name__}: {e}",
            audit_hash=_audit_hash(prompt, str(e)),
            raw_model=model,
            risk_flags=["llm_unavailable"],
        )

    payload: Optional[Dict[str, Any]] = None
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "review_verdict":
            payload = getattr(block, "input", None)
            break

    if not isinstance(payload, dict):
        return LLMReview(
            suggestion="block",
            severity="critical",
            rationale="LLM did not return tool_use payload",
            audit_hash=_audit_hash(prompt, json.dumps({"raw": str(resp)})[:512]),
            raw_model=model,
            risk_flags=["llm_schema_violation"],
        )

    suggestion = _clamp_suggestion(payload.get("suggestion", ""))
    severity = payload.get("severity", "unknown")
    if severity not in ("info", "minor", "major", "critical"):
        severity = "unknown"
    rationale = str(payload.get("rationale", "")).strip() or "(no rationale)"
    risk_flags = list(payload.get("risk_flags") or [])

    return LLMReview(
        suggestion=suggestion,
        severity=severity,
        rationale=rationale,
        audit_hash=_audit_hash(prompt, json.dumps(payload, sort_keys=True)),
        raw_model=model,
        risk_flags=risk_flags,
    )


def _stub_review(prompt: str, reason: str) -> LLMReview:
    return LLMReview(
        suggestion="agree",
        severity="unknown",
        rationale=f"LLM stub: {reason}",
        audit_hash=_audit_hash(prompt, reason),
        raw_model=None,
        risk_flags=["llm_stubbed"],
    )
