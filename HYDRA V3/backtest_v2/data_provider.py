# -*- coding: utf-8 -*-
"""data_provider — bar source for the harness.

Reuses ``Backtest.data.BacktestData`` for the heavy lifting.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class DataProviderError(RuntimeError):
    pass


class OandaDataProvider:
    def __init__(self, *, cache_dir: Path, pair: str = "EUR/USD",
                 granularity: str = "M15"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._pair = pair
        self._granularity = granularity

    def _build_oanda_client(self):
        token = os.environ.get("OANDA_API_TOKEN")
        account = os.environ.get("OANDA_ACCOUNT_ID")
        if not (token and account):
            return None
        try:
            from OandaAdapter.client import OandaClient    # type: ignore
            env = os.environ.get("OANDA_ENV", "practice")
            return OandaClient(token=token, account_id=account,
                               environment=env)
        except Exception:
            return None

    def load_bars(self, *, start: datetime, end: datetime,
                  force_refresh: bool = False) -> List:
        from Backtest.data import BacktestData    # type: ignore

        slug = self._pair.replace("/", "").lower()
        cache_path = self._cache_dir / f"{slug}_{self._granularity.lower()}.jsonl"

        client = self._build_oanda_client()
        bd = BacktestData(client=client, cache_path=str(cache_path),
                          pair=self._pair, granularity=self._granularity)
        bars = bd.load(start=start, end=end, force_refresh=force_refresh)
        if not bars:
            if client is None:
                raise DataProviderError(
                    "No bars returned. OANDA credentials missing AND "
                    f"cache empty at {cache_path}. Set OANDA_API_TOKEN + "
                    "OANDA_ACCOUNT_ID and re-run, or seed the cache. "
                    "DO NOT run a backtest on synthetic substitutes "
                    "for real history.")
            raise DataProviderError(
                f"OANDA returned 0 bars for {self._pair} "
                f"{start.isoformat()}..{end.isoformat()}. ")
        return bars


def provider_for_tests(synthetic_bars: List) -> "FixtureDataProvider":
    return FixtureDataProvider(synthetic_bars)


class FixtureDataProvider:
    def __init__(self, bars: List):
        self._bars = list(bars)

    def load_bars(self, *, start: Optional[datetime] = None,
                  end: Optional[datetime] = None,
                  force_refresh: bool = False) -> List:
        if not self._bars:
            return []
        out = self._bars
        if start is not None:
            out = [b for b in out if b.time >= start]
        if end is not None:
            out = [b for b in out if b.time <= end]
        return out
