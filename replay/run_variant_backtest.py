"""HYDRA V5.2+ — variant-aware backtest runner.

Imports a named variant from `replay.variants`, applies its monkey-patch
in-process, runs the same 2-year backtest, and writes outputs into a
variant-scoped folder.

Crucially: the patch is local to this Python process. It NEVER mutates
the on-disk source. Live trading is impossible from this script.

Usage:
    python replay/run_variant_backtest.py \
        --variant v5_2_drop_volatility_normal \
        --output-dir replay_runs/v5_2 \
        --time-budget-s 300

The runner reuses the same chunked, resumable engine as
`run_v47_backtest.py`. On completion, the war room can run on this
variant's cycles.jsonl exactly the same way it runs on V5.0.
"""
from __future__ import annotations

import argparse
import importlib
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
from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4


def _import_variant(name: str):
    return importlib.import_module(f"replay.variants.{name}")


# V5.7 hook: variants can set this to 0 to exclude the bar AT now_utc
# from the visible slice (true no-lookahead). Default 1 preserves V5.0
# slicing for all other variants.
_VARIANT_NO_LOOKAHEAD_OFFSET = 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True,
                   help="Name of variant module under replay.variants")
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--lookback-bars", type=int, default=500)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--time-budget-s", type=int, default=300)
    p.add_argument("--checkpoint-every", type=int, default=1000)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    variant = _import_variant(args.variant)
    label, revert = variant.apply()
    description = variant.describe()
    (args.output_dir / "variant_describe.json").write_text(
        json.dumps(description, indent=2, default=str), encoding="utf-8"
    )
    print(f"VARIANT: {label}")
    print(f"hypothesis: {description['hypothesis']}")

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
        run_meta = state["run_meta"]
        print(f"RESUME from {resume_idx}")
    else:
        resume_idx = 0
        counters = {"total": 0, "ENTER_CANDIDATE": 0, "WAIT": 0,
                    "BLOCK": 0, "ORCHESTRATOR_ERROR": 0, "errors": 0}
        run_meta = None

    pairs = ["EUR_USD", "USD_JPY"]
    print("loading bars...")
    bars_by_pair = {pp: load_bars(pp) for pp in pairs}
    end_utc = max(bars_by_pair[pp][-1].timestamp for pp in pairs)
    start_utc = end_utc - timedelta(days=args.days)
    print(f"window {start_utc.isoformat()} -> {end_utc.isoformat()} "
          f"({args.days}d)")

    if run_meta is None:
        run_meta = {
            "variant": label,
            "start_utc": start_utc.isoformat(),
            "end_utc": end_utc.isoformat(),
            "days": args.days,
            "lookback_bars": args.lookback_bars,
        }

    occ = build_replay_occurrences(start_utc - timedelta(days=7),
                                    end_utc + timedelta(days=7))
    scheduler = EventScheduler()
    scheduler.load_occurrences(occ)
    nb_dir = args.output_dir / "smartnotebook"
    nb_dir.mkdir(parents=True, exist_ok=True)
    notebook = SmartNoteBookV4(nb_dir)
    news = ReplayNewsMindV4(scheduler=scheduler)
    orch = HydraOrchestratorV4(smartnotebook=notebook, newsmind=news)

    timeline = sorted({b.timestamp for pp in pairs
                        for b in bars_by_pair[pp]
                        if start_utc <= b.timestamp <= end_utc})
    n_timeline = len(timeline)
    print(f"timeline {n_timeline} starting at {resume_idx}")

    bar_index = {pp: {b.timestamp: i for i, b in enumerate(bars_by_pair[pp])}
                  for pp in pairs}

    mode = "a" if resume_idx > 0 else "w"
    cf = cycles_path.open(mode)
    ef = enter_path.open(mode)

    started = time.time()
    last_log = time.time()
    deadline = started + args.time_budget_s
    ti = resume_idx
    try:
        while ti < n_timeline:
            if time.time() > deadline:
                break
            now_utc = timeline[ti]
            for symbol in pairs:
                idx = bar_index[symbol].get(now_utc)
                if idx is None:
                    continue
                offset = _VARIANT_NO_LOOKAHEAD_OFFSET
                lo = max(0, idx + offset - args.lookback_bars)
                visible = bars_by_pair[symbol][lo:idx + offset]
                if not visible:
                    continue
                try:
                    res = orch.run_cycle(
                        symbol=symbol, now_utc=now_utc,
                        bars_by_pair={symbol: visible},
                        bars_by_tf={"M15": visible},
                    )
                    rec = cycle_to_record(res)
                    cf.write(json.dumps(rec) + "\n")
                    counters["total"] += 1
                    counters[res.final_status] = counters.get(
                        res.final_status, 0) + 1
                    if res.final_status == "ENTER_CANDIDATE":
                        ef.write(json.dumps(rec) + "\n")
                        ef.flush()
                except Exception as e:
                    counters["errors"] += 1
                    cf.write(json.dumps({"error": str(e), "symbol": symbol,
                                         "ts": now_utc.isoformat()}) + "\n")
            ti += 1
            if ((ti - resume_idx) % args.checkpoint_every == 0
                    or (time.time() - last_log) > 10):
                cf.flush()
                ef.flush()
                print(
                    f"  [{label}] idx={ti}/{n_timeline} "
                    f"({ti / n_timeline * 100:.1f}%) "
                    f"total={counters['total']} "
                    f"ENTER={counters['ENTER_CANDIDATE']} "
                    f"WAIT={counters['WAIT']} BLOCK={counters['BLOCK']} "
                    f"err={counters['errors']}",
                    flush=True,
                )
                last_log = time.time()
    finally:
        cf.close()
        ef.close()
        revert()

    state_path.write_text(json.dumps(
        {"next_idx": ti, "counters": counters, "run_meta": run_meta},
        indent=2,
    ))
    if ti >= n_timeline:
        summary = {**run_meta, "pairs": pairs, "timeline_size": n_timeline,
                   "calendar_occurrences": len(occ), "counters": counters}
        summary_path.write_text(json.dumps(summary, indent=2))
        done_marker.write_text("done")
        print(f"DONE [{label}]. {counters}")
    else:
        progress_path.write_text(f"idx={ti}/{n_timeline}")
        print(f"CHUNK done [{label}]. idx={ti}/{n_timeline} "
              f"({ti / n_timeline * 100:.1f}%). counters={counters}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crash_path = Path(sys.argv[sys.argv.index("--output-dir") + 1]
                          if "--output-dir" in sys.argv else ".") / "CRASH"
        crash_path.write_text(
            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )
        raise
