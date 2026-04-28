# HYDRA V5

Production-grade rebuild of the HYDRA multi-brain decision system.

This folder is the canonical V5 release. It contains three things:

| Path | Contents |
|---|---|
| `All Files/` | Reports, documentation, test results, Red Team verdicts, run instructions, limitations & risks. |
| `HYDRA V5 CODE/` | The code that runs the system. Pointer-only — the actual modules live in the parent `HYDRA V4` tree (single source of truth, avoids duplication). |
| `Run_HYDRA_V5.bat` | The single launcher. Defaults to dry-run. Live trading requires explicit per-day arming. |

## What V5 is

V5 is the V4.7 architectural fix (ChartMind directional, News+Market vetoers) plus:

- War Room investigation toolkit (`replay/war_room/`).
- V4.8 calibration sweep harness (`replay/calibration/`).
- V4.9 controlled-live micro-execution gate (`live/`) with 16-condition safety guard.
- GitHub Actions cloud pipeline that runs the full backtest + War Room on every push.
- Defence-in-depth: nothing live is on by default; arming requires both `HYDRA_LIVE_ARMED=1` env var **and** a per-day approval token file.

## Quick start

Double-click `Run_HYDRA_V5.bat`. It runs sanity checks then shows a menu:

1. Backtest (2-year, resumable, no live)
2. War Room (analyse the latest backtest)
3. Dry-run live (live data, all execution blocked)
4. Controlled-live micro (requires arming + token)

## Live trading state

Live trading is **OFF** by default. To turn it on for one day:

1. In your terminal: `set HYDRA_LIVE_ARMED=1`
2. Create `HYDRA V4\replay_runs\controlled_live\approval_YYYYMMDD.token` with any non-empty content (today's UTC date).
3. Run launcher option 4.
4. The 16-condition guard still applies per cycle. Any guard failure aborts the order.

To stop trading instantly: `touch HYDRA V4\replay_runs\controlled_live\KILL` (or simply create that file).

## What's been verified vs what's pending

- ✅ V4.7 architectural fix — passed 143/143 GateMind unit tests.
- ⏳ Full 2-year backtest — runs in cloud via GitHub Actions; numbers fill `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md`.
- ⏳ V4.8 calibration sweeps — harness ready; sweeps run only if V4.7 baseline justifies (decision tree in V4.7 report §33).
- ⏳ V4.9 controlled-live — code path complete with 16-guard gate; **never** executed without explicit arming.
- 🔒 Live OANDA writer client (`live_data/oanda_live_client.py`) is intentionally not included in this release. Until a hand-written, audited writer is added, controlled-live degrades to dry-run mode.

## Reports (all in `All Files/`)

1. `HYDRA_V5_FINAL_TRANSFORMATION_AND_RELEASE_REPORT.md` — what changed, what's verified, what's pending.
2. `HYDRA_V5_RED_TEAM_FINAL_REPORT.md` — adversarial review of the entire release.
3. `HYDRA_V5_RUN_INSTRUCTIONS.md` — how to operate the launcher safely.
4. `HYDRA_V5_LIMITATIONS_AND_RISKS.md` — exactly what V5 cannot do, and why.
5. `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md` — V4.7 War Room results.
6. `HYDRA_4_8_POST_RESCUE_AND_DRY_RUN_REPORT.md` — V4.8 verification + dry-run evidence.
7. `HYDRA_4_9_CONTROLLED_LIVE_MICRO_EXECUTION_REPORT.md` — V4.9 outcome (or honest reason for not enabling).

## Non-negotiable principles (still in force)

- No trust without evidence. Every "done" claim must produce: code + test + log + artifact.
- Fail-CLOSED. When in doubt → BLOCK.
- No lookahead. No data leakage.
- LIVE_ORDER_GUARD across all 6 layers, plus the V4.9 16-condition guard on top.
- Secrets never enter git. The launcher refuses to start if any token literal appears in tracked source.
