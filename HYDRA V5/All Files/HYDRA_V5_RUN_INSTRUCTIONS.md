# HYDRA V5 — Run Instructions

## Daily operations

### Backtest mode (no live)

1. Double-click `HYDRA V5\Run_HYDRA_V5.bat`.
2. Choose `[1]` Backtest. Resumable; safe to interrupt.
3. When `replay_runs\v47_2y\DONE` appears, choose `[2]` War Room.
4. Read `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md` at the repo root.

### Cloud mode (no laptop needed)

1. Push any change to `main` on GitHub. The workflow `HYDRA V4.7 — Backtest + War Room` runs automatically.
2. Or click "Run workflow" on the Actions tab to trigger manually.
3. The workflow commits results back to the repo. Refresh the report file to see the new numbers.

### Dry-run live (read live data, no orders)

1. Double-click launcher → `[3]` Dry-run. Runs for 60 minutes, polls every 5 minutes.
2. Output: `replay_runs\dry_run\dry_run_log.jsonl` and `dry_run_summary.json`.
3. The summary's `live_order_attempted_total` MUST be `0`. If it's not, abort everything and investigate.

### Controlled-live micro

1. Verify the V4.8 final report and the V4.9 plan say "promotable" / "ready". Otherwise: do not arm.
2. Verify your OANDA practice account is selected (never live).
3. In a fresh terminal: `set HYDRA_LIVE_ARMED=1`.
4. Create today's approval token:
   `echo approved > "C:\Users\Mansur\Desktop\HYDRA V4\replay_runs\controlled_live\approval_YYYYMMDD.token"`
   (use today's UTC date, e.g. `approval_20260428.token`).
5. Double-click launcher → `[4]` Controlled-live. The 16-guard runs per cycle.
6. To stop instantly: `echo stop > "C:\Users\Mansur\Desktop\HYDRA V4\replay_runs\controlled_live\KILL"`.

## Pre-flight checklist (before any controlled-live run)

- [ ] Latest backtest finished within the last 24 hours.
- [ ] War Room report's verdict is "PROMOTABLE" for the variant currently in use.
- [ ] OANDA account is the **practice** account (live account is out of scope for V4.9).
- [ ] No alerts in the GitHub Actions log.
- [ ] Today's approval token is freshly created (UTC date matches).
- [ ] `HYDRA_LIVE_ARMED=1` is set only in this shell, not globally.
- [ ] Spread on EUR/USD and USD/JPY is below 2.5 pips at the moment of arming.
- [ ] You are awake and watching the launcher window for the first 30 minutes.

## What success looks like

A successful day in controlled-live mode is:
- 0 to 4 micro-trades placed.
- Every placed trade has the exact `audit_id` recorded in SmartNoteBook AND in OANDA's transaction log.
- Daily realised P/L within ±1 % of equity.
- Every guard failure logged to `controlled_live_log.jsonl` with the failing condition.
- No surprise.

## What failure looks like, and what to do

| Symptom | Action |
|---|---|
| Launcher refuses to start with "secret literal in tracked source" | Search the repo for the literal, move it to `secrets/`, re-test. |
| Pre-flight: backtest is stale | Re-run the backtest before considering arming. |
| Cycle log shows `ARMED_BUT_GUARD_BLOCKED` repeatedly | Each block is correct behaviour. Read `guard_failing` to see which guard is unhappy. Fix the underlying issue (spread? data freshness? grade slipped to B?). |
| OANDA returns an order error | The launcher logs `ORDER_PLACEMENT_ERROR` and continues to dry-run for the rest of the session. Investigate before re-arming. |
| Daily P/L hits −1 % | Guard G15 fires, no further orders that day. Log will show the cap. Rest the rest of the day. |

## Escalation

Anything that smells wrong is a stop, not a "try again". The launcher is designed to be conservative, not heroic. Investigate, fix, document, then re-test in dry-run before re-arming.
