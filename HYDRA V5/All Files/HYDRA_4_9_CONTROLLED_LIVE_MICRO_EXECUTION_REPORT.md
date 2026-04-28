# HYDRA V4.9 — Controlled Live Micro-Execution Report

V4.9 is the FIRST phase that allows real orders to reach a real broker. Every defence in the system is on at maximum strictness. The phase is conditional and may legitimately end with **zero trades placed** — that is a successful outcome, not a failure, if the conditions for placing a trade did not arise.

---

## 1. Conditions for V4.9 to even begin

All of the following must be true at start time. If any one fails, V4.9 is documented as "skipped" and the system stays in dry-run.

- V4.7 cloud workflow finished with `replay_runs/v47_2y/DONE`.
- War Room final report has real numbers (no placeholders).
- V4.8 final verdict says "APPROVED for V4.9".
- Live OANDA writer client (`live_data/oanda_live_client.py`) exists, has been audited, and the audit signature is present.
- The OANDA account selected is the **practice** account, not live.
- The user has set `HYDRA_LIVE_ARMED=1` in the launcher's shell.
- A token file `replay_runs/controlled_live/approval_YYYYMMDD.token` exists with non-empty content (today's UTC date).

If all of the above is true, V4.9 may run for at most 60 minutes per session, and the user must remain at the launcher window for the first 30 minutes.

## 2. Per-cycle gate

The 16-condition `live/safety_guards.py::evaluate_all` runs on every ENTER candidate. All 16 must return True; any False aborts that order.

| Guard | What it checks |
|---|---|
| G01 | News+Market non-opposing AND ChartMind directional |
| G02 | GateMind has emitted ENTER_CANDIDATE |
| G03 | All three grades A or A+ |
| G04 | No B grades (redundant with G03; defence in depth) |
| G05 | No should_block on any brain |
| G06 | No data-quality issue on any brain |
| G07 | Now is inside one of the two NY trading windows |
| G08 | Spread ≤ 2.5 pips |
| G09 | Last bar age ≤ 1.5 × bar interval |
| G10 | Per-trade risk ≤ 0.25 % of equity (V4.9 default 0.10 %) |
| G11 | Stop loss is set and positive |
| G12 | Take profit is set OR a documented exit_logic is present |
| G13 | SmartNoteBook is ready to record |
| G14 | Kill switch file is absent |
| G15 | Today's realised P/L > −1.0 % |
| G16 | Today's trade count < 4 |

## 3. What gets logged

Every cycle, regardless of whether an order is placed, writes a record to `replay_runs/controlled_live/controlled_live_log.jsonl`. The record's `mode` field is one of:

- `DRY_RUN` — system not armed, or arming conditions not met. No order considered.
- `ARMED_BUT_NO_ENTRY` — armed, but cycle did not produce ENTER_CANDIDATE.
- `ARMED_BUT_GUARD_BLOCKED` — armed, ENTER produced, but at least one guard failed. `guard_failing` lists which.
- `ARMED_BUT_WRITER_MISSING` — armed and guards cleared, but no live writer client present. Order not placed.
- `DRY_RUN_WOULD_HAVE_TRADED` — armed flag was off but everything else cleared. Useful for path-coverage proof.
- `ORDER_PLACED` — armed, all guards cleared, writer present, order submitted to OANDA. `order_result` contains the broker's response.
- `ORDER_PLACEMENT_ERROR` — order submission raised. `error` records the reason.

## 4. Termination

- Session duration cap: 60 minutes per launcher invocation.
- Daily orders cap: 4 (guard G16).
- Daily loss cap: 1.0 % of equity (guard G15).
- Kill switch: touch `replay_runs/controlled_live/KILL` from any shell.

## 5. What V4.9 success looks like

- 0 to 4 micro-orders placed during the session.
- Every placed order has a matching SmartNoteBook entry with the same `audit_id` AND a matching OANDA transaction id.
- Daily P/L stays inside ±1 %.
- Every guard failure is logged with the failing condition name.
- No `ORDER_PLACEMENT_ERROR`. No `ARMED_BUT_WRITER_MISSING` (if armed and writer is supposed to be there).

## 6. What V4.9 failure looks like

- Any `ORDER_PLACEMENT_ERROR` → stop, investigate, do not re-arm same day.
- Any guard fired N times in one session for non-obvious reasons → stop, investigate.
- Any cycle with `final_status == "ORCHESTRATOR_ERROR"` → stop.
- Any mismatch between SmartNoteBook entry and OANDA transaction id → stop, investigate.

## 7. Current status of V4.9 (at file freeze)

- **Code path:** complete and unit-clean (`live/controlled_live.py`, `live/safety_guards.py`).
- **Live writer client:** **not shipped**. V4.9 cannot place real orders in this release.
- **Verdict:** V4.9 is **architecturally ready** but **operationally not yet enabled** because the audited writer client is the next deliverable, not part of V5.

This is intentional. Shipping V5 with a writer client would be premature: each writer needs its own audit, and there is no point auditing a writer until V4.8 confirms a promotable variant exists. The order of operations is:

1. V4.7 cloud run finishes → real numbers.
2. V4.8 sweeps → promotable variant found (or honest "no, redesign needed").
3. If promotable: write OANDA writer client, audit it, sign it, ship it.
4. Then and only then: arm V4.9 and place a first practice-account micro-order.

## 8. Final V4.9 verdict

The verdict line below is updated when V4.9 actually runs:

```
V4.9 status: SKIPPED — writer client not yet shipped; V5 architecture ready; awaiting V4.8 outcome.
```

If a future iteration runs V4.9 successfully, replace the line with:

```
V4.9 status: COMPLETE — N orders placed, M passed, audit reconciled, daily P/L X.YZ%.
```
