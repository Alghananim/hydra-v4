"""HYDRA V11 — backtest runner over 6 pairs on M5 (or M15 fallback).

Same chunked + resumable pattern as run_v47_backtest.py, with these
V11 additions:

  - Iterates over `v11.pairs.PAIRS` (6 instruments).
  - Loads M5 bars from `data_cache/<PAIR>/M5/merged.jsonl` if present;
    falls back to M15 with a clearly logged degradation message.
  - Uses `HydraOrchestratorV11` wrapper for per-pair grade gates +
    extra-setup detection.
  - Cycle records carry the V11 context (window, extra setups).

Output:
  state.json            — resumable cursor + counters per pair
  cycles.jsonl          — per-cycle records
  enter_candidates.jsonl
  summary.json          — per-pair breakdown when DONE
  per_pair_state.json   — fine-grained per-pair counters
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from replay.run_v47_backtest import (
    cycle_to_record, load_bars, parse_iso, to_bar,
)
from marketmind.v4.models import Bar
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
from newsmind.v4.event_scheduler import EventScheduler
from replay.replay_calendar import build_replay_occurrences
from replay.replay_newsmind import ReplayNewsMindV4

from v11.pairs import all_pairs
from v11.orchestrator import HydraOrchestratorV11


def _try_load_bars(pair: str, tf: str) -> list:
    """Try data_cache/<PAIR>/<tf>/merged.jsonl. Return [] if missing."""
    path = PROJECT_ROOT / "data_cache" / pair / tf / "merged.jsonl"
    if not path.exists():
        return []
    bars = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                bars.append(to_bar(json.loads(line)))
    bars.sort(key=lambda b: b.timestamp)
    return bars


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--lookback-bars", type=int, default=500)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--time-budget-s", type=int, default=300)
    p.add_argument("--checkpoint-every", type=int, default=2000)
    p.add_argument("--prefer-tf", default="M5",
                   help="Try this TF first, fall back to M15.")
    p.add_argument("--pairs", default=None,
                   help="Comma-separated subset (default: all 6 V11 pairs)")
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    state_path = args.output_dir / "state.json"
    cycles_path = args.output_dir / "cycles.jsonl"
    enter_path = args.output_dir / "enter_candidates.jsonl"
    summary_path = args.output_dir / "summary.json"
    progress_path = args.output_dir / "progress.txt"
    done_marker = args.output_dir / "DONE"

    if state_path.exists():
        state = json.loads(state_path.read_text())
        resume_idx = state["next_idx"]
        counters = state["counters"]
        per_pair = state.get("per_pair", {})
        run_meta = state["run_meta"]
        print(f"RESUME from {resume_idx}")
    else:
        resume_idx = 0
        counters = {"total": 0, "ENTER_CANDIDATE": 0, "WAIT": 0, "BLOCK": 0,
                    "ORCHESTRATOR_ERROR": 0, "errors": 0}
        per_pair = {}
        run_meta = None

    pair_list = (args.pairs.split(",") if args.pairs else list(all_pairs()))
    pair_list = [p.strip() for p in pair_list if p.strip()]
    print(f"V11 pairs: {pair_list}")

    bars_by_pair: dict = {}
    for sym in pair_list:
        for tf in (args.prefer_tf, "M15"):
            bars = _try_load_bars(sym, tf)
            if bars:
                bars_by_pair[sym] = (tf, bars)
                print(f"  {sym}: loaded {len(bars):,} bars from {tf}")
                break
        else:
            print(f"  {sym}: NO data — will be skipped")
    if not bars_by_pair:
        print("ERROR: no bars loaded for any pair. Run v11.m5_data_fetch first.",
              file=sys.stderr)
        sys.exit(1)

    end_utc = max(bars[-1].timestamp for _, bars in bars_by_pair.values())
    start_utc = end_utc - timedelta(days=args.days)
    print(f"window {start_utc.isoformat()} -> {end_utc.isoformat()} "
          f"({args.days}d)")

    if run_meta is None:
        run_meta = {
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "days": args.days,
            "lookback_bars": args.lookback_bars,
            "pairs": pair_list,
            "tf_per_pair": {p: tf for p, (tf, _) in bars_by_pair.items()},
        }

    occ = build_replay_occurrences(start_utc - timedelta(days=7),
                                    end_utc + timedelta(days=7))
    scheduler = EventScheduler()
    scheduler.load_occurrences(occ)
    nb_dir = args.output_dir / "smartnotebook"
    nb_dir.mkdir(parents=True, exist_ok=True)
    notebook = SmartNoteBookV4(nb_dir)
    news = ReplayNewsMindV4(scheduler=scheduler)
    orch = HydraOrchestratorV11(smartnotebook=notebook, newsmind=news)

    # Build a single sorted timeline across all pairs (deduped).
    all_ts = set()
    for sym, (tf, bars) in bars_by_pair.items():
        for b in bars:
            if start_utc <= b.timestamp <= end_utc:
                all_ts.add(b.timestamp)
    timeline = sorted(all_ts)
    n_timeline = len(timeline)
    print(f"timeline {n_timeline:,} unique timestamps")

    bar_index = {sym: {b.timestamp: i for i, b in enumerate(bars)}
                  for sym, (_, bars) in bars_by_pair.items()}

    mode = "a" if resume_idx > 0 else "w"
    cf = cycles_path.open(mode)
    ef = enter_path.open(mode)
    started = time.time()
    deadline = started + args.time_budget_s
    last_log = time.time()
    ti = resume_idx

    while ti < n_timeline:
        if time.time() > deadline:
            break
        now_utc = timeline[ti]
        for symbol, (tf, sym_bars) in bars_by_pair.items():
            idx = bar_index[symbol].get(now_utc)
            if idx is None:
                continue
            lo = max(0, idx + 1 - args.lookback_bars)
            visible = sym_bars[lo:idx + 1]
            if not visible:
                continue
            try:
                res = orch.run_cycle(
                    symbol=symbol, now_utc=now_utc,
                    bars_by_pair={symbol: visible},
                    bars_by_tf={tf: visible},
                )
                rec = cycle_to_record(res)
                # Add V11 context if present
                v11ctx = getattr(res, "v11_context", None)
                if v11ctx is not None:
                    rec["v11_window"] = v11ctx.window_label
                    rec["v11_inside_bar"] = v11ctx.inside_bar
                    rec["v11_range_break"] = v11ctx.range_break
                    rec["v11_mean_reversion"] = v11ctx.mean_reversion
                    rec["v11_extra_setup_count"] = v11ctx.extra_setup_count
                cf.write(json.dumps(rec) + "\n")
                counters["total"] += 1
                counters[res.final_status] = counters.get(res.final_status, 0) + 1
                pp = per_pair.setdefault(symbol, {"total": 0, "ENTER_CANDIDATE": 0})
                pp["total"] += 1
                pp[res.final_status] = pp.get(res.final_status, 0) + 1
                if res.final_status == "ENTER_CANDIDATE":
                    ef.write(json.dumps(rec) + "\n")
                    ef.flush()
            except Exception as e:
                counters["errors"] += 1
                cf.write(json.dumps({
                    "error": str(e), "symbol": symbol,
                    "ts": now_utc.isoformat(),
                }) + "\n")
        ti += 1
        if ((ti - resume_idx) % args.checkpoint_every == 0
                or (time.time() - last_log) > 10):
            cf.flush()
            ef.flush()
            print(
                f"  idx={ti:,}/{n_timeline:,} ({ti / n_timeline * 100:.1f}%) "
                f"total={counters['total']:,} "
                f"ENTER={counters['ENTER_CANDIDATE']} "
                f"WAIT={counters['WAIT']} BLOCK={counters['BLOCK']} "
                f"err={counters['errors']}",
                flush=True,
            )
            last_log = time.time()

    cf.close()
    ef.close()
    state_path.write_text(json.dumps({
        "next_idx": ti, "counters": counters,
        "per_pair": per_pair, "run_meta": run_meta,
    }, indent=2))
    if ti >= n_timeline:
        summary = {**run_meta, "timeline_size": n_timeline,
                   "calendar_occurrences": len(occ),
                   "counters": counters, "per_pair": per_pair}
        summary_path.write_text(json.dumps(summary, indent=2))
        done_marker.write_text("done")
        print(f"DONE. {counters}")
        print(f"per pair: {per_pair}")
    else:
        progress_path.write_text(f"idx={ti}/{n_timeline}")
        print(f"CHUNK done. idx={ti}/{n_timeline} "
              f"({ti / n_timeline * 100:.1f}%). counters={counters}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crash = Path(sys.argv[sys.argv.index("--output-dir") + 1]
                     if "--output-dir" in sys.argv else ".") / "CRASH"
        crash.write_text(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise
