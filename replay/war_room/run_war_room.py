"""HYDRA 4.7 War Room — orchestrator.

Runs the full investigation pipeline:

  Step 1 diagnostics              -> diagnostics.{json,md}
  Step 2 bottleneck attribution   -> bottleneck_attribution.{json,md}
  Step 3 shadow P&L               -> shadow_pnl.{json,md}, shadow_trades.jsonl
  Step 4 hypothesis register      -> hypotheses.{json,md}
  Step 5 Red Team probes          -> red_team.{json,md}
  Step 6 final report             -> HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md

Inputs:
  --cycles      cycles.jsonl from a finished or in-progress run_v47_backtest.
  --data-cache  HYDRA V4/data_cache (for shadow P&L and Red Team spread check).
  --out-dir     Directory for all artefacts.
  --repo-root   HYDRA V4 (for Red Team static checks).

The orchestrator is idempotent: re-run after a fuller backtest to refresh
all artefacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import diagnostics
from . import bottleneck_attribution
from . import shadow_pnl
from . import hypotheses
from . import red_team
from . import report_writer
from . import chartmind_score_dump


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=Path, required=True)
    p.add_argument("--data-cache", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--repo-root", type=Path, required=True)
    args = p.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("[1/6] diagnostics...")
    diag = diagnostics.run(args.cycles, args.out_dir)
    print(f"     total records: {diag['total_records']:,}")

    print("[2/6] bottleneck attribution...")
    bot = bottleneck_attribution.run(args.cycles, args.out_dir)
    print(f"     attributed: {len(bot['attribution'])} categories")

    print("[3/6] shadow P&L (this can take a while)...")
    sp = shadow_pnl.run(args.cycles, args.data_cache, args.out_dir)
    for mode, info in sp.get("summary_by_mode", {}).items():
        print(f"     {mode}: {info['trades']:,} trades, "
              f"net_pips={info['net_pips_after_cost']}")

    print("[4/6] hypothesis register...")
    hs = hypotheses.run(args.out_dir)
    print(f"     hypotheses: {len(hs)}")

    print("[5/6] Red Team probes...")
    probes = red_team.run(args.repo_root, args.data_cache, args.cycles,
                            args.out_dir, args.out_dir)
    n_pass = sum(1 for x in probes if x.get("passed"))
    print(f"     probes passed: {n_pass}/{len(probes)}")

    print("[5b/6] V5.1 ChartMind score dump...")
    cm_summary = chartmind_score_dump.run(args.cycles, args.out_dir)
    print(f"     chartmind rows parsed: {cm_summary.get('rows_parsed', 0):,}")

    print("[6/6] writing final report...")
    report_path = args.repo_root / (
        "HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_"
        "PERFORMANCE_RESCUE_REPORT.md"
    )
    report_writer.write(report_path, args.out_dir, diag, bot, sp, hs, probes)
    print(f"     report written: {report_path}")


if __name__ == "__main__":
    main()
