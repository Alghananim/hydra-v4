# HYDRA V4.8 — Post-Rescue & Dry-Run Report

V4.8 is the verification phase between V4.7 (architectural fix) and V4.9 (controlled live). It has two halves:

- **A. Post-rescue verification** — confirm V4.7's fix produced honest improvements, not artefacts.
- **B. Live-armed dry run** — prove the system can read live data, run all 5 brains, and **never** reach an order placement code path.

This document is filled with concrete findings once the cloud workflow run produces the data. Below is the structure and the criteria.

---

## A. Post-rescue verification

### A.1 Before / after metrics

| Metric | V4.6 (pre-fix) | V4.7 (full run) | Verdict |
|---|---:|---:|---|
| Total cycles | 99,298 | (filled at runtime) | — |
| ENTER_CANDIDATE | 0 | (runtime) | improvement = ? |
| WAIT | (runtime) | (runtime) | — |
| BLOCK | (runtime) | (runtime) | — |
| Trades / day | 0.0 | (runtime) | target ≥ 2 |
| Days with 2+ trades | 0 | (runtime) | — |
| Net pips after cost | n/a | (runtime) | target > 0 |
| Win rate (excl. timeout) | n/a | (runtime) | ≥ 45 % to consider promotion |
| Max drawdown (pips) | n/a | (runtime) | ratio < 0.6 |

### A.2 Per-mind contribution

The bottleneck attribution table from `replay_runs/v47_warroom/bottleneck_attribution.md` is reproduced here. The dominant labels indicate which brain to focus calibration on:

- `session_outside_window` — design choice, not a bottleneck.
- `grade_below_A:MarketMind` — if dominant, MarketMind grade is the lever.
- `grade_below_A:ChartMind` — if dominant, ChartMind sensitivity is the lever.
- `consensus:incomplete_agreement` — chart=WAIT but news/market directional; expected and benign under V4.7.
- `consensus:directional_conflict` — News or Market explicitly opposed Chart; rare and informative.

### A.3 Hypotheses verified or rejected

The 15 hypotheses from `replay_runs/v47_warroom/hypotheses.md` are graded "supported", "rejected", or "inconclusive" based on the cloud run's diagnostics + bottleneck attribution + shadow P&L. The decision tree for V4.8 sweeps follows directly from which hypotheses survived.

### A.4 Rejected-trade shadow P&L

Three shadow modes from `replay_runs/v47_warroom/shadow_pnl.md`:

- `shadow_chart` — every directional ChartMind decision, ignoring grade and consensus.
- `shadow_grade_B` — directional ChartMind with grade ≥ B and no opposing News/Market.
- `shadow_2_of_3` — V4.7 baseline (informational sanity check).

The promotion criteria in `replay/calibration/compare.py::promotion_verdict`:

- Red Team passed: 8/8.
- ENTER count > V4.7 baseline.
- Win rate (excl. timeout) ≥ 45 %.
- Net pips > V4.7 baseline.
- Drawdown / net pips ratio < 0.6.

A variant satisfying all five is "PROMOTABLE". Anything weaker is reported but flagged "DO_NOT_PROMOTE".

### A.5 Decision

If at least one safe-range variant is promotable → **proceed to V4.9 dry run** with that variant. If none is promotable → V4.8 closes with the recommendation "redesign timeframe / instrument set" rather than further threshold tweaks. The V4.8 final commit will state plainly which path is taken.

---

## B. Live-armed dry run

### B.1 Setup

- Launcher: `live/dry_run.py` invoked via `Run_HYDRA_V5.bat → [3]`.
- Duration: 60 minutes.
- Cycle interval: 5 minutes (12 cycles total per pair).
- OANDA: read-only client only. No write client present in this release.
- Pairs: EUR/USD, USD/JPY.

### B.2 Pass criteria

| Criterion | Pass condition |
|---|---|
| Live data read | Each cycle either returns ≥ 1 bar OR logs an OANDA-side error (with mode `DRY_RUN`). |
| All 5 brains run | Each cycle's record contains `news`, `market`, `chart` outputs unless an upstream BLOCK fired. |
| GateMind decision present | Each cycle has `final_status` ∈ {ENTER_CANDIDATE, WAIT, BLOCK, ORCHESTRATOR_ERROR}. |
| SmartNoteBook recorded | Each cycle has a corresponding ledger entry under `replay_runs/dry_run/smartnotebook/`. |
| **Live orders attempted = 0** | `dry_run_summary.json::live_order_attempted_total == 0`. |

### B.3 Verdict

The dry run passes only if all five criteria above are satisfied. Any single failure aborts the V4.9 step.

### B.4 What this proves

- Architecture works on live data, not just cached data.
- LIVE_ORDER_GUARD blocks every order even when the system is running on a real OANDA connection.
- SmartNoteBook ledger is written and consistent with the cycle log.

### B.5 What this does not prove

- That V4.7's calibration is profitable on live conditions. That requires V4.9 with real fills.
- That the OANDA write client (when added) will respect every guard. That requires its own audit when written.

---

## C. Combined V4.8 verdict

V4.8 closes with one of:

- **APPROVED for V4.9** — at least one promotable variant exists AND dry run passes all 5 criteria.
- **APPROVED for redesign** — no promotable variant; V4.9 explicitly skipped; next phase is timeframe / instrument redesign.
- **NOT APPROVED** — dry run failed; investigate before any further phase.

The verdict is committed as a single line at the end of this report once the data lands.
