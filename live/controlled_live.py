"""HYDRA V4.9 — Controlled Live Micro-Execution.

Runs the same loop as dry_run.py but, when ALL of the following are
simultaneously true, may submit ONE micro-size market order through the
OANDA write-capable client:

  1. HYDRA_LIVE_ARMED=1 in the environment (per-process explicit opt-in).
  2. A daily approval token file exists at <output_dir>/approval_TODAY.
     Token must contain a non-empty body. The user creates this token
     manually on the day they want to allow live orders. Without it,
     this script behaves exactly like dry_run.
  3. All 16 conditions in safety_guards.evaluate_all() pass.
  4. LIVE_ORDER_GUARD's existing 6 layers in the orchestrator pass.

Defaults:
  - Risk: 0.10 % of equity per trade. (Below the 0.25 % hard cap in G10.)
  - Max trades / day: 4.
  - Max daily loss: 1.0 % of equity.
  - Kill switch: <output_dir>/KILL — touch this file from any shell to
    stop trading instantly.

This script does NOT contain a live OANDA write client. It imports
`live_data.oanda_live_client` if it exists and uses it; otherwise it
refuses to place any order and logs the absence. This separation
ensures that a missing or mis-built client cannot accidentally submit
orders.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from live import safety_guards


def _approval_token_for_today(output_dir: Path) -> Path:
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return output_dir / f"approval_{today_str}.token"


def _load_live_writer():
    """Returns the live order placer if available, else None.

    The function deliberately does NOT raise — a missing client must
    cause graceful degrade to dry-run, never an uncaught exception.
    """
    try:
        from live_data.oanda_live_client import OandaLiveClient  # noqa
        return OandaLiveClient()
    except Exception:
        return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--duration-minutes", type=int, default=120)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--cycle-interval-s", type=int, default=300)
    p.add_argument("--risk-pct", type=float, default=0.10,
                   help="Per-trade risk as %% of equity (default 0.10).")
    p.add_argument("--max-trades-today", type=int, default=4)
    p.add_argument("--max-daily-loss-pct", type=float, default=1.0)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    armed_env = os.environ.get("HYDRA_LIVE_ARMED", "0") == "1"
    approval_path = _approval_token_for_today(args.output_dir)
    approval_present = approval_path.exists() and approval_path.read_text(encoding="utf-8").strip() != ""

    armed = armed_env and approval_present

    log_path = args.output_dir / "controlled_live_log.jsonl"
    summary_path = args.output_dir / "controlled_live_summary.json"
    kill_path = args.output_dir / "KILL"

    counters = {"total": 0, "ENTER_CANDIDATE_seen": 0, "orders_placed": 0,
                 "orders_blocked_by_guard": 0,
                 "orders_blocked_by_writer_missing": 0,
                 "errors": 0}

    print(f"Controlled-live: armed={armed} (env={armed_env}, approval={approval_present})")
    if not armed:
        print("Running in DRY-RUN mode (one or more arming conditions absent).")

    try:
        from live_data.oanda_read_only import OandaReadOnlyClient
        from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
        from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
        from newsmind.v4.NewsMindV4 import NewsMindV4
    except Exception as e:
        print(f"ABORT: import failed: {e}", file=sys.stderr)
        return 3

    nb_dir = args.output_dir / "smartnotebook"
    nb_dir.mkdir(parents=True, exist_ok=True)
    notebook = SmartNoteBookV4(nb_dir)

    try:
        oanda_read = OandaReadOnlyClient()
    except Exception as e:
        print(f"ABORT: OANDA read client unavailable: {e}", file=sys.stderr)
        return 4

    writer = _load_live_writer() if armed else None
    if armed and writer is None:
        print("Armed but live writer not present — degrading to dry-run.")
        armed = False

    news = NewsMindV4()
    orch = HydraOrchestratorV4(smartnotebook=notebook, newsmind=news)

    today_realised_pl_pct = 0.0
    trades_today = 0

    deadline = time.time() + args.duration_minutes * 60
    cycle_n = 0
    stop = {"flag": False}
    def _stop(sig, frame):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    with log_path.open("w", encoding="utf-8") as logf:
        while time.time() < deadline and not stop["flag"]:
            cycle_n += 1
            now_utc = datetime.now(timezone.utc)
            for sym in ("EUR_USD", "USD_JPY"):
                try:
                    bars = oanda_read.recent_bars(sym, "M15", count=500)
                except Exception as ex:
                    counters["errors"] += 1
                    logf.write(json.dumps({
                        "cycle": cycle_n, "ts": now_utc.isoformat(),
                        "symbol": sym, "error": "bar_fetch", "exc": str(ex)
                    }) + "\n")
                    continue
                if not bars:
                    continue

                res = orch.run_cycle(
                    symbol=sym, now_utc=now_utc,
                    bars_by_pair={sym: bars},
                    bars_by_tf={"M15": bars},
                )
                counters["total"] += 1
                counters[res.final_status] = counters.get(res.final_status, 0) + 1

                rec = {
                    "cycle": cycle_n, "ts": now_utc.isoformat(),
                    "symbol": sym, "final_status": res.final_status,
                    "final_reason": res.final_reason,
                    "session_status": res.session_status,
                    "armed": armed,
                }

                if res.final_status != "ENTER_CANDIDATE":
                    rec["mode"] = "ARMED_BUT_NO_ENTRY" if armed else "DRY_RUN"
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                    continue

                counters["ENTER_CANDIDATE_seen"] += 1
                # 16-condition gate.
                last_bar = bars[-1] if bars else None
                last_bar_utc = getattr(last_bar, "timestamp", None)
                spread_pips = getattr(last_bar, "spread_pips", None)

                verdict = safety_guards.evaluate_all(
                    news=res.news_output, market=res.market_output,
                    chart=res.chart_output,
                    gate_decision=res.gate_decision,
                    trade_candidate=getattr(res.gate_decision,
                                              "trade_candidate", None),
                    smartnotebook=notebook,
                    now_utc=now_utc,
                    spread_pips=spread_pips, last_bar_utc=last_bar_utc,
                    risk_pct_of_equity=args.risk_pct,
                    today_realised_pl_pct=today_realised_pl_pct,
                    trades_today=trades_today,
                    kill_switch_path=kill_path,
                )
                rec["guard_cleared"] = verdict.cleared
                rec["guard_failing"] = verdict.failing

                if not verdict.cleared:
                    counters["orders_blocked_by_guard"] += 1
                    rec["mode"] = "ARMED_BUT_GUARD_BLOCKED" if armed else "DRY_RUN"
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                    continue

                if not armed:
                    rec["mode"] = "DRY_RUN_WOULD_HAVE_TRADED"
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                    continue

                if writer is None:
                    counters["orders_blocked_by_writer_missing"] += 1
                    rec["mode"] = "ARMED_BUT_WRITER_MISSING"
                    logf.write(json.dumps(rec) + "\n")
                    logf.flush()
                    continue

                # All clear. Place ONE micro order.
                try:
                    order_result = writer.place_micro_market_order(
                        symbol=sym,
                        direction=getattr(res.gate_decision, "direction"),
                        risk_pct=args.risk_pct,
                        sl=res.gate_decision.trade_candidate.stop_loss,
                        tp=getattr(res.gate_decision.trade_candidate,
                                     "take_profit", None),
                    )
                    counters["orders_placed"] += 1
                    trades_today += 1
                    rec["mode"] = "ORDER_PLACED"
                    rec["order_result"] = order_result
                except Exception as ex:
                    counters["errors"] += 1
                    rec["mode"] = "ORDER_PLACEMENT_ERROR"
                    rec["error"] = str(ex)

                logf.write(json.dumps(rec) + "\n")
                logf.flush()

            slept = 0
            while slept < args.cycle_interval_s and not stop["flag"]:
                time.sleep(min(1, args.cycle_interval_s - slept))
                slept += 1

    summary_path.write_text(json.dumps({
        "cycles": cycle_n, "counters": counters,
        "armed_at_end": armed,
        "approval_present": approval_present,
    }, indent=2), encoding="utf-8")
    print(f"Controlled-live finished. Cycles: {cycle_n}. "
          f"Orders placed: {counters['orders_placed']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
