"""Per-bar-series memoization — adapted from V3.

Bar series only changes when a new bar arrives, so we fingerprint
(id, len, last_close, last_ts) and cache expensive computations.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence, Tuple


_CACHE: dict = {}
_HITS = 0
_MISSES = 0
_MAX = 1024


def _fingerprint(bars: Sequence[Any]) -> Tuple:
    if not bars:
        return ("empty",)
    last = bars[-1]
    ts = last.timestamp.isoformat() if hasattr(last, "timestamp") else "?"
    return (id(bars), len(bars), round(getattr(last, "close", 0.0), 6), ts)


def memoize(name: str, bars: Sequence[Any], compute: Callable[[], Any]) -> Any:
    global _HITS, _MISSES
    key = (name, _fingerprint(bars))
    if key in _CACHE:
        _HITS += 1
        return _CACHE[key]
    _MISSES += 1
    val = compute()
    _CACHE[key] = val
    if len(_CACHE) > _MAX:
        for _ in range(_MAX // 8):
            _CACHE.pop(next(iter(_CACHE)))
    return val


def stats() -> dict:
    total = _HITS + _MISSES
    return {
        "hits": _HITS,
        "misses": _MISSES,
        "hit_rate": round(_HITS / total, 3) if total else 0.0,
        "size": len(_CACHE),
    }


def clear() -> None:
    global _HITS, _MISSES
    _CACHE.clear()
    _HITS = 0
    _MISSES = 0
