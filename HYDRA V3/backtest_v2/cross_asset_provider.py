# -*- coding: utf-8 -*-
"""cross_asset_provider — DXY / SPX / Gold replay for MarketMind."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class CrossAssetProvider:
    def __init__(self, *, cache_dir: Path, primary_pair: str = "EUR/USD"):
        self._cache_dir = Path(cache_dir)
        self._primary = primary_pair
        self._companion = "USD/JPY" if primary_pair != "USD/JPY" else "EUR/USD"

    def load_companion(self, *, start: datetime, end: datetime) -> List:
        try:
            from .data_provider import OandaDataProvider
            prov = OandaDataProvider(cache_dir=self._cache_dir,
                                      pair=self._companion)
            return prov.load_bars(start=start, end=end)
        except Exception:
            return []

    def load_xau(self, *, start: datetime, end: datetime) -> List:
        return []

    def load_spx(self, *, start: datetime, end: datetime) -> List:
        return []

    def slice_baskets(self, *, primary_bars: List, companion_bars: List,
                      cursor: int) -> Dict[str, List]:
        baskets = {self._primary: primary_bars[: cursor + 1]}
        if companion_bars:
            if len(companion_bars) == len(primary_bars):
                baskets[self._companion] = companion_bars[: cursor + 1]
            else:
                t_now = primary_bars[cursor].time
                baskets[self._companion] = [b for b in companion_bars
                                             if b.time <= t_now]
        return baskets
