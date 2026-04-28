# -*- coding: utf-8 -*-
"""BacktestConfig — single source of truth for every harness knob."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class BacktestConfig:
    pair: str = "EUR/USD"
    granularity: str = "M15"
    start_utc: Optional[datetime] = None
    end_utc: Optional[datetime] = None

    initial_balance: float = 10_000.0
    risk_pct_per_trade: float = 0.0025
    pip_value_per_lot: float = 10.0
    units_per_lot: int = 100_000

    strict_mode: bool = True
    use_llm: bool = False

    entry_slippage_pips: float = 0.5
    stop_slippage_pips: float = 1.0
    target_slippage_pips: float = 0.2
    fallback_spread_pips: float = 0.5
    commission_per_lot_per_side: float = 0.0

    cache_dir: Path = field(default_factory=lambda: Path("./.backtest_cache"))
    output_dir: Path = field(default_factory=lambda: Path("./backtest_results"))
    smartnotebook_dir: Optional[Path] = None

    run_id: str = ""
    label: str = ""

    max_bars: Optional[int] = None
    fail_fast_on_leak: bool = True

    def __post_init__(self):
        if isinstance(self.cache_dir, str):
            self.cache_dir = Path(self.cache_dir)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if self.smartnotebook_dir is None:
            self.smartnotebook_dir = self.output_dir / "notebook"
        elif isinstance(self.smartnotebook_dir, str):
            self.smartnotebook_dir = Path(self.smartnotebook_dir)
        self.pair_pip = 0.01 if "JPY" in self.pair.upper() else 0.0001

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            elif isinstance(v, Path):
                d[k] = str(v)
            else:
                d[k] = v
        return d

    def stamp_run_id(self) -> str:
        if not self.run_id:
            now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            tag = (self.label or ("strict" if self.strict_mode else "loose"))
            self.run_id = f"{tag}_{self.pair.replace('/', '')}_{now}"
        return self.run_id
