"""SmartNoteBook V4 — secret redactor.

Strips well-known secret-shaped tokens from records BEFORE persistence.
Operates at the record boundary in storage.append_record.

Patterns covered (R6):
  * "Bearer <token>"           -> "Bearer [REDACTED]"
  * "sk-<alnum...>"             (OpenAI / Anthropic style)
  * "OANDA_TOKEN=<...>"         (OANDA assignment form)
  * Standalone OANDA-shaped hex tokens (32-char or 32-char-dashed-16+-char)
  * "api_key": "xxxx" inside JSON-ish strings
  * AWS access key IDs:        AKIA[0-9A-Z]{16}
  * JWT three-segment tokens:  eyJ.../.../...
  * Dict-key-based: any dict value under {api_key, secret, password,
    pass, pwd, oanda_token, aws_secret_access_key, aws_access_key_id,
    aws_session_token, ...} is replaced with [REDACTED] regardless of
    the value's shape.

Unicode obfuscation defense (S3):
  * Inputs are NFKC-normalized
  * Zero-width spaces (U+200B, U+200C, U+200D, U+FEFF) are stripped
  * Soft hyphen (U+00AD) is stripped
  This defeats tricks like "Be{soft-hyphen}arer" and "sk{ZWSP}-..."

The redactor walks any nested dict / list / dataclass and replaces strings
in-place (returning a new copy — the input is NOT mutated). Non-string
leaves are passed through unchanged.

Belt-and-braces: `assert_clean` raises SecretLeakError if any of the
patterns survived redaction. Storage calls assert_clean as a final
boundary check.

Integrity-field exemption: keys "chain_hash" and "prev_hash" hold sha256
hex (64 chars) which would otherwise look like secrets. These are NEVER
redacted — they are required for chain verification.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from smartnotebook.v4.error_handling import SecretLeakError
from smartnotebook.v4.notebook_constants import REDACTION_PLACEHOLDER

_log = logging.getLogger("smartnotebook")

# Unicode characters used to obfuscate secrets — strip them before
# regex matching so "Be{U+00AD}arer" and "sk{U+200B}-abc" still hit.
# Using explicit \u escapes so the source survives any encoding round-trip.
_OBFUSCATION_CHARS = (
    "­"   # soft hyphen
    "​"   # zero-width space
    "‌"   # zero-width non-joiner
    "‍"   # zero-width joiner
    "⁠"   # word joiner
    "﻿"   # zero-width no-break space (BOM)
)
_OBFUSCATION_RE = re.compile("[" + _OBFUSCATION_CHARS + "]")


def _normalize_for_match(s: str) -> str:
    """NFKC-normalize and strip zero-width / soft-hyphen chars."""
    if not isinstance(s, str):
        return s
    s = unicodedata.normalize("NFKC", s)
    s = _OBFUSCATION_RE.sub("", s)
    return s


_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=:+/]{6,}")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")
_OANDA_ASSIGN_RE = re.compile(r"(?i)(oanda[_\-]?(?:api[_\-]?)?token)\s*[:=]\s*[\"']?([A-Za-z0-9\-]{16,})[\"']?")
_OANDA_RAW_RE = re.compile(r"\b[a-fA-F0-9]{32,}-[a-fA-F0-9]{16,}\b")
# Standalone 32-hex string (typical OANDA token half). Excludes 64-hex sha256 by
# the upper bound — chain hashes are 64 chars and are skipped anyway.
_OANDA_HEX_NODASH_RE = re.compile(r"(?<![a-fA-F0-9])[a-fA-F0-9]{32}(?![a-fA-F0-9])")
_JSONLIKE_KV_RE = re.compile(
    r"(?i)(\"(?:api[_\-]?key|secret|password|pass|pwd|access[_\-]?token|aws[_\-]?(?:secret|access)[_\-]?(?:access[_\-]?)?key(?:[_\-]?id)?|aws[_\-]?session[_\-]?token)\"\s*:\s*)\"[^\"]+\""
)
# S3 — Long-form assign (>=8 chars value) for general secret keys
_ASSIGN_KV_RE = re.compile(
    r"(?i)\b(api[_\-]?key|secret|access[_\-]?token|aws[_\-]?(?:secret|access)[_\-]?(?:access[_\-]?)?key(?:[_\-]?id)?|aws[_\-]?session[_\-]?token)\s*=\s*[\"']?[A-Za-z0-9_\-\.=]{8,}[\"']?"
)
# S3 — Password-class assign (>=4 chars). Catches "password=test", "pwd=1234".
_ASSIGN_KV_PASSWORD_RE = re.compile(
    r"(?i)\b(password|passwd|pass|pwd)\s*=\s*[\"']?[A-Za-z0-9_\-\.=!@#$%^&*+/]{4,}[\"']?"
)
# S3 — AWS access key
_AWS_ACCESS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
# S3 — JWT three-segment (header.payload.signature, base64url-ish)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


def _redact_string(s: str) -> str:
    if not isinstance(s, str):
        return s
    # Pre-normalize: NFKC + strip zero-width / soft-hyphen so attackers
    # cannot defeat literal regex with U+00AD inside "Bearer".
    out = _normalize_for_match(s)
    before = out
    out = _BEARER_RE.sub(f"Bearer {REDACTION_PLACEHOLDER}", out)
    out = _SK_RE.sub(REDACTION_PLACEHOLDER, out)
    out = _OANDA_ASSIGN_RE.sub(lambda m: f"{m.group(1)}={REDACTION_PLACEHOLDER}", out)
    out = _OANDA_RAW_RE.sub(REDACTION_PLACEHOLDER, out)
    out = _OANDA_HEX_NODASH_RE.sub(REDACTION_PLACEHOLDER, out)
    out = _JSONLIKE_KV_RE.sub(lambda m: f"{m.group(1)}\"{REDACTION_PLACEHOLDER}\"", out)
    out = _ASSIGN_KV_RE.sub(lambda m: f"{m.group(1)}={REDACTION_PLACEHOLDER}", out)
    out = _ASSIGN_KV_PASSWORD_RE.sub(lambda m: f"{m.group(1)}={REDACTION_PLACEHOLDER}", out)
    out = _AWS_ACCESS_KEY_RE.sub(REDACTION_PLACEHOLDER, out)
    out = _JWT_RE.sub(REDACTION_PLACEHOLDER, out)
    if out != before:
        _log.warning("secret redaction triggered (len=%d)", len(s))
    return out


_SECRET_KEY_NAMES = {
    "api_key", "apikey", "api-key",
    "secret", "password", "passwd", "pass", "pwd",
    "access_token", "access-token", "accesstoken",
    "oanda_token", "oanda-token", "oanda_api_token",
    "token", "auth_token", "auth-token",
    "private_key", "private-key", "privatekey",
    # S3 — AWS triumvirate
    "aws_access_key_id", "aws-access-key-id",
    "aws_secret_access_key", "aws-secret-access-key",
    "aws_session_token", "aws-session-token",
}


def _is_secret_key(k):
    if not isinstance(k, str):
        return False
    return k.lower().replace("-", "_") in {n.replace("-", "_") for n in _SECRET_KEY_NAMES}


# Minimum value length for dict-key-triggered redaction. Lower for
# password-class names so even short dev passwords get redacted.
_PASSWORD_NAMES = {"password", "passwd", "pass", "pwd"}


def _key_min_value_len(k: str) -> int:
    base = k.lower().replace("-", "_")
    if base in _PASSWORD_NAMES:
        return 1   # any non-empty value
    return 8


def redact(value: Any) -> Any:
    """Recursively walk and return a redacted copy of `value`.

    - dicts are walked; values under known secret-key names are unconditionally
      replaced. Integrity fields (chain_hash, prev_hash) are passed through.
    - lists / tuples are walked
    - strings go through _redact_string
    - dataclasses are converted to dict
    """
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ("chain_hash", "prev_hash"):
                out[k] = v
            elif _is_secret_key(k) and isinstance(v, str) and len(v) >= _key_min_value_len(k):
                _log.warning("secret redaction triggered for dict key=%s", k)
                out[k] = REDACTION_PLACEHOLDER
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if is_dataclass(value):
        return redact(asdict(value))
    return value


def _walk_for_secrets(value: Any) -> List[str]:
    findings: List[str] = []
    if isinstance(value, str):
        normalized = _normalize_for_match(value)
        for rx, name in (
            (_BEARER_RE, "bearer"),
            (_SK_RE, "sk_token"),
            (_OANDA_ASSIGN_RE, "oanda_assign"),
            (_OANDA_RAW_RE, "oanda_raw"),
            (_AWS_ACCESS_KEY_RE, "aws_access_key"),
            (_JWT_RE, "jwt"),
        ):
            if rx.search(normalized):
                findings.append(f"{name}:{value[:40]}")
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in ("chain_hash", "prev_hash"):
                continue
            findings.extend(_walk_for_secrets(v))
    elif isinstance(value, (list, tuple)):
        for v in value:
            findings.extend(_walk_for_secrets(v))
    return findings


def assert_clean(value: Any) -> None:
    findings = _walk_for_secrets(value)
    if findings:
        raise SecretLeakError(
            f"secrets survived redaction: {findings[:3]} (count={len(findings)})"
        )
