"""HYDRA V4.7 — resumable 2-year backtest runner.

Runs the frozen orchestrator (with the V4.7 consensus fix in place) over
real cached M15 data for EUR/USD and USD/JPY, in chunks of N seconds, with
a JSON state file so the process can be killed and resumed without losing
work.

Output (under --output-dir):
  state.json             - resume cursor + counters
  cycles.jsonl           - one record per cycle (BLOCK / WAIT / ENTER)
  enter_candidates.jsonl - subset where final_status == ENTER_CANDIDATE
  summary.json           - written when the timeline completes
  smartnotebook/         - SmartNoteBook ledger (HMAC chain + JSONL + SQLite)
  DONE                   - marker file when timeline is exhausted

Usage:
  python replay/run_v47_backtest.py --output-dir replay_runs/v47_2y \\
         --time-budget-s 55 --checkpoint-every 1000

Re-run the same command to resume from the last checkpoint.
"""
from __future__ import annotations
import argparse, json, sys, time, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from marketmind.v4.models import Bar
from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
from newsmind.v4.event_scheduler import EventScheduler
from replay.replay_calendar import build_replay_occurrences
from replay.replay_newsmind import ReplayNewsMindV4
from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4


def parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "." in s:
        head, tail = s.split(".", 1)
        idx = max(tail.find("+"), tail.find("-"))
        frac, tz = (tail[:idx], tail[idx:]) if idx >= 0 else (tail, "")
        s = f"{head}.{frac[:6]}{tz}"
    return datetime.fromisoformat(s).astimezone(timezone.utc)


# V12-F1: per-pair pip size. The hardcoded *10000 broke USD/JPY:
# JPY pairs quote to 2 decimals (pip = 0.01), so spread_pips was
# inflated by 100x — every JPY bar tripped MarketMind's liquidity
# spread_anomaly check. Net: USD/JPY systematically blocked.
_PIP_SIZE = {
    "EUR_USD": 0.0001, "GBP_USD": 0.0001, "AUD_USD": 0.0001,
    "USD_CHF": 0.0001, "USD_CAD": 0.0001, "NZD_USD": 0.0001,
    "USD_JPY": 0.01,   "EUR_JPY": 0.01,   "GBP_JPY": 0.01,
}


def to_bar(d: dict, pair: str = "EUR_USD") -> Bar:
    dt = parse_iso(d["time"])
    mid = d["mid"]
    pip = _PIP_SIZE.get(pair, 0.0001)
    spread = 0.0
    try:
        spread = max(0.0, (float(d["ask"]["c"]) - float(d["bid"]["c"])) / pip)
    except Exception:
        pass
    return Bar(
        timestamp=dt,
        open=float(mid["o"]),
        high=float(mid["h"]),
        low=float(mid["l"]),
        close=float(mid["c"]),
        volume=float(d.get("volume", 0)),
        spread_pips=spread,
    )


def load_bars(pair: str) -> list:
    path = PROJECT_ROOT / "data_cache" / pair / "M15" / "merged.jsonl"
    bars = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                # V12-F1: pass pair to to_bar so JPY spreads are right.
                bars.append(to_bar(json.loads(line), pair))
    bars.sort(key=lambda b: b.timestamp)
    return bars


def cycle_to_record(c) -> dict:
    """V5.1: include the brain evidence strings (truncated) so the
    war room can parse internal scores. No behaviour change in the
    orchestrator — we just stop discarding data we already have.

    Evidence is capped at 1024 chars per brain to keep cycles.jsonl
    bounded in size. Parsing tolerates truncation.
    """
    EVIDENCE_CHAR_CAP = 1024

    def bo(b):
        if b is None:
            return None
        ev_list = list(b.evidence) if b.evidence else []
        ev_truncated = []
        budget = EVIDENCE_CHAR_CAP
        for s in ev_list:
            s = str(s)
            if len(s) >= budget:
                ev_truncated.append(s[:budget])
                break
            ev_truncated.append(s)
            budget -= len(s) + 1  # +1 for separator
        out = {
            "brain": b.brain_name,
            "decision": b.decision,
            "grade": b.grade.value,
            "data_quality": b.data_quality,
            "should_block": b.should_block,
            "evidence_count": len(b.evidence),
            "evidence": ev_truncated,
            "confidence": float(b.confidence),
        }
        # V12-F6: persist ChartMind's references so the pnl simulator
        # and shadow_pnl can use real ATR-based stops/targets instead
        # of the V5 fixed 10/20-pip simulator. Only ChartMind has
        # these fields; News/Market expose getattr(...) → None.
        for k in ("invalidation_level", "stop_reference",
                  "target_reference", "setup_anchor", "entry_zone",
                  "atr_value", "setup_type"):
            v = getattr(b, k, None)
            if v is not None:
                out[k] = v
        return out

    direction = None
    if c.gate_decision is not None:
        try:
            direction = c.gate_decision.direction.value
        except Exception:
            pass
    return {
        "cycle_id": c.cycle_id,
        "symbol": c.symbol,
        "timestamp_utc": c.timestamp_utc.isoformat(),
        "session_status": c.session_status,
        "final_status": c.final_status,
        "final_reason": c.final_reason,
        "direction": direction,
        "errors": list(c.errors) if c.errors else [],
        "news": bo(c.news_output),
        "market": bo(c.market_output),
        "chart": bo(c.chart_output),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=730)
    p.add_argument("--lookback-bars", type=int, default=500)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--time-budget-s", type=int, default=55)
    p.add_argument("--checkpoint-every", type=int, default=1000)
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
        run_meta = state["run_meta"]
        print(f"RESUME from {resume_idx}")
    else:
        resume_idx = 0
        counters = {"total": 0, "ENTER_CANDIDATE": 0, "WAIT": 0, "BLOCK": 0,
                    "ORCHESTRATOR_ERROR": 0, "errors": 0}
        run_meta = None

    pairs = ["EUR_USD", "USD_JPY"]
    print("loading bars...")
    bars_by_pair = {pp: load_bars(pp) for pp in pairs}
    end_utc = max(bars_by_pair[pp][-1].timestamp for pp in pairs)
    start_utc = end_utc - timedelta(days=args.days)
    print(f"window {start_utc.isoformat()} -> {end_utc.isoformat()} ({args.days}d)")

    if run_meta is None:
        run_meta = {
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

    timeline = sorted({b.timestamp for pp in pairs for b in bars_by_pair[pp]
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
    while ti < n_timeline:
        if time.time() > deadline:
            break
        now_utc = timeline[ti]
        for symbol in pairs:
            idx = bar_index[symbol].get(now_utc)
            if idx is None:
                continue
            # V2-W5 (no-lookahead): timeline[ti] is OPEN time of bar idx.
            # At now_utc, bar idx has not yet closed; including it leaks future
            # close into ChartMind. Visible window = bars STRICTLY before idx.
            lo = max(0, idx - args.lookback_bars)
            visible = bars_by_pair[symbol][lo:idx]
            if not visible:
                continue
            try:
                res = orch.run_cycle(
                    symbol=symbol,
                    now_utc=now_utc,
                    bars_by_pair={symbol: visible},
                    bars_by_tf={"M15": visible},
                )
                rec = cycle_to_record(res)
                cf.write(json.dumps(rec) + "\n")
                counters["total"] += 1
                counters[res.final_status] = counters.get(res.final_status, 0) + 1
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
            elapsed = time.time() - started
            print(
                f"  idx={ti}/{n_timeline} ({ti / n_timeline * 100:.1f}%) "
                f"total={counters['total']} ENTER={counters['ENTER_CANDIDATE']} "
                f"WAIT={counters['WAIT']} BLOCK={counters['BLOCK']} "
                f"err={counters['errors']}",
                flush=True,
            )
            last_log = time.time()

    cf.close()
    ef.close()
    state_path.write_text(json.dumps(
        {"next_idx": ti, "counters": counters, "run_meta": run_meta}, indent=2))
    elapsed = time.time() - started
    if ti >= n_timeline:
        summary = {**run_meta, "pairs": pairs, "timeline_size": n_timeline,
                   "calendar_occurrences": len(occ), "counters": counters}
        summary_path.write_text(json.dumps(summary, indent=2))
        done_marker.write_text("done")
        print(f"DONE. {counters}")
    else:
        progress_path.write_text(f"idx={ti}/{n_timeline}")
        print(
            f"CHUNK done in {elapsed:.0f}s. "
            f"idx={ti}/{n_timeline} ({ti / n_timeline * 100:.1f}%). "
            f"counters={counters}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        crash = Path(sys.argv[sys.argv.index("--output-dir") + 1]
                     if "--output-dir" in sys.argv else ".") / "CRASH"
        crash.write_text(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise
