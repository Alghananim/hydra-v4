"""HYDRA 4.7 War Room — Step 3: rejected-trade shadow P&L.

For every cycle that was rejected for a *specific* reason, simulate what
would have happened if it had entered the trade ChartMind suggested,
using ONLY future bars from the data cache (no lookahead leak — we read
bars *after* the decision timestamp from the same cached series the
backtest uses).

Three shadow modes are computed per rejected cycle (when applicable):

  1. shadow_chart    : enter in ChartMind's direction whenever
                       chart.decision in {BUY, SELL}, regardless of grade
                       or consensus. ("What if ChartMind had final say?")
  2. shadow_grade_B  : enter when ChartMind is directional AND
                       (chart.grade in {A, A+, B}) AND no opposing vote.
                       ("What if the grade gate accepted B?")
  3. shadow_2_of_3   : enter when ChartMind is directional AND at least
                       one other mind matches direction or is WAIT.
                       (This is what V4.7 already does — sanity check.)

P&L per shadow trade is computed against fixed SL/TP in pips:
  - SL = 20 pips
  - TP = 40 pips (R:R = 1:2)
  - max hold = 24 bars (6h on M15)
  - cost   = 1.5 pips spread+slippage round-trip

The first of {SL hit, TP hit, max hold reached} wins. SL/TP collisions
within the same bar are resolved conservatively as SL hit (worst-case for
the trade, fairest for evaluation). Costs are subtracted from the gross
result.

We aggregate:
  - trade count per mode
  - win rate
  - net pips (sum of pip outcomes minus costs)
  - max drawdown in pips
  - per-pair breakdown
  - per-session-window breakdown
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


PIP = {"EUR_USD": 0.0001, "USD_JPY": 0.01}
SL_PIPS = 20.0
TP_PIPS = 40.0
COST_PIPS = 1.5
MAX_HOLD_BARS = 24


@dataclass
class ShadowTrade:
    cycle_id: str
    timestamp_utc: str
    symbol: str
    direction: str
    mode: str
    entry_price: float
    exit_price: float
    pips: float
    bars_held: int
    outcome: str  # TP / SL / TIMEOUT


def _iter_cycles(cycles_path: Path) -> Iterator[Dict[str, Any]]:
    if not cycles_path.exists():
        return
    with cycles_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "cycle_id" in rec:
                yield rec


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "." in s:
        head, tail = s.split(".", 1)
        idx = max(tail.find("+"), tail.find("-"))
        frac, tz = (tail[:idx], tail[idx:]) if idx >= 0 else (tail, "")
        s = f"{head}.{frac[:6]}{tz}"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def _load_bars_index(data_cache_dir: Path, pair: str) -> List[Dict[str, Any]]:
    """Load M15 merged.jsonl for one pair as a list ordered by time."""
    p = data_cache_dir / pair / "M15" / "merged.jsonl"
    out: List[Dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(d)
    out.sort(key=lambda b: b["time"])
    return out


def _ts_to_index(bars: List[Dict[str, Any]]) -> Dict[str, int]:
    return {b["time"]: i for i, b in enumerate(bars)}


def _simulate(
    bars: List[Dict[str, Any]],
    entry_idx: int,
    direction: str,
    pair: str,
) -> Optional[Tuple[float, float, float, int, str]]:
    """Return (entry, exit, pips_after_cost, bars_held, outcome)."""
    if entry_idx + 1 >= len(bars):
        return None
    pip = PIP[pair]
    entry_bar = bars[entry_idx]
    entry_price = float(entry_bar["mid"]["c"])
    if direction == "BUY":
        sl = entry_price - SL_PIPS * pip
        tp = entry_price + TP_PIPS * pip
    else:
        sl = entry_price + SL_PIPS * pip
        tp = entry_price - TP_PIPS * pip

    end = min(len(bars), entry_idx + 1 + MAX_HOLD_BARS)
    for i in range(entry_idx + 1, end):
        b = bars[i]
        h = float(b["mid"]["h"])
        l = float(b["mid"]["l"])
        # Conservative: if both hit within the same bar, count SL.
        if direction == "BUY":
            sl_hit = l <= sl
            tp_hit = h >= tp
        else:
            sl_hit = h >= sl
            tp_hit = l <= tp
        if sl_hit:
            return (entry_price, sl,
                    -SL_PIPS - COST_PIPS, i - entry_idx, "SL")
        if tp_hit:
            return (entry_price, tp,
                    TP_PIPS - COST_PIPS, i - entry_idx, "TP")

    # Timeout — exit at close of last bar.
    last_idx = end - 1
    if last_idx <= entry_idx:
        return None
    exit_price = float(bars[last_idx]["mid"]["c"])
    if direction == "BUY":
        gross_pips = (exit_price - entry_price) / pip
    else:
        gross_pips = (entry_price - exit_price) / pip
    return (entry_price, exit_price, gross_pips - COST_PIPS,
            last_idx - entry_idx, "TIMEOUT")


def _eligible(rec: Dict[str, Any], mode: str) -> Optional[str]:
    """Return the trade direction if the cycle qualifies under `mode`."""
    chart = rec.get("chart") or {}
    news = rec.get("news") or {}
    market = rec.get("market") or {}
    chart_dir = chart.get("decision")
    if chart_dir not in ("BUY", "SELL"):
        return None
    if rec.get("session_status") == "outside_window":
        return None
    if any(m.get("should_block") for m in (news, market, chart)):
        return None

    if mode == "shadow_chart":
        return chart_dir

    if mode == "shadow_grade_B":
        if chart.get("grade") not in ("A+", "A", "B"):
            return None
        # No opposing vote
        opp = "SELL" if chart_dir == "BUY" else "BUY"
        if news.get("decision") == opp or market.get("decision") == opp:
            return None
        return chart_dir

    if mode == "shadow_2_of_3":
        # ChartMind directional + at least one other matching/non-opposing
        opp = "SELL" if chart_dir == "BUY" else "BUY"
        non_opposing = sum(
            1 for m in (news, market)
            if m.get("decision") != opp
        )
        if non_opposing >= 1:
            return chart_dir
        return None

    return None


def compute(
    cycles_path: Path,
    data_cache_dir: Path,
    modes: Tuple[str, ...] = ("shadow_chart", "shadow_grade_B",
                              "shadow_2_of_3"),
) -> Dict[str, Any]:
    bars_by_pair: Dict[str, List[Dict[str, Any]]] = {}
    idx_by_pair: Dict[str, Dict[str, int]] = {}
    for pair in ("EUR_USD", "USD_JPY"):
        bars = _load_bars_index(data_cache_dir, pair)
        bars_by_pair[pair] = bars
        idx_by_pair[pair] = _ts_to_index(bars)

    results: Dict[str, List[ShadowTrade]] = {m: [] for m in modes}

    for rec in _iter_cycles(cycles_path):
        sym = rec.get("symbol")
        if sym not in bars_by_pair:
            continue
        ts = rec.get("timestamp_utc")
        if not ts:
            continue
        bar_key = ts.replace("+00:00", "Z").replace("Z", "Z") if ts else None
        # cycles.jsonl uses ISO with "+00:00"; bars use "...Z". Convert.
        # Build the equivalent bar timestamp string the cache uses:
        try:
            dt = _parse_iso(ts)
        except Exception:
            continue
        bar_ts = dt.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        idx = idx_by_pair[sym].get(bar_ts)
        if idx is None:
            continue
        for mode in modes:
            direction = _eligible(rec, mode)
            if direction is None:
                continue
            sim = _simulate(bars_by_pair[sym], idx, direction, sym)
            if sim is None:
                continue
            entry_price, exit_price, pips, held, outcome = sim
            results[mode].append(ShadowTrade(
                cycle_id=rec.get("cycle_id") or "",
                timestamp_utc=ts,
                symbol=sym,
                direction=direction,
                mode=mode,
                entry_price=entry_price,
                exit_price=exit_price,
                pips=pips,
                bars_held=held,
                outcome=outcome,
            ))

    # Aggregate
    summary: Dict[str, Any] = {}
    for mode, trades in results.items():
        net = sum(t.pips for t in trades)
        wins = sum(1 for t in trades if t.outcome == "TP")
        losses = sum(1 for t in trades if t.outcome == "SL")
        timeouts = sum(1 for t in trades if t.outcome == "TIMEOUT")
        # Equity curve + drawdown
        eq = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(trades, key=lambda x: x.timestamp_utc):
            eq += t.pips
            peak = max(peak, eq)
            max_dd = min(max_dd, eq - peak)
        per_pair: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"trades": 0, "net_pips": 0.0, "wins": 0, "losses": 0,
                     "timeouts": 0}
        )
        for t in trades:
            ps = per_pair[t.symbol]
            ps["trades"] += 1
            ps["net_pips"] += t.pips
            if t.outcome == "TP":
                ps["wins"] += 1
            elif t.outcome == "SL":
                ps["losses"] += 1
            else:
                ps["timeouts"] += 1
        summary[mode] = {
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "timeouts": timeouts,
            "win_rate_excl_timeout": (wins / (wins + losses) * 100.0)
                                       if (wins + losses) else None,
            "net_pips_after_cost": round(net, 1),
            "avg_pips_per_trade": round(net / len(trades), 2) if trades else None,
            "max_drawdown_pips": round(max_dd, 1),
            "per_pair": {k: {**v,
                              "net_pips": round(v["net_pips"], 1)}
                          for k, v in per_pair.items()},
        }

    return {
        "params": {
            "SL_PIPS": SL_PIPS, "TP_PIPS": TP_PIPS,
            "COST_PIPS": COST_PIPS, "MAX_HOLD_BARS": MAX_HOLD_BARS,
        },
        "summary_by_mode": summary,
        "trade_counts_total": {m: len(v) for m, v in results.items()},
    }, results


def render_markdown(d: Dict[str, Any]) -> str:
    lines = ["# HYDRA 4.7 — Step 3 Shadow P&L\n"]
    lines.append(
        f"Params: SL {d['params']['SL_PIPS']}p, TP {d['params']['TP_PIPS']}p, "
        f"cost {d['params']['COST_PIPS']}p, max hold "
        f"{d['params']['MAX_HOLD_BARS']} bars (6h on M15)\n"
    )
    for mode, info in d["summary_by_mode"].items():
        lines.append(f"## Mode: `{mode}`")
        lines.append(f"- trades: {info['trades']:,}")
        lines.append(f"- wins (TP): {info['wins']:,}")
        lines.append(f"- losses (SL): {info['losses']:,}")
        lines.append(f"- timeouts: {info['timeouts']:,}")
        wr = info.get("win_rate_excl_timeout")
        if wr is not None:
            lines.append(f"- win rate (excl. timeouts): {wr:.1f}%")
        lines.append(f"- net pips after cost: **{info['net_pips_after_cost']}**")
        if info.get("avg_pips_per_trade") is not None:
            lines.append(f"- avg pips / trade: {info['avg_pips_per_trade']}")
        lines.append(f"- max drawdown (pips): {info['max_drawdown_pips']}")
        lines.append("- per-pair:")
        for pair, sub in info["per_pair"].items():
            lines.append(f"  - {pair}: trades={sub['trades']:,}, "
                          f"net_pips={sub['net_pips']}, "
                          f"wins={sub['wins']}, losses={sub['losses']}, "
                          f"timeouts={sub['timeouts']}")
        lines.append("")
    return "\n".join(lines)


def run(cycles_path: Path, data_cache_dir: Path,
        out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, trades = compute(cycles_path, data_cache_dir)
    (out_dir / "shadow_pnl.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "shadow_pnl.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    # Also dump every shadow trade for downstream Red Team probing.
    with (out_dir / "shadow_trades.jsonl").open("w", encoding="utf-8") as f:
        for mode, ts in trades.items():
            for t in ts:
                f.write(json.dumps(asdict(t)) + "\n")
    return summary


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=Path, required=True)
    p.add_argument("--data-cache", type=Path, required=True,
                   help="HYDRA V4/data_cache directory")
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.cycles, args.data_cache, args.out_dir)
    print(f"shadow P&L written to {args.out_dir}")
