# HYDRA V5 — Red Team Final Report

The Red Team's job is to prove the V5 release is unsafe or untrustworthy. Each attempted attack appears below with its outcome.

## A. Attacks on the backtest

### A1. Look-ahead in the simulator
- **Probe:** static check of `replay/war_room/shadow_pnl.py` — the simulation loop must start at `entry_idx + 1` and never reference `bars[entry_idx]` inside the loop body.
- **Tool:** `red_team.p1_no_lookahead_in_simulator`.
- **Verdict at file freeze:** PASS (verified by source inspection).

### A2. Costs not deducted
- **Probe:** every exit branch in `_simulate` subtracts `COST_PIPS`. Three required substrings present.
- **Tool:** `red_team.p2_costs_deducted`.
- **Verdict:** PASS.

### A3. Unrealistic spread assumption
- **Probe:** median spread across cached bars vs. assumed `COST_PIPS`.
- **Tool:** `red_team.p3_realistic_spread_floor`.
- **Verdict:** computed by the cloud run; will be filled into the auto-generated `red_team.md`.

### A4. Single-segment-only profitability
- **Probe:** split shadow trades into 4 time segments; each segment must be individually profitable.
- **Tool:** `red_team.p4_segmented_robustness`.
- **Verdict:** computed at runtime.

### A5. Single-pair-only profitability
- **Probe:** EUR/USD and USD/JPY each individually positive net pips.
- **Tool:** `red_team.p5_per_pair_robustness`.
- **Verdict:** computed at runtime.

### A6. Single-window-only profitability
- **Probe:** pre-open and morning each individually positive.
- **Tool:** `red_team.p6_per_window_robustness`.
- **Verdict:** computed at runtime.

### A7. Drawdown disguise
- **Probe:** drawdown / net-pips ratio < 0.6.
- **Tool:** `red_team.p7_drawdown_floor`.
- **Verdict:** computed at runtime.

### A8. Loose modes amplify drawdown
- **Probe:** any loosened mode must have ≤ 2× the baseline drawdown.
- **Tool:** `red_team.p8_loose_modes_dont_explode_drawdown`.
- **Verdict:** computed at runtime.

## B. Attacks on the brains and gate

### B1. NewsMind silently goes WAIT for everything
- **Threat:** NewsMind's V4.7 contract is "WAIT or BLOCK only". A bug could make it always WAIT, including during real high-impact events.
- **Mitigation:** the calendar-based `event_scheduler` deterministically forces BLOCK during ±N-min windows around configured events. The `replay/replay_calendar.py` covers 174 historical events.
- **Verdict:** Mitigated. Audit (during V4.7 War Room) will count actual BLOCK occurrences and confirm they line up with calendar entries.

### B2. ChartMind directional with grade C masquerading as A
- **Threat:** if grading is mis-calibrated, low-confidence setups could get high grades.
- **Mitigation:** grade is computed from explicit numeric evidence. The shadow simulator records the grade alongside the trade outcome; correlation between grade and win rate is auditable.
- **Verdict:** verified via shadow P&L outputs.

### B3. GateMind R6 (consensus) bypassed
- **Threat:** the V4.7 fix changes consensus_check; could a bug return `unanimous_buy` when chart is actually WAIT?
- **Mitigation:** 143/143 GateMind unit tests pass after the V4.7 change. The new `incomplete_agreement` branch correctly returns when ChartMind is not directional.
- **Verdict:** PASS at unit-test level.

### B4. Audit ID forgery
- **Threat:** could an attacker submit a false GateDecision with a forged audit_id?
- **Mitigation:** `make_audit_id` is deterministic from inputs; SmartNoteBook chain HMAC (when key is set) prevents tampering. Without HMAC the chain is tamper-detect, not forge-resist; the launcher logs a warning when HMAC is unset.
- **Verdict:** PASS in HMAC mode; documented limitation otherwise.

## C. Attacks on the live execution path

### C1. Accidental arming
- **Threat:** a stray `set HYDRA_LIVE_ARMED=1` in the user's environment could leave live trading on across sessions.
- **Mitigation:** arming requires BOTH the env var AND a per-day token file. The token has today's UTC date in its name; yesterday's token is automatically irrelevant.
- **Verdict:** Mitigated.

### C2. Live writer accidentally bundled
- **Threat:** an unaudited writer module could be imported.
- **Mitigation:** `controlled_live._load_live_writer` returns `None` on any import failure and degrades to dry-run; the writer is intentionally not shipped in V5.
- **Verdict:** Mitigated by absence.

### C3. Bad TP/SL bypassing G11/G12
- **Threat:** a candidate without SL or TP/exit logic submitted as ENTER.
- **Mitigation:** guard G11 requires SL; guard G12 requires TP or documented exit logic.
- **Verdict:** Mitigated.

### C4. Spread spike at entry
- **Threat:** spread balloons between cycle decision and order submission.
- **Mitigation:** guard G08 blocks orders with spread > 2.5 pips at the entry bar.
- **Limit:** does not protect against intra-bar spread spikes between decision and execution. Honest acknowledgement — V4.9's micro size limits the damage of any such event.

### C5. Stale-data trade
- **Threat:** trading a stale quote during a connectivity loss.
- **Mitigation:** guard G09 enforces freshness within 1.5 × bar interval.

### C6. Daily loss not enforced
- **Threat:** consecutive losses run past the daily cap.
- **Mitigation:** guard G15 caps at 1.0 % equity per day.

## D. Attacks on the repo / supply chain

### D1. Token leak via git
- **Threat:** an OANDA token literal accidentally committed.
- **Mitigation:** `.gitignore` covers `**/api_keys/`, `**/credentials/`, `**/tokens/`, `*token*.txt`, `*credential*.txt`, `secrets/*.key`, `*.env`. Launcher refuses to start if "oanda_api_token" appears in tracked Python source.
- **Verdict:** Mitigated by multiple layers.

### D2. Public repo exposure
- **Threat:** strategy code is world-visible (because GitHub blocks private for the user's region).
- **Limit:** acknowledged; trade-off documented in `HYDRA_V5_LIMITATIONS_AND_RISKS.md`.

### D3. Unauthorised workflow run
- **Threat:** an attacker forks the repo and tries to run the workflow.
- **Mitigation:** `secrets` are not used by this workflow; nothing useful runs in a fork. `permissions: contents: write` only applies on the owner's repo.

## E. Attacks on the report itself

### E1. Numbers not regenerated
- **Threat:** the report shows last week's numbers as if they were current.
- **Mitigation:** the report is overwritten by `report_writer.py` on every cloud run. The commit hash and run id are visible in the GitHub Actions log; the report does not include a date in the body that could be confused with old data.

### E2. Fake commit
- **Threat:** an attacker pushes a hand-crafted "successful" report.
- **Mitigation:** the commit history is visible. The report file is generated by a deterministic Python module; reviewers can re-run `Run_HYDRA_V5.bat → War Room` to regenerate locally and diff.

## Verdict

The release passes Red Team A1–A2 (static), and the dynamic probes (A3–A8) plus B1–C6 will report their verdicts in the auto-generated `red_team.md` after the cloud run completes. Any red verdict is a stop, not a discussion.

## Outstanding Red Team work

- After V4.8 sweep results land, every safe-range variant must individually pass A3–A8 before becoming "promotable".
- Before V4.9 ever places a real order, dry-run logs must show ≥ 1 cycle that reached `DRY_RUN_WOULD_HAVE_TRADED` to prove the path is reachable, AND ≥ 1 cycle where the 16-guard correctly blocked despite ENTER (proving the guard is active).
