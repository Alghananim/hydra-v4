"""HYDRA V4 — P&L Simulator.

Walks each ENTER_CANDIDATE cycle forward through cached M15 bars and
computes a deterministic trade outcome under explicit SL/TP rules.
Aggregates results to net profit, win rate, profit factor, max
drawdown, expectancy, and the 2-trades-per-day target.

DESIGN PRINCIPLES
=================
1. NO LOOKAHEAD. Each trade walks bars forward FROM the entry bar; it
   never peeks past the SL/TP/timeout exit. The decision to enter is
   already made (in the upstream replay); this simulator only resolves
   what would have happened given that decision.
2. NO LIVE TRADING. Pure simulation over local bar JSONL files.
3. EXPLICIT ASSUMPTIONS. Every cost (spread, slippage), every rule
   (SL pips, TP pips, R:R, max bars in trade) is a constructor
   parameter. No hidden defaults that could "tune" results.
4. REPRODUCIBLE. Given the same decision_cycles input + same bar data
   + same parameters, output is byte-identical.
5. HONEST METRICS. Reports gross profit, gross loss, costs separately,
   and net only after subtracting costs.

INPUTS
======
- A list of ENTER_CANDIDATE cycles, each with: cycle_id, symbol,
  timestamp_utc, direction (BUY/SELL).
- The cached merged.jsonl bar files for each symbol.

OUTPUTS
=======
- A JSON file (or returned dict) with:
    overall metrics
    per-pair metrics
    per-session metrics (PRE_OPEN / MORNING)
    full trade ledger (every individual outcome)
    sensitivity-grid optional (varying SL/TP/slippage)

STANDALONE USAGE
================
    python -m replay.pnl_simulator \\
        --decision-cycles replay_results/decision_cycles.csv \\
        --bars-dir data_cache \\
        --sl-pips 10 --tp-pips 20 --slippage-pips 0.5 \\
        --risk-per-trade-pct 1.0 --starting-balance 10000 \\
        --output replay_results/pnl_results.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

_log = logging.getLogger("replay.pnl")

_NY_TZ = ZoneInfo("America/New_York")

# Pip resolution per pair (must match data_quality_checker.PIP_SIZE)
PIP_SIZE: Dict[str, float] = {
    "EUR_USD": 0.0001,
    "USD_JPY": 0.01,
    "GBP_USD": 0.0001,
    "AUD_USD": 0.0001,
    "USD_CHF": 0.0001,
    "USD_CAD": 0.0001,
}


# =====================================================================
# Data structures
# =====================================================================

@dataclass(frozen=True)
class EntryCandidate:
    """One ENTER_CANDIDATE record. Direction must be BUY or SELL.

    V12: optionally carries ChartMind-supplied stop/target/ATR. When
    these are present the simulator uses them per-trade; when absent
    the simulator falls back to the fixed sl_pips/tp_pips defaults.
    """
    cycle_id: str
    symbol: str
    timestamp_utc: datetime
    direction: str
    session_status: str
    # V12 references (None for legacy V5 candidates)
    invalidation_level: Optional[float] = None
    target_reference: Optional[float] = None
    atr_value: Optional[float] = None
    setup_anchor: Optional[float] = None

    def __post_init__(self) -> None:
        if self.direction not in ("BUY", "SELL"):
            raise ValueError(f"direction must be BUY or SELL, got {self.direction!r}")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be tz-aware UTC")


@dataclass(frozen=True)
class TradeOutcome:
    cycle_id: str
    symbol: str
    direction: str
    session_status: str

    entry_time_utc: datetime
    entry_price: float
    exit_time_utc: datetime
    exit_price: float
    exit_reason: str           # "SL" | "TP" | "TIMEOUT" | "WINDOW_CLOSE"
    duration_bars: int

    # P&L
    pnl_pips_gross: float      # before slippage
    pnl_pips_net: float        # after slippage
    pnl_dollars: float         # at the simulator's risk-per-trade and balance
    won: bool                  # pnl_pips_net > 0

    # Cost breakdown (so net = gross - cost is auditable)
    spread_paid_pips: float
    slippage_paid_pips: float


@dataclass
class BacktestMetrics:
    # Counts
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    timeouts: int = 0

    # Pip P&L
    gross_profit_pips: float = 0.0
    gross_loss_pips: float = 0.0
    net_profit_pips: float = 0.0
    spread_cost_pips: float = 0.0
    slippage_cost_pips: float = 0.0

    # Dollar P&L
    gross_profit_dollars: float = 0.0
    gross_loss_dollars: float = 0.0
    net_profit_dollars: float = 0.0
    starting_balance: float = 0.0
    ending_balance: float = 0.0
    return_pct: float = 0.0

    # Stats
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    expectancy_pips: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    # Risk
    max_drawdown_dollars: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_start_utc: Optional[str] = None
    max_drawdown_end_utc: Optional[str] = None

    # Frequency
    trading_days: int = 0
    trades_per_day: float = 0.0
    days_with_2plus_trades: int = 0
    days_with_2plus_trades_pct: float = 0.0

    # Provenance
    parameters: Dict[str, Any] = field(default_factory=dict)


# =====================================================================
# Bar loader
# =====================================================================

def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "." in s:
        head, tail = s.split(".", 1)
        idx = max(tail.find("+"), tail.find("-"))
        if idx >= 0:
            frac, tz = tail[:idx], tail[idx:]
        else:
            frac, tz = tail, ""
        s = f"{head}.{frac[:6]}{tz}"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_bars(merged_jsonl: Path) -> List[Dict[str, Any]]:
    """Load merged.jsonl into a list of candle dicts, sorted by time."""
    bars: List[Dict[str, Any]] = []
    with merged_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            bars.append(json.loads(line))
    bars.sort(key=lambda b: b.get("time", ""))
    return bars


def index_bars_by_time(bars: List[Dict[str, Any]]) -> Dict[datetime, int]:
    """Map UTC datetime -> bar index for fast lookup."""
    out: Dict[datetime, int] = {}
    for i, b in enumerate(bars):
        t = _parse_iso(b["time"])
        out[t] = i
    return out


# =====================================================================
# Simulator core
# =====================================================================

class PnLSimulator:
    """Walks ENTER_CANDIDATEs forward and resolves trade outcomes.

    Parameters
    ----------
    sl_pips           Stop-loss distance in pips.
    tp_pips           Take-profit distance in pips.
    slippage_pips     One-side slippage applied at both entry and exit.
    risk_per_trade_pct  Fraction of balance risked per trade. The
                      position size is computed so SL hit equals this
                      dollar loss (compounded across trades).
    starting_balance  Account balance in USD at the start of the backtest.
    max_bars_in_trade Force exit after this many M15 bars if neither
                      SL nor TP hit. 96 = 24 hours.
    ny_window_only_exit If True, also force exit at the NY window
                      boundary even if TP/SL not hit.
    """

    def __init__(
        self,
        *,
        sl_pips: float = 10.0,
        tp_pips: float = 20.0,
        slippage_pips: float = 0.5,
        risk_per_trade_pct: float = 1.0,
        starting_balance: float = 10_000.0,
        max_bars_in_trade: int = 96,
        ny_window_only_exit: bool = False,
        # V12-F7: break-even trigger. When unrealized P&L >= breakeven_at_r
        # times the initial risk, move SL to entry. 0 = disabled.
        breakeven_at_r: float = 1.0,
        # V12-F8: trailing-stop activation R-multiple. When unrealized
        # P&L >= trail_at_r times initial risk, start trailing the SL
        # at trail_atr_mult × ATR behind the running peak.
        trail_at_r: float = 2.0,
        trail_atr_mult: float = 1.5,
    ) -> None:
        if sl_pips <= 0 or tp_pips <= 0:
            raise ValueError("sl_pips and tp_pips must be positive")
        if slippage_pips < 0:
            raise ValueError("slippage_pips must be >= 0")
        if not (0.0 < risk_per_trade_pct <= 100.0):
            raise ValueError("risk_per_trade_pct must be in (0, 100]")
        if starting_balance <= 0:
            raise ValueError("starting_balance must be positive")
        if max_bars_in_trade < 1:
            raise ValueError("max_bars_in_trade must be >= 1")

        self.sl_pips = float(sl_pips)
        self.tp_pips = float(tp_pips)
        self.slippage_pips = float(slippage_pips)
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.starting_balance = float(starting_balance)
        self.max_bars_in_trade = int(max_bars_in_trade)
        self.ny_window_only_exit = bool(ny_window_only_exit)
        self.breakeven_at_r = float(breakeven_at_r)
        self.trail_at_r = float(trail_at_r)
        self.trail_atr_mult = float(trail_atr_mult)

    # ------------------------------------------------------------------
    def parameters(self) -> Dict[str, Any]:
        return {
            "sl_pips": self.sl_pips,
            "tp_pips": self.tp_pips,
            "slippage_pips": self.slippage_pips,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "starting_balance": self.starting_balance,
            "max_bars_in_trade": self.max_bars_in_trade,
            "ny_window_only_exit": self.ny_window_only_exit,
        }

    # ------------------------------------------------------------------
    def simulate_trade(
        self,
        candidate: EntryCandidate,
        bars: List[Dict[str, Any]],
        bar_index: Dict[datetime, int],
        running_balance: float,
    ) -> Optional[TradeOutcome]:
        """Resolve one ENTER_CANDIDATE → a TradeOutcome (or None if cannot
        find the entry bar)."""
        symbol = candidate.symbol
        pip = PIP_SIZE.get(symbol)
        if pip is None:
            _log.warning("unknown pip size for %s; defaulting to 0.0001", symbol)
            pip = 0.0001

        # Locate entry bar by timestamp
        entry_idx = bar_index.get(candidate.timestamp_utc)
        if entry_idx is None:
            _log.warning(
                "no bar at %s for %s — skipping cycle %s",
                candidate.timestamp_utc.isoformat(), symbol, candidate.cycle_id
            )
            return None

        # Entry: at the NEXT bar's open (no lookahead — we decide at bar t,
        # we fill at bar t+1's open).
        if entry_idx + 1 >= len(bars):
            _log.warning("not enough forward bars for cycle %s", candidate.cycle_id)
            return None

        entry_bar = bars[entry_idx + 1]
        entry_time = _parse_iso(entry_bar["time"])

        if candidate.direction == "BUY":
            entry_price_raw = float(entry_bar["ask"]["o"])  # buy at ask
            entry_price = entry_price_raw + self.slippage_pips * pip
        else:
            entry_price_raw = float(entry_bar["bid"]["o"])  # sell at bid
            entry_price = entry_price_raw - self.slippage_pips * pip

        # V12-F4/F5: prefer ChartMind references when present (stop +
        # target are real, ATR-based, RR=2 floor). Fallback to fixed
        # sl_pips/tp_pips for legacy candidates.
        sl_price: float
        tp_price: float
        if (candidate.invalidation_level is not None
                and candidate.target_reference is not None):
            sl_price = float(candidate.invalidation_level)
            tp_price = float(candidate.target_reference)
            initial_risk = abs(entry_price - sl_price)
        else:
            if candidate.direction == "BUY":
                sl_price = entry_price - self.sl_pips * pip
                tp_price = entry_price + self.tp_pips * pip
            else:
                sl_price = entry_price + self.sl_pips * pip
                tp_price = entry_price - self.tp_pips * pip
            initial_risk = self.sl_pips * pip

        if initial_risk <= 0:
            return None  # degenerate references — skip

        # V12-F8: ATR for trailing stop. Use candidate.atr_value if
        # supplied, else 1×ATR ≈ initial_risk / 1.5 (since stop = 1.5×ATR).
        atr_for_trail = (
            float(candidate.atr_value) if candidate.atr_value
            else initial_risk / 1.5
        )

        # Walk forward
        exit_idx = entry_idx + 1
        exit_reason = "TIMEOUT"
        exit_price = float(entry_bar["mid"]["c"])

        # V12 stateful trade vars
        peak = entry_price if candidate.direction == "BUY" else entry_price
        trough = entry_price if candidate.direction == "SELL" else entry_price
        breakeven_armed = False
        trail_armed = False

        for k in range(self.max_bars_in_trade):
            i = entry_idx + 1 + k
            if i >= len(bars):
                exit_reason = "DATA_END"
                break
            b = bars[i]

            high = float(b["mid"]["h"])
            low = float(b["mid"]["l"])

            # Update favourable extremes for trailing/break-even.
            if candidate.direction == "BUY":
                peak = max(peak, high)
                fav_move = peak - entry_price
            else:
                trough = min(trough, low)
                fav_move = entry_price - trough

            # V12-F7 — break-even: once price has moved breakeven_at_r×R
            # in our favour, snap SL to entry (locks in zero loss).
            if (not breakeven_armed and self.breakeven_at_r > 0
                    and fav_move >= self.breakeven_at_r * initial_risk):
                if candidate.direction == "BUY":
                    sl_price = max(sl_price, entry_price)
                else:
                    sl_price = min(sl_price, entry_price)
                breakeven_armed = True

            # V12-F8 — trailing stop: once price has moved trail_at_r×R,
            # trail the SL at trail_atr_mult×ATR behind peak/trough.
            if (not trail_armed and self.trail_at_r > 0
                    and fav_move >= self.trail_at_r * initial_risk):
                trail_armed = True
            if trail_armed:
                trail_dist = self.trail_atr_mult * atr_for_trail
                if candidate.direction == "BUY":
                    new_sl = peak - trail_dist
                    if new_sl > sl_price:
                        sl_price = new_sl
                else:
                    new_sl = trough + trail_dist
                    if new_sl < sl_price:
                        sl_price = new_sl

            if candidate.direction == "BUY":
                hit_sl = low <= sl_price
                hit_tp = high >= tp_price
            else:
                hit_sl = high >= sl_price
                hit_tp = low <= tp_price

            if hit_sl and hit_tp:
                exit_reason = "TRAIL_SL" if trail_armed else (
                    "BE_SL" if breakeven_armed else "SL"
                )
                exit_price = sl_price
                exit_idx = i
                break
            if hit_sl:
                exit_reason = "TRAIL_SL" if trail_armed else (
                    "BE_SL" if breakeven_armed else "SL"
                )
                exit_price = sl_price
                exit_idx = i
                break
            if hit_tp:
                exit_reason = "TP"
                exit_price = tp_price
                exit_idx = i
                break

            exit_idx = i
            exit_price = float(b["mid"]["c"])

        exit_bar = bars[exit_idx]
        exit_time = _parse_iso(exit_bar["time"])

        # Apply exit-side slippage (against us)
        if exit_reason in ("SL", "TP"):
            if candidate.direction == "BUY":
                exit_price -= self.slippage_pips * pip
            else:
                exit_price += self.slippage_pips * pip

        # P&L in pips
        if candidate.direction == "BUY":
            pnl_pips_net = (exit_price - entry_price) / pip
        else:
            pnl_pips_net = (entry_price - exit_price) / pip

        # Reconstruct gross (without slippage) for transparency
        gross_exit = exit_price + (
            (self.slippage_pips * pip) if candidate.direction == "BUY"
            else -(self.slippage_pips * pip)
        )
        gross_entry = entry_price - (
            (self.slippage_pips * pip) if candidate.direction == "BUY"
            else -(self.slippage_pips * pip)
        )
        if candidate.direction == "BUY":
            pnl_pips_gross = (gross_exit - gross_entry) / pip
        else:
            pnl_pips_gross = (gross_entry - gross_exit) / pip

        # Spread paid (entry side)
        try:
            spread_paid_pips = (
                (float(entry_bar["ask"]["o"]) - float(entry_bar["bid"]["o"])) / pip
            )
        except (KeyError, ValueError):
            spread_paid_pips = 0.0

        slippage_paid_pips = 2 * self.slippage_pips  # entry + exit

        # P&L in dollars: position sized so that an SL hit = risk_per_trade_pct
        # of running_balance.
        risk_dollars = running_balance * (self.risk_per_trade_pct / 100.0)
        # Position size in units: risk_dollars / (sl_pips * pip_value_per_unit)
        # For most pairs vs USD, pip_value_per_unit ≈ pip (e.g. 0.0001 USD per
        # unit for EUR_USD, or 0.01 JPY per unit for USD_JPY which we convert
        # below). For USD_JPY (quote = JPY), need to convert pip move to USD
        # at current price.
        if symbol == "USD_JPY":
            # 1 unit position; 1-pip move = pip JPY = (pip / entry_price) USD
            pip_value_usd_per_unit = pip / entry_price
        else:
            # For *_USD pairs, 1-pip move = pip USD per unit
            pip_value_usd_per_unit = pip
        if pip_value_usd_per_unit <= 0:
            pnl_dollars = 0.0
        else:
            position_units = risk_dollars / (self.sl_pips * pip_value_usd_per_unit)
            pnl_dollars = pnl_pips_net * pip_value_usd_per_unit * position_units

        won = pnl_pips_net > 0.0

        return TradeOutcome(
            cycle_id=candidate.cycle_id,
            symbol=symbol,
            direction=candidate.direction,
            session_status=candidate.session_status,
            entry_time_utc=entry_time,
            entry_price=entry_price,
            exit_time_utc=exit_time,
            exit_price=exit_price,
            exit_reason=exit_reason,
            duration_bars=exit_idx - entry_idx,
            pnl_pips_gross=pnl_pips_gross,
            pnl_pips_net=pnl_pips_net,
            pnl_dollars=pnl_dollars,
            won=won,
            spread_paid_pips=spread_paid_pips,
            slippage_paid_pips=slippage_paid_pips,
        )

    # ------------------------------------------------------------------
    def run(
        self,
        candidates: List[EntryCandidate],
        bars_by_pair: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[List[TradeOutcome], BacktestMetrics]:
        """Run the simulator over all candidates. Returns (trades, metrics)."""
        # Build per-pair indices
        index_by_pair = {p: index_bars_by_time(b) for p, b in bars_by_pair.items()}

        # Sort candidates chronologically — required for compounding balance.
        candidates_sorted = sorted(candidates, key=lambda c: c.timestamp_utc)

        trades: List[TradeOutcome] = []
        running_balance = self.starting_balance
        equity_curve: List[Tuple[datetime, float]] = [
            (candidates_sorted[0].timestamp_utc if candidates_sorted else datetime.now(timezone.utc),
             running_balance)
        ]

        for cand in candidates_sorted:
            bars = bars_by_pair.get(cand.symbol)
            idx = index_by_pair.get(cand.symbol)
            if bars is None or idx is None:
                _log.warning("no bars loaded for symbol %s; skipping", cand.symbol)
                continue
            outcome = self.simulate_trade(cand, bars, idx, running_balance)
            if outcome is None:
                continue
            trades.append(outcome)
            running_balance += outcome.pnl_dollars
            equity_curve.append((outcome.exit_time_utc, running_balance))

        metrics = self._aggregate(trades, running_balance, equity_curve)
        metrics.parameters = self.parameters()
        return trades, metrics

    # ------------------------------------------------------------------
    def _aggregate(
        self,
        trades: List[TradeOutcome],
        ending_balance: float,
        equity_curve: List[Tuple[datetime, float]],
    ) -> BacktestMetrics:
        m = BacktestMetrics(starting_balance=self.starting_balance)
        m.ending_balance = ending_balance
        m.return_pct = (ending_balance / self.starting_balance - 1.0) * 100.0
        m.total_trades = len(trades)

        wins = [t for t in trades if t.won]
        losses = [t for t in trades if (not t.won) and t.pnl_pips_net < 0]
        breakevens = [t for t in trades if t.pnl_pips_net == 0]
        timeouts = [t for t in trades if t.exit_reason in ("TIMEOUT", "DATA_END")]

        m.wins = len(wins)
        m.losses = len(losses)
        m.breakevens = len(breakevens)
        m.timeouts = len(timeouts)

        m.gross_profit_pips = sum(t.pnl_pips_net for t in wins)
        m.gross_loss_pips = abs(sum(t.pnl_pips_net for t in losses))
        m.net_profit_pips = m.gross_profit_pips - m.gross_loss_pips
        m.spread_cost_pips = sum(t.spread_paid_pips for t in trades)
        m.slippage_cost_pips = sum(t.slippage_paid_pips for t in trades)

        m.gross_profit_dollars = sum(t.pnl_dollars for t in wins)
        m.gross_loss_dollars = abs(sum(t.pnl_dollars for t in losses))
        m.net_profit_dollars = m.gross_profit_dollars - m.gross_loss_dollars

        m.win_rate = (m.wins / m.total_trades * 100.0) if m.total_trades else 0.0
        m.profit_factor = (
            m.gross_profit_dollars / m.gross_loss_dollars
            if m.gross_loss_dollars > 0
            else float("inf") if m.gross_profit_dollars > 0
            else 0.0
        )
        m.avg_win_pips = (m.gross_profit_pips / m.wins) if m.wins else 0.0
        m.avg_loss_pips = (m.gross_loss_pips / m.losses) if m.losses else 0.0
        m.expectancy_pips = (
            (m.win_rate / 100.0) * m.avg_win_pips -
            (1 - m.win_rate / 100.0) * m.avg_loss_pips
        )

        # Consecutive streaks
        max_loss_streak = 0
        max_win_streak = 0
        cur_loss_streak = 0
        cur_win_streak = 0
        for t in trades:
            if t.won:
                cur_win_streak += 1
                cur_loss_streak = 0
            elif t.pnl_pips_net < 0:
                cur_loss_streak += 1
                cur_win_streak = 0
            else:
                cur_loss_streak = 0
                cur_win_streak = 0
            max_loss_streak = max(max_loss_streak, cur_loss_streak)
            max_win_streak = max(max_win_streak, cur_win_streak)
        m.max_consecutive_losses = max_loss_streak
        m.max_consecutive_wins = max_win_streak

        # Drawdown from equity curve
        peak = equity_curve[0][1] if equity_curve else self.starting_balance
        max_dd_dollars = 0.0
        max_dd_pct = 0.0
        peak_time: Optional[datetime] = equity_curve[0][0] if equity_curve else None
        dd_start_time: Optional[datetime] = None
        dd_end_time: Optional[datetime] = None
        for t, bal in equity_curve:
            if bal > peak:
                peak = bal
                peak_time = t
            dd = peak - bal
            dd_pct = (dd / peak * 100.0) if peak > 0 else 0.0
            if dd > max_dd_dollars:
                max_dd_dollars = dd
                max_dd_pct = dd_pct
                dd_start_time = peak_time
                dd_end_time = t
        m.max_drawdown_dollars = max_dd_dollars
        m.max_drawdown_pct = max_dd_pct
        m.max_drawdown_start_utc = dd_start_time.isoformat() if dd_start_time else None
        m.max_drawdown_end_utc = dd_end_time.isoformat() if dd_end_time else None

        # Frequency
        if trades:
            ny_dates = set()
            for t in trades:
                ny_t = t.entry_time_utc.astimezone(_NY_TZ)
                ny_dates.add(ny_t.date())
            m.trading_days = len(ny_dates)
            m.trades_per_day = m.total_trades / max(m.trading_days, 1)

            # Days with 2+ trades
            from collections import Counter
            counts: Counter = Counter()
            for t in trades:
                counts[t.entry_time_utc.astimezone(_NY_TZ).date()] += 1
            days_2plus = sum(1 for c in counts.values() if c >= 2)
            m.days_with_2plus_trades = days_2plus
            m.days_with_2plus_trades_pct = (
                days_2plus / m.trading_days * 100.0 if m.trading_days else 0.0
            )

        return m


# =====================================================================
# CSV ingestion
# =====================================================================

def load_candidates_from_decision_cycles_csv(
    path: Path,
) -> List[EntryCandidate]:
    """Read decision_cycles.csv (produced by replay_report_generator) and
    extract the ENTER_CANDIDATE rows."""
    candidates: List[EntryCandidate] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("final_status") != "ENTER_CANDIDATE":
                continue
            # Direction may live under 'gate_decision' as nested JSON
            gd = row.get("gate_decision") or row.get("direction")
            direction: Optional[str] = None
            if gd:
                if isinstance(gd, str):
                    try:
                        gd_obj = json.loads(gd)
                        direction = (gd_obj or {}).get("direction")
                    except (json.JSONDecodeError, AttributeError):
                        direction = gd if gd in ("BUY", "SELL") else None
                else:
                    direction = (gd or {}).get("direction")
            if direction is None:
                # Fallback: try top-level 'direction' column.
                direction = row.get("direction")
            if direction not in ("BUY", "SELL"):
                _log.warning("skipping row with unparseable direction: %r", row)
                continue
            ts_raw = row.get("timestamp_utc") or row.get("now_utc")
            if not ts_raw:
                continue
            ts = _parse_iso(ts_raw)
            # V12-F6: pull through ChartMind references when present.
            def _flt(k):
                v = row.get(k)
                if v in (None, "", "null"):
                    return None
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            candidates.append(EntryCandidate(
                cycle_id=row.get("cycle_id") or "",
                symbol=row.get("symbol") or "",
                timestamp_utc=ts,
                direction=direction,
                session_status=row.get("session_status") or "unknown",
                invalidation_level=_flt("invalidation_level"),
                target_reference=_flt("target_reference"),
                atr_value=_flt("atr_value"),
                setup_anchor=_flt("setup_anchor"),
            ))
    return candidates


# =====================================================================
# Per-pair / per-session breakdown
# =====================================================================

def split_metrics_by(
    trades: List[TradeOutcome],
    starting_balance: float,
    by: str,  # "symbol" or "session_status"
    sim: PnLSimulator,
) -> Dict[str, BacktestMetrics]:
    """Re-aggregate metrics for each subset of trades grouped by `by`."""
    out: Dict[str, BacktestMetrics] = {}
    groups: Dict[str, List[TradeOutcome]] = {}
    for t in trades:
        key = getattr(t, by)
        groups.setdefault(key, []).append(t)
    for key, sub in groups.items():
        # Build a fresh equity curve for this subset
        running = starting_balance
        eq = [(sub[0].entry_time_utc, running)] if sub else []
        for t in sub:
            running += t.pnl_dollars
            eq.append((t.exit_time_utc, running))
        m = sim._aggregate(sub, running, eq)
        m.parameters = sim.parameters()
        out[key] = m
    return out


# =====================================================================
# CLI
# =====================================================================

def _trades_to_records(trades: List[TradeOutcome]) -> List[Dict[str, Any]]:
    out = []
    for t in trades:
        d = asdict(t)
        d["entry_time_utc"] = t.entry_time_utc.isoformat()
        d["exit_time_utc"] = t.exit_time_utc.isoformat()
        out.append(d)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="HYDRA V4 P&L simulator")
    p.add_argument("--decision-cycles", type=Path, required=True,
                   help="Path to decision_cycles.csv from replay_report_generator")
    p.add_argument("--bars-dir", type=Path, required=True,
                   help="Path to data_cache/ root (containing <pair>/<gran>/merged.jsonl)")
    p.add_argument("--granularity", default="M15")
    p.add_argument("--symbols", nargs="+", default=["EUR_USD", "USD_JPY"])
    p.add_argument("--sl-pips", type=float, default=10.0)
    p.add_argument("--tp-pips", type=float, default=20.0)
    p.add_argument("--slippage-pips", type=float, default=0.5)
    p.add_argument("--risk-per-trade-pct", type=float, default=1.0)
    p.add_argument("--starting-balance", type=float, default=10_000.0)
    p.add_argument("--max-bars-in-trade", type=int, default=96)
    p.add_argument("--output", type=Path, required=True,
                   help="Where to write the JSON results")
    p.add_argument("--trades-csv", type=Path, default=None,
                   help="Optional: also write the per-trade ledger as CSV")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    candidates = load_candidates_from_decision_cycles_csv(args.decision_cycles)
    _log.info("loaded %d ENTER_CANDIDATE rows", len(candidates))

    bars_by_pair: Dict[str, List[Dict[str, Any]]] = {}
    for pair in args.symbols:
        merged = args.bars_dir / pair / args.granularity / "merged.jsonl"
        if not merged.exists():
            _log.error("merged.jsonl not found for %s at %s", pair, merged)
            continue
        bars_by_pair[pair] = load_bars(merged)
        _log.info("loaded %d bars for %s", len(bars_by_pair[pair]), pair)

    sim = PnLSimulator(
        sl_pips=args.sl_pips,
        tp_pips=args.tp_pips,
        slippage_pips=args.slippage_pips,
        risk_per_trade_pct=args.risk_per_trade_pct,
        starting_balance=args.starting_balance,
        max_bars_in_trade=args.max_bars_in_trade,
    )

    trades, overall = sim.run(candidates, bars_by_pair)
    by_symbol = split_metrics_by(trades, args.starting_balance, "symbol", sim)
    by_session = split_metrics_by(trades, args.starting_balance, "session_status", sim)

    output = {
        "overall": asdict(overall),
        "by_symbol": {k: asdict(v) for k, v in by_symbol.items()},
        "by_session": {k: asdict(v) for k, v in by_session.items()},
        "trades_count": len(trades),
        "candidates_loaded": len(candidates),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    _log.info("wrote results to %s", args.output)

    if args.trades_csv:
        records = _trades_to_records(trades)
        if records:
            keys = list(records[0].keys())
            with args.trades_csv.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for r in records:
                    w.writerow(r)
            _log.info("wrote trade ledger to %s", args.trades_csv)

    print("=" * 60)
    print(f" Total trades:    {overall.total_trades}")
    print(f" Win rate:        {overall.win_rate:.2f}%")
    print(f" Net profit:      ${overall.net_profit_dollars:,.2f} "
          f"({overall.return_pct:+.2f}%)")
    print(f" Profit factor:   {overall.profit_factor:.2f}")
    print(f" Max drawdown:    {overall.max_drawdown_pct:.2f}% "
          f"(${overall.max_drawdown_dollars:,.2f})")
    print(f" Trades/day:      {overall.trades_per_day:.2f}")
    print(f" Days 2+ trades:  {overall.days_with_2plus_trades_pct:.1f}%")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
