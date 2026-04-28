# -*- coding: utf-8 -*-
"""LeakDetector — structural defence against look-ahead bias."""
from __future__ import annotations

from typing import Any, Iterator, List, Sequence


class LookaheadLeakError(RuntimeError):
    """Raised when any consumer touches a bar past the cursor."""


class LeakSafeBars:
    """Sequence wrapper that hides bars past the cursor."""

    __slots__ = ("_all", "_cursor", "_pair")

    def __init__(self, all_bars: Sequence[Any], *, cursor: int = -1,
                 pair: str = ""):
        self._all = list(all_bars)
        self._cursor = cursor if cursor >= 0 else len(self._all) - 1
        self._pair = pair

    def __len__(self) -> int:
        return self._cursor + 1

    @property
    def cursor(self) -> int:
        return self._cursor

    def set_cursor(self, new_cursor: int) -> None:
        if new_cursor < -1 or new_cursor >= len(self._all):
            raise IndexError(
                f"LeakSafeBars: cursor {new_cursor} out of "
                f"[-1, {len(self._all)-1}]")
        self._cursor = new_cursor

    def total_len(self) -> int:
        return len(self._all)

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self._all))
            if step > 0 and stop - 1 > self._cursor:
                raise LookaheadLeakError(
                    f"LeakSafeBars[{self._pair}]: slice end {stop-1} > "
                    f"cursor {self._cursor} (look-ahead bias detected)")
            if start > self._cursor:
                raise LookaheadLeakError(
                    f"LeakSafeBars[{self._pair}]: slice start {start} > "
                    f"cursor {self._cursor} (look-ahead bias detected)")
            return self._all[key]
        if isinstance(key, int):
            idx = key if key >= 0 else len(self) + key
            if idx > self._cursor or idx < 0:
                raise LookaheadLeakError(
                    f"LeakSafeBars[{self._pair}]: index {idx} > "
                    f"cursor {self._cursor} (look-ahead bias detected)")
            return self._all[idx]
        raise TypeError(f"LeakSafeBars: unsupported key type {type(key)}")

    def __iter__(self) -> Iterator[Any]:
        for i in range(self._cursor + 1):
            yield self._all[i]

    def visible(self) -> List[Any]:
        return list(self._all[: self._cursor + 1])

    def peek_future_for_test(self, offset: int) -> Any:
        idx = self._cursor + offset
        if idx < 0 or idx >= len(self._all):
            return None
        return self._all[idx]
