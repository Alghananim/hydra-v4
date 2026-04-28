"""HYDRA V4 — run_live_replay.py

The script the USER runs on their laptop with real OANDA + Anthropic
keys configured in the environment. It:

  1. Loads secrets from env (no prompts in code, no inline keys).
  2. Builds an OandaReadOnlyClient (no live trading possible).
  3. Downloads (or resumes) 2 years of M15 bars for EUR_USD + USD_JPY.
  4. Validates data quality. Aborts if not acceptable.
  5. Loads the merged JSONL into memory.
  6. Constructs the AnthropicBridge.
  7. Builds the user's OrchestratorV4 (must already exist in the
     project — the replay engine treats it as a duck-typed object
     with `run_cycle(symbol, now_utc, bars_by_pair, bars_by_tf)`).
  8. Runs TwoYearReplay end-to-end.
  9. Walks SmartNoteBook to compute SHADOW_OUTCOME records (replay
     uses a 24-bar look-forward from each REJECTED_TRADE, but only
     using bars that were KNOWN at replay-end — i.e., past data).
 10. Extracts CANDIDATE LESSONs with allowed_from_timestamp = end.
 11. Writes the report bundle to replay_results/.

Hard-coded sandbox safety: this file does not run in our build agent
sandbox — it imports modules that need network. The user runs it.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic_bridge.bridge import AnthropicBridge
from anthropic_bridge.secret_loader import (
    SecretNotConfiguredError,
    load_anthropic_key,
    load_oanda_credentials,
)
from live_data.data_cache import JsonlCache
from live_data.data_loader import download_two_years
from live_data.data_quality_checker import is_acceptable
from live_data.oanda_readonly_client import OandaReadOnlyClient
from replay.lesson_extractor import extract_candidate_lessons
from replay.replay_report_generator import write_full_report
from replay.two_year_replay import TwoYearReplay


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_orchestrator_factory():
    """Import the actual frozen HydraOrchestratorV4."""
    from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
    return HydraOrchestratorV4


def main(argv: Optional[List[str]] = None) -> int:
    _setup_logging()
    log = logging.getLogger("run_live_replay")

    pairs = ["EUR_USD", "USD_JPY"]
    end_date = datetime.now(timezone.utc).replace(microsecond=0)

    # 1) secrets
    try:
        anthropic_key = load_anthropic_key()
        oanda_token, oanda_account = load_oanda_credentials()
    except SecretNotConfiguredError as e:
        log.error("missing secrets: %s", e)
        return 2
    import os
    oanda_env = os.environ.get("OANDA_ENV", "practice")

    # 2) read-only client
    client = OandaReadOnlyClient(
        token=oanda_token,
        account_id=oanda_account,
        env=oanda_env,
    )

    # 3-4) download + DQ
    cache = JsonlCache(Path("data_cache"))
    bars_by_pair: Dict[str, List[Dict[str, Any]]] = {}
    for p in pairs:
        log.info("downloading 2y M15 for %s", p)
        out = download_two_years(client, p, end_date, cache, granularity="M15")
        log.info(
            "pair=%s pages_written=%d pages_skipped=%d total_bars=%d",
            p, out["pages_written"], out["pages_skipped"],
            out["quality_report"]["total_bars"],
        )
        if not out["quality_ok"]:
            log.error("DQ failed for %s: %s", p, out["quality_reasons"])
            return 3
        # Read deduped+sorted candles from merged.jsonl (avoids page-boundary dups).
        merged_path = out["merged_path"]
        bars_list: List[Dict[str, Any]] = []
        with open(merged_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                bars_list.append(json.loads(line))
        bars_by_pair[p] = bars_list

    # 5-6) bridge (built but NOT injected into frozen orchestrator;
    # the frozen Orchestrator V4 does not call Anthropic in v4.0 — the
    # bridge will be wired in a future phase. We still build it so its
    # secret-handling is exercised on this run.)
    bridge = AnthropicBridge(api_key=anthropic_key)
    log.info("anthropic bridge built (downgrade-only, not yet wired into orchestrator)")

    # 7) orchestrator + smartnotebook + REAL historical news scheduler
    OrchestratorCls = _load_orchestrator_factory()
    from smartnotebook.v4.SmartNoteBookV4 import SmartNoteBookV4
    from newsmind.v4.event_scheduler import EventScheduler
    from replay.replay_calendar import build_replay_occurrences
    from replay.replay_newsmind import ReplayNewsMindV4

    notebook_dir = Path("data_cache") / "smartnotebook"
    notebook = SmartNoteBookV4(notebook_dir)

    # Pre-compute replay window for the calendar (matches step 8 below).
    import os as _os
    _replay_days = int(_os.environ.get("REPLAY_DAYS", "90"))
    from datetime import timedelta as _td
    replay_start = end_date - _td(days=_replay_days)
    # Pad +/- 7 days so blackout windows around boundary events are caught.
    occ = build_replay_occurrences(
        start_utc=replay_start - _td(days=7),
        end_utc=end_date + _td(days=7),
    )
    log.info("replay calendar: %d historical event occurrences in window", len(occ))

    # Build EventScheduler with curated 10-event YAML + historical occurrences.
    # ReplayNewsMindV4 wraps it: BLOCK in blackout, A grade when clean.
    scheduler = EventScheduler()
    scheduler.load_occurrences(occ)
    news = ReplayNewsMindV4(scheduler=scheduler)
    orchestrator = OrchestratorCls(smartnotebook=notebook, newsmind=news)
    log.info(
        "orchestrator built (HydraOrchestratorV4) with ReplayNewsMindV4 "
        "(no HTTP, %d scheduled events)", len(occ)
    )

    # Convert dict candles to Bar dataclass instances for the orchestrator
    from marketmind.v4.models import Bar
    def _dict_to_bar(d):
        # JSONL candle: {time, mid:{c}, bid:{c}, ask:{c}, volume, ...}
        ts = d.get("time") or d.get("timestamp_utc")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        mid = d.get("mid", {})
        o = float(d.get("open", mid.get("o", mid.get("c", 0.0))))
        h = float(d.get("high", mid.get("h", mid.get("c", 0.0))))
        l = float(d.get("low",  mid.get("l", mid.get("c", 0.0))))
        c = float(d.get("close", mid.get("c", 0.0)))
        v = float(d.get("volume", 0))
        spread = d.get("spread_pips")
        if spread is None and "ask" in d and "bid" in d:
            try:
                spread = (float(d["ask"]["c"]) - float(d["bid"]["c"])) * 10000
            except Exception:
                spread = None
        return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, spread_pips=spread if spread is not None else 0.0)

    bars_typed = {p: [_dict_to_bar(d) for d in bars_by_pair[p]] for p in pairs}
    log.info("converted %d EUR_USD + %d USD_JPY dict candles to Bar instances",
             len(bars_typed.get("EUR_USD", [])), len(bars_typed.get("USD_JPY", [])))

    # 8) replay — window already computed in step 7 (replay_start)
    start = replay_start
    log.info("replay window: last %d days (%s -> %s)",
             _replay_days, start.isoformat(), end_date.isoformat())
    replay = TwoYearReplay(
        orchestrator=orchestrator,
        smartnotebook=notebook,
        bars_by_pair=bars_typed,
        anthropic_bridge=bridge,
    )
    result = replay.run(start=start, end=end_date, pairs=pairs)

    # 9-10) ledger walk + lessons
    storage = notebook.storage
    decision_cycles = list(storage.iter_records(record_type="DECISION_CYCLE"))
    rejected_trades = list(storage.iter_records(record_type="REJECTED_TRADE"))
    shadow_outcomes = list(storage.iter_records(record_type="SHADOW_OUTCOME"))
    lessons_proposed = extract_candidate_lessons(
        rejected_records=rejected_trades,
        shadow_records=shadow_outcomes,
        end_of_replay=end_date,
    )
    result.lessons_extracted = len(lessons_proposed)
    result.shadow_outcomes_generated = len(shadow_outcomes)

    # 11) report
    out_dir = Path("replay_results")
    paths = write_full_report(
        out_dir=out_dir,
        result=result,
        decision_cycles=decision_cycles,
        rejected_trades=rejected_trades,
        shadow_outcomes=shadow_outcomes,
        lessons=lessons_proposed,
        pairs=pairs,
        notes=[
            f"OANDA env: {oanda_env}",
            f"granularity: M15",
            f"bars EUR_USD: {len(bars_by_pair['EUR_USD'])}",
            f"bars USD_JPY: {len(bars_by_pair['USD_JPY'])}",
        ],
    )
    log.info("wrote %d artefacts: %s", len(paths), list(paths.keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
