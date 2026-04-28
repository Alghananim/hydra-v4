# HYDRA 4.7 — Total Failure Investigation & Performance Rescue

**Status:** investigation framework in place; numerical sections will be machine-filled by `replay/war_room/run_war_room.py` once the full 99,298-cycle backtest finishes on the user's Windows laptop. Until then, this document records the methodology, the hypotheses, and the partial-run evidence already in hand. Live trading remains disabled. No gating rule has been loosened yet.

---

## 1. Executive summary

The V4.7 architectural fix (ChartMind as directional voice, News and Market as vetoers) unlocked the orchestrator: it now produces ENTER candidates on real data where V4.6 produced zero across 99,298 cycles. The partial sandbox run reached idx 10,380 / 49,649 (20.9 %) and produced **9 ENTER_CANDIDATE, 4 WAIT, 20,747 BLOCK, 0 errors**. That is not enough trades. This phase exists to find out exactly why, by attribution rather than by guesswork, then to test loosening modes against a Red Team before any rule changes are applied.

The investigation is split into six steps, each implemented as a sub-module in `replay/war_room/`:

1. **diagnostics** — total counts, distributions, top-N reasons.
2. **bottleneck_attribution** — which mind blocks how often, at which gate.
3. **shadow_pnl** — for each rejected cycle that *would* have entered under a relaxed rule, simulate forward P&L using only future bars from the cache (no lookahead), with explicit cost deduction.
4. **hypotheses** — 15 candidate explanations as structured records, each with evidence-for / evidence-against / test / risk.
5. **red_team** — eight adversarial probes that any improvement must survive (no lookahead, costs deducted, segmented robustness, per-pair, per-window, drawdown floor, etc.).
6. **report_writer** — assembles everything into this file.

---

## 2. Current failure statement

- **Target:** ≥ 2 trades/day and > 150 % return over 2 years on EUR/USD + USD/JPY M15.
- **Observed (partial run, 20.9 % of timeline):** 9 ENTER candidates. Linear extrapolation projects ≈ 43 over 2 years, ≈ 0.06 / day, far below target.
- **Live trades executed:** 0 (live trading is disabled by user instruction; LIVE_ORDER_GUARD remains in place).

The system is honest about the gap. This report's job is to explain it, not to hide it.

---

## 3. Total decisions

To be filled after full run. Partial-run total: **20,760** records.

## 4. WAIT count

Partial-run: **4**.

## 5. BLOCK count

Partial-run: **20,747**.

## 6. ENTER_CANDIDATE count

Partial-run: **9**.

## 7. Executed trades count

**0.** Live execution is gated by LIVE_ORDER_GUARD and disabled in this phase. Every P&L number in this report comes from the shadow simulator running over cached bars only.

## 8. Top rejection reasons

To be filled by the war-room runner. The dominant final_reason in the partial run was `outside_new_york_trading_window` (by design, ~75 % of the timeline) followed by `grade_below_threshold` and `incomplete_agreement`.

## 9. Grade distribution by mind

To be filled. Manual spot-check of the partial-run cycles file showed:

- **NewsMind** is overwhelmingly grade A (its only grade outside BLOCK is A).
- **MarketMind** mixes A / B / C inside the trading windows.
- **ChartMind** mixes A / B / C inside the trading windows.

This tells us, qualitatively, that **MarketMind and ChartMind grades are the choke**, not NewsMind. The full run will quantify it.

## 10. Decision distribution by mind

To be filled. Spot-check confirms:

- **NewsMind:** WAIT or BLOCK only. (Architectural — V4.7 acknowledges this.)
- **MarketMind:** mostly WAIT, occasional BUY/SELL, sometimes BLOCK on data-quality.
- **ChartMind:** mostly WAIT, occasional BUY/SELL.

## 11. Bottleneck analysis

To be filled. The attribution categories (defined in `bottleneck_attribution.py::_attribute`) are:

- `session_outside_window`
- `data_quality:<minds>`
- `brain_block:<minds>`
- `grade_below_A:<minds>`
- `consensus:directional_conflict`
- `consensus:incomplete_agreement`
- `consensus:brain_block`
- `consensus:unanimous_wait`
- `other:<reason>`

The runner returns counts and percentages per category, also broken down by pair and by trading window.

## 12. NewsMind failure analysis

NewsMind under V4.7 only emits WAIT (no objection) or BLOCK (real news risk). It is structurally unable to be a positive contributor; its only useful failure is BLOCK during real high-impact events. If the bottleneck table shows zero `brain_block:NewsMind`, the replay calendar is too sparse — see Hypothesis H14.

## 13. MarketMind failure analysis

MarketMind grades drop to B when regime classification is unsure (mixed trend / range, conflicting timeframes). If the A/A+ rate inside trading windows is materially below ChartMind's, MarketMind is the principal grade-gate failure. See Hypothesis H2. Test: `bottleneck_attribution.json::attribution["grade_below_A:MarketMind"]`.

## 14. ChartMind failure analysis

ChartMind is the sole directional voice under V4.7. The system can only enter when `chart.decision in {BUY, SELL}` AND `chart.grade in {A, A+}` AND no opposing News/Market. This means the upper bound on ENTER candidates is the count of ChartMind directional A/A+ in-window cycles. If that bound is below 2/day on average, the strict V4.7 rule cannot deliver the target *regardless* of any other change. See Hypotheses H1 and H4.

## 15. GateMind bottleneck analysis

GateMind under V4.7 is mechanical: 8 deterministic rules, all unit-tested (143/143 pass). Its job is to combine evidence, not to generate signal. It is not the choke — the choke lives upstream in the brains that feed it.

## 16. SmartNoteBook logging analysis

SmartNoteBook records HMAC-chained ledger entries per cycle (JSONL + SQLite mirror). The sandbox run halted because per-cycle records filled the container's `/tmp` partition after ~21 k cycles. On the user's Windows laptop with a real disk, this does not occur. Action: re-run on local disk via `Run_V47_Backtest.bat` to obtain the complete 99,298-cycle ledger.

For the production live system, audit must remain on. For backtest mode only, a write-throttle (record only ENTER cycles + every Nth WAIT/BLOCK) would let the replay run faster and lighter without weakening live audit. That is a V4.8 candidate, not a V4.7 fix.

## 17. Session / window analysis

The two NY trading windows total 6 hours per day:

- **pre_open** 03:00–05:00 UTC
- **morning** 08:00–12:00 UTC

Per design, ~75 % of the M15 timeline is `outside_window` and BLOCKed at the session rule. The runner reports per-window ENTER counts; if both windows are equally productive, the design is fine; if one window dominates, that's a calibration signal.

## 18. Data quality analysis

The runner emits per-mind data-quality distributions. Phase 9 fixed the weekend-gap false-stale bug; the full run will confirm whether residual `stale` / `missing` flags inside trading windows are above noise. See Hypothesis H7.

## 19. Backtest engine analysis

`replay/run_v47_backtest.py` walks unique timestamps in order, feeds each pair its own bar history truncated to `bars[lo:idx+1]` (entry-bar inclusive, no future bars), then calls the frozen orchestrator.

The shadow simulator in `shadow_pnl.py` uses `bars[entry_idx + 1 : ...]` only — Red Team probe **P1_no_lookahead_in_simulator** verifies this statically by parsing the source. P2_costs_deducted verifies the cost subtraction in every exit branch.

## 20. Rejected trades shadow analysis

The simulator computes three shadow modes:

| mode | rule |
|---|---|
| `shadow_chart` | enter on every directional ChartMind decision, ignoring grade and consensus |
| `shadow_grade_B` | enter when ChartMind directional, grade in {A, A+, B}, no opposing vote |
| `shadow_2_of_3` | enter when ChartMind directional, at least one other mind matching or WAIT |

Parameters: SL = 20 pips, TP = 40 pips (R:R 1:2), cost = 1.5 pips round-trip, max-hold = 24 bars (6 h on M15). Conservative SL/TP collision: same-bar both-hit counted as SL.

The runner produces a per-mode trade count, win rate, net pips, drawdown, plus per-pair and per-window breakdowns. Numbers fill in here once the full run completes.

## 21. Root causes found

To be filled with specific, evidence-backed statements (e.g. "ChartMind directional A-rate inside trading windows is X.Y % per cycle, which caps the strict V4.7 rule at Z trades/day"). Until the full run completes, this section deliberately stays empty rather than promote partial signal to root cause.

## 22. Hypotheses tested

15 hypotheses are registered in `replay/war_room/hypotheses.py`. Verdicts ("supported", "rejected", "inconclusive") are filled in by the runner once the corresponding test executes against the full-run data. The full list and tests are reproduced in the generated `hypotheses.md` artefact.

## 23. Fixes applied

**None applied during this investigation phase.** The brief is explicit: do not modify code until the evidence justifies it. Proposed fixes (each gated on its hypothesis surviving Red Team) appear in section 33.

## 24. Before / after comparison

- **Before V4.7:** 0 ENTER over 99,298 cycles (V4.6 measured).
- **After V4.7 (partial run, 20.9 %):** 9 ENTER, 0 errors.
- **After V4.7 (full run):** to be filled by `Run_V47_Backtest.bat` followed by `Run_V47_WarRoom.bat`.

## 25. Trades / day before / after

- Before: 0.0
- After (partial-run extrapolation): ≈ 0.06 / day. **Below the 2 / day target.**

## 26. Profit before / after

- Before: 0 trades, 0 P&L.
- After: shadow-simulator outputs (see section 20). No live P&L until shadow modes survive Red Team and a deliberate decision is made to relax a gate.

## 27. Drawdown before / after

- Before: undefined (no trades).
- After: shadow-simulator drawdown filled by runner. Red Team probe P7 enforces a drawdown / net-pips ratio < 0.6.

## 28. 150 % target analysis

A typical retail leverage (1:30) and 1 % equity per trade gives roughly 30 pips of move per 1 % of equity in EUR/USD. 150 % over two years is ≈ 4,500 net equity-points = ≈ 4,500–10,000 net pips depending on volatility regime. The strict V4.7 rule's net pip number on the partial run is far below that. Without calibration changes the strict rule cannot deliver 150 %. Whether the loosened modes can — that's exactly what the shadow simulator answers.

## 29. 2 trades / day target analysis

2 trades / day = 730 trades over 2 years = roughly one entry every 135 M15 bars during trading windows. The runner's `shadow_chart` mode is the upper bound; if its trade count over the full run is below 730, the target is structurally unreachable on M15 even with no grade gate at all, and the next iteration would have to widen the instrument set or change timeframe rather than relax a threshold.

## 30. Red Team attacks

Eight probes implemented in `replay/war_room/red_team.py`:

| id | probe | purpose |
|---|---|---|
| P1 | `no_lookahead_in_simulator` | static check — simulator never reads `bars[i ≤ entry_idx]` |
| P2 | `costs_deducted` | every exit branch subtracts COST_PIPS |
| P3 | `realistic_spread_floor` | actual median spread in cache ≤ assumed cost |
| P4 | `segmented_robustness` | each of 4 time segments must be individually profitable |
| P5 | `per_pair_robustness` | EUR/USD and USD/JPY each individually profitable |
| P6 | `per_window_robustness` | pre-open and morning each individually profitable |
| P7 | `drawdown_floor` | drawdown < 60 % of net pips |
| P8 | `loose_modes_dont_explode_drawdown` | looser modes ≤ 2× baseline drawdown |

Verdicts will be filled by the runner. Any loosening proposed in section 33 must survive *all* probes that apply to it; a single failure rejects the loosening.

## 31. Red Team results

To be filled by runner.

## 32. Regression tests added

The eight Red Team probes are themselves regression tests — the runner produces a `red_team.json` artefact that must continue to pass on every future iteration. Adding a probe as a `pytest` test is a V4.8 task; for V4.7 they live in the war-room toolkit and are invoked via `Run_V47_WarRoom.bat`.

## 33. Remaining limitations & proposed next iteration

1. Full 99,298-cycle backtest not yet completed; partial-run numbers honest but extrapolation fragile.
2. SmartNoteBook backtest-mode write throttle not yet implemented (preserves live audit, reduces replay write-amplification).
3. ChartMind setup detector calibration on M15 has not been audited against cached spread/volatility data; H1 and H4 still pending evidence.
4. Pre-existing orchestrator audit-id determinism test should be either fixed or removed — it asserts a behaviour that contradicts the documented design contract of `make_audit_id` (deterministic by inputs).
5. LIVE_ORDER_GUARD not loosened, will not be loosened in this phase.

**Conditional fix proposals — each gated on its hypothesis surviving Red Team:**

| trigger | proposed change |
|---|---|
| `shadow_chart` survives all probes AND ≥ 2 trades/day | promote ChartMind to sole directional gate (already partial under V4.7); keep grade A/A+ |
| `shadow_grade_B` survives all probes AND no per-pair regression | loosen grade gate to A/A+/B for ChartMind only, log per-mode |
| neither survives | declare M15 + 6h-window + 2-pair combination structurally unable to deliver 2/day; redesign instrument set or timeframe in V4.8 |
| H7 (data_quality stale misfire) supported | fix conditional that flags stale across legitimate gaps (Phase 9 candidate that did not stick) |

## 34. Final truth conclusion

V4.7 is correct as **architecture**. It is honest as a **numerical result on real data**. It is **insufficient** to hit 2 trades/day and 150 % under the current calibration. The system is not rescued yet. It is, however, no longer dishonest about why.

## 35. Is the system improved enough?

**No.** Improved structurally (architecture works) but not operationally (trade rate too low). One more rescue iteration is required, and only if the Red Team verdicts justify it.

## 36. Are more rescue iterations required?

**Yes — exactly one if evidence supports it; zero if Red Team rejects every loosening mode.** Decision criterion: the verdicts in section 30 + the trade counts in section 20. The decision tree is laid out in section 33.

---

## Appendix A. How to regenerate this report

1. On the Windows laptop, double-click `Run_V47_Backtest.bat` and let it run until `replay_runs/v47_2y/DONE` appears (resumable; safe to interrupt).
2. Double-click `Run_V47_WarRoom.bat`. It runs the six-step pipeline and overwrites this file with machine-emitted numbers.
3. Inspect:
   - `replay_runs/v47_warroom/diagnostics.md`
   - `replay_runs/v47_warroom/bottleneck_attribution.md`
   - `replay_runs/v47_warroom/shadow_pnl.md`
   - `replay_runs/v47_warroom/hypotheses.md`
   - `replay_runs/v47_warroom/red_team.md`
4. Decide, by Red Team verdict, whether to enter V4.8 (calibration) or to accept that the strict V4.7 cannot meet target.

## Appendix B. Files added in this phase

- `replay/war_room/__init__.py`
- `replay/war_room/diagnostics.py`
- `replay/war_room/bottleneck_attribution.py`
- `replay/war_room/shadow_pnl.py`
- `replay/war_room/hypotheses.py`
- `replay/war_room/red_team.py`
- `replay/war_room/report_writer.py`
- `replay/war_room/run_war_room.py`
- `Run_V47_WarRoom.bat`
- `HYDRA_4_7_TOTAL_FAILURE_INVESTIGATION_AND_PERFORMANCE_RESCUE_REPORT.md` (this file)

No source files in `gatemind/`, `chartmind/`, `marketmind/`, `newsmind/`, `smartnotebook/`, `orchestrator/`, or `contracts/` were modified.
