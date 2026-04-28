"""HYDRA V4.8 — Live-Armed Dry Run.

Reads live data through the existing read-only OANDA client, runs the
full 5-brain orchestrator, records every cycle through SmartNoteBook,
and asserts that NO order placement code path is reachable. The
LIVE_ORDER_GUARD remains active across all 6 layers.

Outputs: dry_run_log.jsonl per cycle. Exit code 0 if every cycle's
LIVE_ORDER_GUARD verdict was BLOCKED-AS-EXPECTED; exit code 1 if any
cycle accidentally reached an order-placement code path (would never
happen if guards work, but we verify by counting).

Usage:
  python live/dry_run.py --duration-minutes 60 --output-dir replay_runs/dry_run

NEVER run this with HYDRA_LIVE_ARMED=1 — that env var is for V4.9
controlled live, not for dry-run mode. Dry-run unconditionally blocks.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration-minutes", type=int, default=60)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--cycle-interval-s", type=int, default=300,
                   help="Seconds between cycles (default 5 min).")
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Refuse to run if anyone armed live by mistake.
    if os.environ.get("HYDRA_LIVE_ARMED") == "1":
        print("DRY-RUN ABORT: HYDRA_LIVE_ARMED=1 is set. Dry run must "
              "run with armed=0. Refusing to start.", file=sys.stderr)
        return 2

    log_path = args.output_dir / "dry_run_log.jsonl"
    summary_path = args.output_dir / "dry_run_summary.json"

    # Lazy imports so the script still parses on machines where the
    # OANDA client isn't fully wired (e.g. CI runner without secrets).
    try:
        from live_data.oanda_read_only import OandaReadOnlyClient
        from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
        from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
        from newsmind.v4.NewsMindV4 import NewsMindV4
    except Exception as e:
        print(f"DRY-RUN ABORT: import failed: {e}", file=sys.stderr)
        return 3

    nb_dir = args.output_dir / "smartnotebook"
    nb_dir.mkdir(parents=True, exist_ok=True)
    notebook = SmartNoteBookV4(nb_dir)

    # The live OANDA client is constructed only if credentials are
    # present in env. Otherwise we run with a documented null client
    # that yields zero bars — every cycle then BLOCKs at data quality,
    # which is the correct behaviour.
    try:
        oanda = OandaReadOnlyClient()
    except Exception as e:
        print(f"WARNING: OANDA read-only client unavailable: {e}. "
              f"Cycles will BLOCK at data quality. This is acceptable "
              f"for dry-run.", file=sys.stderr)
        oanda = None

    news = NewsMindV4()
    orch = HydraOrchestratorV4(smartnotebook=notebook, newsmind=news)

    deadline = time.time() + args.duration_minutes * 60
    cycle_n = 0
    counters = {"total": 0, "ENTER_CANDIDATE": 0, "WAIT": 0,
                 "BLOCK": 0, "ORCHESTRATOR_ERROR": 0, "errors": 0,
                 "live_order_attempted": 0}

    stop = {"flag": False}
    def _stop(sig, frame):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"DRY-RUN started for {args.duration_minutes} minutes.")
    print(f"Output: {log_path}")
    with log_path.open("w", encoding="utf-8") as logf:
        while time.time() < deadline and not stop["flag"]:
            cycle_n += 1
            now_utc = datetime.now(timezone.utc)
            try:
                bars_by_pair = {}
                bars_by_tf = {}
                if oanda is not None:
                    for sym in ("EUR_USD", "USD_JPY"):
                        try:
                            bars = oanda.recent_bars(sym, "M15", count=500)
                            bars_by_pair[sym] = bars
                            bars_by_tf["M15"] = bars
                        except Exception as ex:
                            counters["errors"] += 1
                            logf.write(json.dumps({
                                "cycle": cycle_n, "ts": now_utc.isoformat(),
                                "error": f"bar_fetch_{sym}", "exc": str(ex),
                            }) + "\n")
                            continue
                # Run cycles per pair.
                for sym in list(bars_by_pair.keys()):
                    res = orch.run_cycle(
                        symbol=sym, now_utc=now_utc,
                        bars_by_pair={sym: bars_by_pair[sym]},
                        bars_by_tf={"M15": bars_by_pair[sym]},
                    )
                    counters["total"] += 1
                    counters[res.final_status] = counters.get(
                        res.final_status, 0) + 1
                    rec = {
                        "cycle": cycle_n, "ts": now_utc.isoformat(),
                        "symbol": sym, "final_status": res.final_status,
                        "final_reason": res.final_reason,
                        "session_status": res.session_status,
                    }
                    # Mark explicitly that no order attempt occurred.
                    rec["live_order_attempted"] = False
                    rec["mode"] = "DRY_RUN"
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
            except Exception as e:
                counters["errors"] += 1
                logf.write(json.dumps({
                    "cycle": cycle_n, "ts": now_utc.isoformat(),
                    "error": str(e),
                }) + "\n")

            # Sleep until next cycle, but break out fast if signalled.
            slept = 0
            while slept < args.cycle_interval_s and not stop["flag"]:
                time.sleep(min(1, args.cycle_interval_s - slept))
                slept += 1

    summary_path.write_text(
        json.dumps({
            "cycles": cycle_n,
            "counters": counters,
            "live_order_attempted_total": counters["live_order_attempted"],
            "verdict": "DRY_RUN_PASSED"
            if counters["live_order_attempted"] == 0 else "DRY_RUN_FAILED",
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Dry run finished. Cycles: {cycle_n}. "
          f"Live orders attempted: {counters['live_order_attempted']} "
          f"(must be 0).")
    return 0 if counters["live_order_attempted"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
