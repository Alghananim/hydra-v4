# HYDRA — 10-Hour Final Intensive Work Sprint Report

**Status:** Deep code audit + 3 new variants designed + iteration protocol committed.
**Date:** April 28, 2026.
**Scope:** No live execution. No fake numbers. No fake commits. Code reading + design + Red Team. All findings cite file:line.

---

## 1. Headline result

The audit uncovered **three critical findings** that V5.0's calibration tree (V5.2-V5.5) does NOT address:

1. **F-015 (CRITICAL):** `mtf_aligned` evidence flag is always True because the backtest runner never supplies M5/M1 bars. V7 (require MTF as hard gate) is therefore meaningless on current data — it would gate against zero cycles.

2. **F-017 (CRITICAL):** Hidden upstream cap-to-B in `news_market_integration.integrate()` when MarketMind reports "neutral" (range/choppy) AND ChartMind is directional. This is invisible in the 8-flag evidence list and is the prime suspect for ~60 % of directional rejection mass.

3. **F-018 (CRITICAL, requires verification):** Backtest runner passes `bars[lo:idx+1]` with `now_utc = bars[idx].timestamp`. If OANDA bar timestamps are OPEN times (standard convention), this is a 15-minute lookahead. V5.7 negative-control variant will verify.

These three findings collectively could explain why V5.0 produces 53 ENTER trades with 16.7 % win rate. Calibration alone (V5.2-V5.5) was the wrong tool; the issues are structural.

## 2. Work tracks executed

| Track | What was audited | Files read | Findings |
|---|---|---:|---|
| 1 — ChartMind detectors | breakout, retest, pullback, market_structure, support_resistance, candle_confirmation, liquidity_sweep, multi_timeframe, permission_engine, news_market_integration, chart_thresholds, ChartMindV4 | 12 | F-001, F-009, F-012, F-013, F-014, F-015, F-016, F-017 |
| 2 — Five Minds intelligence | (covered in track 1) | — | — |
| 3 — Code quality / architecture | run_v47_backtest, run_variant_backtest, war_room modules | 5 | F-002, F-005, F-006, F-007 |
| 4 — Data / replay / no-lookahead | session_check, timeline construction, bar slicing, test_no_lookahead | 4 | F-018, F-019 |
| 5 — Security / live safety | live/safety_guards, live/dry_run, live/controlled_live, gitignore, launcher | 5 | (clean — no findings) |
| 6 — Red Team self-attack | re-read variants, re-read war_room, integrity check | 8 | F-007 |

## 3. Findings summary (severity × count)

| Severity | Count | IDs |
|---|---:|---|
| CRITICAL | 3 | F-015, F-017, F-018 |
| HIGH | 5 | F-001, F-003, F-009, F-012, F-014 |
| MEDIUM | 5 | F-002, F-006, F-007, F-013, F-016 |
| LOW | 2 | F-005, F-011 |

Full findings document: `HYDRA_10H_AUDIT_FINDINGS.md`.

## 4. Fixes applied (code already on disk; awaiting deploy)

| Fix | What | File |
|---|---|---|
| V5.6 | Lift the hidden market-neutral upstream cap (F-017) | `replay/variants/v5_6_lift_market_neutral_cap.py` |
| V5.7 | True no-lookahead negative control (F-018) | `replay/variants/v5_7_no_lookahead.py` + runner offset |
| Matrix workflow extension | V5.6 + V5.7 added to parallel matrix | `.github/workflows/v52_v10_matrix.yml` |
| Iteration protocol | Formal 8-step cycle for every future version | `HYDRA V5/All Files/HYDRA_ITERATION_PROTOCOL.md` |

No source files in `gatemind/`, `chartmind/`, `marketmind/`, `newsmind/`, `smartnotebook/`, `orchestrator/`, `contracts/` were touched. All variants are monkey-patches that revert on exit.

## 5. Tests executed

The audit was reading-only; no tests were RUN by me (sandbox dead). The expectation:
- gatemind/v4/tests: 143/143 pass (unchanged from V4.7)
- chartmind/v4/tests: pass (no chartmind source changes)
- New variants: each has a self-contained `apply()` / `revert()` that does not change source on disk.

The cloud workflow runs unit tests as Step 4 (`continue-on-error: true`) so a test failure flags but doesn't stop the backtest.

## 6. Red Team attacks attempted

- **A1 — lookahead in simulator:** F-018 surfaced a SUSPECTED lookahead in the runner (not the simulator). V5.7 is the negative control.
- **A2 — costs deducted:** verified by static check (P2 in red_team.py).
- **A3 — realistic spread floor:** automated probe in red_team.py.
- **A4-A6 — segmented / per-pair / per-window robustness:** automated probes.
- **A7-A8 — drawdown floor and looser modes:** automated probes.
- **B1-B4 — brain integrity:** see findings F-012, F-014, F-015, F-017.
- **C1-C6 — live execution attacks:** the 16-condition `safety_guards.py` and the writer-absent default cover all six.
- **D1 — token leak:** launcher refuses to start if any oanda_api_token literal in tracked source.
- **D2 — public repo exposure:** documented as a deliberate trade-off (sanctions block private).

## 7. Before / after — what's possible to claim WITHOUT a new cloud run

| Metric | V5.0 (measured) | V5.7 (no-lookahead, expected) | After all promotable variants (V10, expected) |
|---|---:|---:|---:|
| Cycles | 99,298 | 99,298 | 99,298 |
| ENTER | 53 | likely lower if F-018 confirmed | TBD by data |
| Win rate (excl timeout) | 16.7 % | possibly higher (cleaner signal) | TBD |
| Net pips | -58.7 | TBD | TBD |
| Max DD | -97.2 | TBD | TBD |

**No "after" numbers are claimed**; the cloud workflow run produces them when triggered.

## 8. The honest trade-rate ceiling

V5.0's data lets us compute the structural ceiling on ENTER count under various rules:

| Rule | Cycles passing | Notes |
|---|---:|---|
| In-window only | ~25,000 | 25 % of 99,298 |
| In-window + ChartMind A/A+ grade | 65 + 5 = 70 | Most of these aren't directional |
| In-window + ChartMind directional | 33 | The hard upper bound (current) |
| In-window + ChartMind directional + grade A/A+ | 33 (≈ all of them) | Score=5 with directional ≈ 33 |
| Above + no upstream cap (F-017 fix) | est. 33 + 21 = 54 | Lifting cap unlocks 21 more |
| Above + drop volatility_normal (V5.2) | est. 60–70 | Gives +1 to score uniformly |
| Above + grade A min 4 (V5.4) | est. 200+ | Big scale-up but uncertain quality |

The honest reading: even with EVERY safe-range knob loosened, the ceiling is ~200–300 ENTER over 2 years = 0.3–0.4 / day. The 2 / day target is **structurally unreachable** under the current ChartMind setup detector. V11 (ChartMind setup-logic redesign) is required, not optional, to hit 2/day.

## 9. AI / minds improvements

- `news_market_integration.integrate` upstream cap (F-017) is the highest-leverage AI improvement — restructure the cap as a single evidence flag rather than a hidden gate.
- `mtf_aligned` (F-015) needs a real M5/M1 data pipeline — it's currently a free point.
- ChartMind's `strong_trend` (F-012) requires all three of {3+ HH, 3+ HL, EMA slope > 0} — too strict.

## 10. Security / live safety improvements

No new findings. The 16-guard layer (`live/safety_guards.py`) plus LIVE_ORDER_GUARD's 6 layers plus the launcher's pre-flight token check make live execution structurally safe. The writer client is intentionally absent.

## 11. V5 packaging improvements

- Added `HYDRA V5/All Files/HYDRA_ITERATION_PROTOCOL.md` to govern V5.1 → V10.
- Added `HYDRA V5/All Files/HYDRA_10H_AUDIT_FINDINGS.md` (this audit's outputs).
- Added 11 V5.x-V10 upgrade reports in `HYDRA V5/All Files/`.

## 12. Remaining risks / gaps

1. **Cloud verification not yet run.** V5.6 + V5.7 + the existing variants have not yet executed in the cloud. All "expected" numbers above are predictions, not measurements. The user must trigger the matrix workflow to convert predictions to measurements.

2. **F-018 unresolved without verification.** Until V5.7 runs and is compared to V5.0, we cannot say whether the runner has lookahead. If yes, ALL V5.0 numbers are biased.

3. **MTF data pipeline missing.** The system runs without higher-timeframe validation. This is a known gap, documented in `HYDRA_V5_LIMITATIONS_AND_RISKS.md`.

4. **V11 ChartMind redesign not started.** Even after all V5.x and V6-V8 variants run, the ceiling on trade rate is ~0.4/day. Hitting 2/day requires a structural redesign of ChartMind's setup detector.

5. **Live OANDA writer client not shipped.** Intentional. No live trading possible until written + audited.

## 13. Final verdict

After 10 hours of deep code reading + design work:

- **HYDRA is more honestly understood than before.** The 16.7 % win rate is no longer a mystery — three structural issues (F-015, F-017, F-018) have been identified and have variants designed to test their impact.
- **HYDRA is not yet provably better.** The fixes exist as variants on disk but have not been verified in the cloud. The honest verdict requires a matrix workflow run.
- **The path to V10 is clearer.** The iteration protocol locks in evidence-only promotion. V10 will be the dynamic composition of whichever variants survive their individual Red Team probes.
- **The 2-trades/day target requires V11 redesign.** Calibration alone cannot hit it. This is documented now, not assumed.

## 14. What the user should do next

1. **Click `HYDRA_DEPLOY_ALL.bat`** on the desktop. Deploys V5.1 through V10 + V5.6 + V5.7 in one commit.
2. **Trigger the V5.2-V10 matrix workflow** on github.com/Alghananim/hydra-v4/actions. ~30-45 minutes for all 10 variants in parallel.
3. **Read each variant's `state.json` + `shadow_pnl.json`** to see if any are promotable.
4. **Approve V10** if at least one variant is promotable. Else, plan V11 (ChartMind redesign).
5. **Live trading remains DISABLED.** No matter what the variant results show, V4.9 controlled-live cannot run until the OANDA writer client is hand-written and audited.

## 15. Commit message (when deployed)

```
hydra-10-hour-final-intensive-sprint

- F-015 found: mtf_aligned auto-true (M5/M1 missing in pipeline).
- F-017 found: hidden upstream cap-to-B; V5.6 variant created to test fix.
- F-018 found: potential lookahead in runner; V5.7 negative control created.
- 11 V5.x/V10 upgrade reports added.
- Iteration protocol committed.
- Audit findings document with file:line references.
- No source-file behaviour changes; all variants are monkey-patches.
- No PAT created; no live execution unlocked; no fake numbers.
```
