"""NewsMind V4 — config loader for events.yaml + keywords.yaml.

YAML is parsed via a tiny stdlib-only subset (PyYAML may or may not be
installed in the runner environment). The events file uses a deliberately
flat schema so we can parse it with a hand-rolled mini-YAML if PyYAML is
not available.

Strategy:
  1. Try `import yaml` (PyYAML). If present, use it.
  2. Else fall back to a minimal indentation-based loader sufficient for the
     specific structure of events.yaml / keywords.yaml.

This keeps NewsMind dependency-free in production while still being friendly
to dev environments that have PyYAML.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from newsmind.v4.models import EventSchedule


# ---------------------------------------------------------------------------
# YAML loader (PyYAML if present; tiny fallback otherwise)
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml_parse(text)


def _coerce(scalar: str) -> Any:
    s = scalar.strip()
    if s == "":
        return ""
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "None", "~"):
        return None
    # int
    try:
        return int(s)
    except ValueError:
        pass
    # float
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _mini_yaml_parse(text: str) -> Any:
    """Indentation-based YAML subset.

    Supports:
      key: value
      key:
        subkey: value
      key:
        - item1
        - item2
      key: [a, b, c]      (inline list)
    Does NOT support: anchors, multiline strings, flow maps with nesting,
    YAML tags. These are not used in our config files.
    """
    # strip comments + blank lines
    raw_lines = []
    for line in text.splitlines():
        # strip trailing comment but keep '#' inside quoted strings
        stripped = _strip_comment(line)
        if stripped.strip() == "":
            continue
        raw_lines.append(stripped.rstrip())

    # Build a stack-based tree
    root: Dict[str, Any] = {}
    # stack entries: (indent, container)
    stack: List = [(-1, root)]

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        # pop until top of stack has smaller indent
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise ValueError(f"YAML indent fell off stack at line: {line!r}")
        parent = stack[-1][1]

        if content.startswith("- "):
            value_part = content[2:].strip()
            if not isinstance(parent, list):
                raise ValueError(f"List item under non-list parent: {line!r}")
            if ":" in value_part and not value_part.startswith(("\"", "'")):
                # list of dicts: "- key: val" starts a dict
                new_dict: Dict[str, Any] = {}
                k, _, v = value_part.partition(":")
                v = v.strip()
                if v == "":
                    # value continues on subsequent indented lines
                    pass
                else:
                    new_dict[k.strip()] = _coerce(v)
                parent.append(new_dict)
                stack.append((indent, new_dict))
            else:
                parent.append(_coerce(value_part))
            i += 1
            continue

        if ":" in content:
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                # children follow at greater indent — peek next non-empty
                next_indent = _peek_indent(raw_lines, i + 1)
                if next_indent is None or next_indent <= indent:
                    # empty mapping
                    parent[key] = {}
                else:
                    # decide list vs dict by the next line's first non-space char
                    nxt = raw_lines[i + 1].lstrip()
                    if nxt.startswith("- "):
                        new_container: Any = []
                    else:
                        new_container = {}
                    parent[key] = new_container
                    stack.append((indent, new_container))
            elif value.startswith("[") and value.endswith("]"):
                # inline list
                inner = value[1:-1].strip()
                if inner == "":
                    parent[key] = []
                else:
                    parent[key] = [_coerce(p) for p in _split_inline_list(inner)]
            else:
                parent[key] = _coerce(value)
            i += 1
            continue

        raise ValueError(f"Unparseable YAML line: {line!r}")

    return root


def _strip_comment(line: str) -> str:
    out = []
    in_single = in_double = False
    for ch in line:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out)


def _peek_indent(lines: List[str], idx: int) -> Optional[int]:
    if idx >= len(lines):
        return None
    ln = lines[idx]
    return len(ln) - len(ln.lstrip(" "))


def _split_inline_list(s: str) -> List[str]:
    parts, buf, depth = [], [], 0
    in_q = None
    for ch in s:
        if in_q:
            buf.append(ch)
            if ch == in_q:
                in_q = None
            continue
        if ch in "\"'":
            in_q = ch
            buf.append(ch)
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())
    return parts


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def default_config_dir() -> Path:
    """The canonical V4 config dir.

    Resolution order:
      1. $HYDRA_V4_CONFIG_DIR if set
      2. <repo-root>/config/news (where repo-root is two parents above this file)
    """
    env = os.environ.get("HYDRA_V4_CONFIG_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    # newsmind/v4/config_loader.py  →  parents[2] is HYDRA V4
    return here.parents[2] / "config" / "news"


def load_events(path: Optional[Path] = None) -> List[EventSchedule]:
    p = path or (default_config_dir() / "events.yaml")
    data = _load_yaml(p)
    if not isinstance(data, dict) or "events" not in data:
        raise ValueError(f"events.yaml malformed at {p}: missing 'events' key")
    out: List[EventSchedule] = []
    for row in data["events"]:
        out.append(
            EventSchedule(
                id=row["id"],
                name=row["name"],
                currency=row["currency"],
                affects=list(row.get("affects", [])),
                blackout_pre_min=int(row["blackout_pre_min"]),
                blackout_post_min=int(row["blackout_post_min"]),
                pip_per_sigma={k: float(v) for k, v in row.get("pip_per_sigma", {}).items()},
                tier=int(row.get("tier", 2)),
            )
        )
    return out


def load_keywords(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or (default_config_dir() / "keywords.yaml")
    data = _load_yaml(p)
    if not isinstance(data, dict):
        raise ValueError(f"keywords.yaml malformed at {p}")
    return data
