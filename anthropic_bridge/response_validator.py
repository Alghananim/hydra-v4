"""HYDRA V4 — anthropic_bridge / response_validator.

Tiny stdlib JSON-schema validator. Supports just the subset our
templates use:

  * type: object | string | array | number | integer | boolean | null
  * required: list[str]
  * properties: dict[str, schema]
  * enum: list
  * minLength, maxLength
  * additionalProperties: False
  * items: schema

A full jsonschema dependency would be overkill and adds a wheel. This
validator intentionally rejects anything outside the supported subset.
"""

from __future__ import annotations

from typing import Any, Dict, List


class ValidationError(ValueError):
    pass


_SUPPORTED_TYPES = {
    "object": dict,
    "string": str,
    "array": list,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def validate(value: Any, schema: Dict[str, Any], _path: str = "$") -> None:
    t = schema.get("type")
    if t is not None:
        py_t = _SUPPORTED_TYPES.get(t)
        if py_t is None:
            raise ValidationError(f"{_path}: unsupported schema type {t!r}")
        # bool is an int subclass — guard against accepting True for 'integer'.
        if t == "integer" and isinstance(value, bool):
            raise ValidationError(f"{_path}: expected integer, got bool")
        if not isinstance(value, py_t):
            raise ValidationError(
                f"{_path}: expected {t}, got {type(value).__name__}"
            )

    if "enum" in schema:
        if value not in schema["enum"]:
            raise ValidationError(
                f"{_path}: value {value!r} not in enum {schema['enum']!r}"
            )

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValidationError(f"{_path}: string shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValidationError(f"{_path}: string longer than maxLength")

    if isinstance(value, list):
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                validate(item, item_schema, f"{_path}[{i}]")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValidationError(f"{_path}: array too long")

    if isinstance(value, dict):
        required: List[str] = list(schema.get("required", []))
        for r in required:
            if r not in value:
                raise ValidationError(f"{_path}: missing required key {r!r}")
        props: Dict[str, Any] = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                validate(v, props[k], f"{_path}.{k}")
            elif schema.get("additionalProperties") is False:
                raise ValidationError(f"{_path}: unexpected key {k!r}")
