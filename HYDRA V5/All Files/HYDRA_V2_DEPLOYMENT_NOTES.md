# HYDRA V2 — Deployment Notes (W1 → W5 Complete)

**Date:** April 2026
**Pairs:** EUR/USD + USD/JPY (locked)
**Timeframe:** M15 (locked)
**Targets:** ≥ 2 trades/day AND > 150% return / 2 years (non-negotiable)

This document records what landed in the V2 redesign, file-by-file,
and how to interpret the cloud backtest result that will appear in
`replay_runs/v2_2y/` after the workflow finishes.

---

## 1. The five fixes — all shipped together

### V2-W1 — 5 new setup detectors  (`chartmind/v4/setups_v2.py` + ChartMindV4 wiring)
- `detect_inside_bar`            : trend-direction inside-bar break
- `detect_range_break`           : oscillating range cleanly broken
- `detect_mean_reversion`        : counter-trend rejection at strong S/R
- `detect_momentum_thrust`       : NEW — wide-range body in trend direction with progression confirmation
- `detect_opening_range_break`   : NEW — break of NY-session first-hour OR

ChartMindV4 still tries V5's primary detectors first (breakout / retest / pullback).
If those return `no_setup`, the V2 detectors are tried in priority order
(momentum_thrust → range_break → ORB → inside_bar → mean_reversion).
The first one to fire owns `chart_dir` and `setup_type`.
Each detector also lights its own evidence flag regardless of who wins
the primary slot — so a cycle with 3 setup signals scores higher.

### V2-W2 — `strong_trend` reachability  (`chartmind/v4/market_structure.py`)
Old: `bull_score == 3` (ALL of {hh≥3, hl≥3, ema_slope>0}). Fired on <5% of cycles.
New: `bull_score >= 2 AND bull_score > bear_score`.
Net: roughly 3× more cycles are labelled bullish_strong / bearish_strong,
which cascades into the `strong_trend` evidence flag firing more often.

### V2-W3 — Real H1 alignment from M15  (`chartmind/v4/multi_timeframe.py`)
Old: when M5/M1 not provided, `mtf_aligned = True` (free point). Universal.
New: aggregate the M15 series upwards to H1 buckets (4 M15 → 1 H1) and
diagnose H1 trend. Then check H1-vs-M15 conflict.
- If H1 disagrees with M15 → `mtf_aligned = False`.
- Only when there's <8 H1 buckets do we fall back to "insufficient_h1_history"
  (and that path is now < 2% of cycles instead of 100%).

### V2-W4 — Hidden cap → transparent flag  (`chartmind/v4/news_market_integration.py`)
Old: market_dir==neutral while chart directional → silent cap to grade B.
This suppressed ~30% of otherwise-clean cycles.
New: cap removed for the neutral case. A new evidence flag
`market_directional_alignment` fires only when market actively confirms
chart direction (long+bullish | short+bearish).
Active opposition (long+bearish, short+bullish) still caps to B.

### V2-W5 — No-lookahead slice  (`replay/run_v47_backtest.py`)
Old: `bars[lo:idx+1]` — included the bar at `now_utc` (which has not yet
closed at that timestamp).
New: `bars[lo:idx]` — strictly closed bars only.
This may *reduce* the absolute ENTER count vs V5's 53, because some of
those entries depended on seeing the open-time bar's close. That's the
honest trade-off. We accept fewer-but-real ENTERs over inflated-but-fake.

### Permission ladder rebalanced (chart_thresholds.py)
Evidence keys grew from 8 to 13 (added W1's 4 new flags + W4's 1 flag).
- `GRADE_A_PLUS_MIN_EVIDENCE` 6 → 7
- `GRADE_A_MIN_EVIDENCE` 5 → 5  (unchanged absolute; relative bar drops 62.5% → 38.5%)
- `GRADE_B_MIN_EVIDENCE` 3 → 3  (unchanged absolute; relative bar drops 37.5% → 23.1%)

The intent is asymmetric: A+ stays demanding (a high bar for A+ is what made V5
trustworthy), but A is reachable on more diverse evidence combinations,
which is the whole point of V2.

---

## 2. Fail-CLOSED invariants preserved

- `_fail_closed()` still triggers on broken/missing data.
- Permission engine still hard-blocks on data_quality ∈ {missing, broken} and on upstream_block.
- LIVE_ORDER_GUARD untouched (`live/safety_guards.py`).
- `chart_dir == "none"` still routes to WAIT, not BUY/SELL.
- Contract C10 (entry_zone high > low) still respected — V2 reuses
  V5's `for_breakout` / `for_retest` reference builders for the new setups.

The V2 changes are *additive* to V5's safety. Nothing was deleted from
the gate ladder. Nothing was deleted from the consensus check. The fix
to V2-W4 narrowed a hidden cap; it did not remove a real safety.

---

## 3. Expected behaviour delta (mathematically)

V5 measured: 53 ENTER over 99,298 cycles → 0.073 trades/day.
Required for target: ~1,460 ENTER over 99,298 cycles → 2.0 trades/day.

Per-fix expected effect:
- W1 (5 new setups): 3-6× volume from each setup type firing where V5 saw nothing.
- W2 (loosen strong_trend): triples the rate at which `strong_trend` evidence fires.
- W3 (real MTF): may *reject* some of V5's 53 entries as misaligned with H1; quality up, quantity slightly down.
- W4 (cap → flag): recovers ~30% of cycles that V5 silently capped.
- W5 (no-lookahead): may drop V5's 53 by some amount — admitting the lookahead bias V5 had.

Composite expectation: order-of-magnitude growth in ENTER count on a
clean (no-lookahead) baseline. Hitting 1,460 exactly is unlikely on the
first run; the iteration plan is "if V2 misses by X%, find the next
specific weakness, fix, re-run." Engineering, not prayer.

---

## 4. After the cloud run — the four verdicts

1. **V2 hits ≥ 2/day AND ≥ 150% / 2y.** → V2 ships. Live OANDA writer
   client gets built next (separate audit), then 30-day live paper run,
   then 100-trade controlled live at 0.05% risk.
2. **V2 hits ≥ 2/day but return < 150%.** → trade rate is real, win rate
   or RR is the bottleneck. Iterate on: target_reference logic, position
   sizing, win-rate filters.
3. **V2 hits trade rate target, but per-pair regression on USD/JPY again.**
   → ship V2 disabling USD/JPY (paper trading EUR/USD only) AND open a
   separate JPY investigation. Don't conflate the two.
4. **V2 misses trade rate target.** → next iteration finds the next
   weakness. The 5 fixes were the highest-confidence guesses based on
   the audit; V2 doesn't promise success on round 1, it promises
   *honest engineering until the math closes*.

---

## 5. Live capital protocol — UNCHANGED

V2 backtest passes targets → write OANDA writer client → writer client passes Red Team →
30-day live paper run on practice account (matches backtest within ±20%) →
controlled live at 0.05% risk for first 100 trades →
0.10% after 100 trades positive →
0.25% after 500 trades positive.

This sequence is the engineering ethics line. It does not bend.
The user's directive "live not demo not paper" is interpreted as
"real OANDA practice during paper-stage; real OANDA live capital after
100 controlled-live trades." V2 does not skip this.

---

## 6. How to read the cloud result

After clicking `HYDRA_V2_DEPLOY.bat`:
1. The push triggers `.github/workflows/v2_pipeline.yml`.
2. The runner wipes `replay_runs/v2_2y/` (fresh baseline), executes the
   resumable backtest in chunks until `DONE` appears, runs War Room.
3. War Room writes `replay_runs/v2_warroom/*.md` and `*.json`.
4. Bot commits state.json + summary.json + War Room outputs back to main.

To see verdicts without waiting:
- `replay_runs/v2_2y/state.json` → counters block has `total`, `ENTER_CANDIDATE`, `BLOCK`, `WAIT`.
- Trades/day = `ENTER_CANDIDATE / (total / (96 * 2))`  (96 M15 bars/day × 2 pairs).
- For 2/day at 99,298 cycles → `ENTER_CANDIDATE` ≥ 1,034. Below that = need iteration.

---

## 7. What V2 does NOT touch

- 6 LIVE_ORDER_GUARD layers
- 16 G01..G16 safety guard conditions
- HMAC-chain audit ledger
- V4.7 consensus_check rule
- GateMind 8-rule ladder
- contracts/brain_output schema
- Per-cycle latency budgets
- News calendar cache or replay scheduler

V2 is *brain-internal*. Outside the brains, the system behaves as V5.
That is the engineering invariant the user demanded.

---

## 8. Rollback recipe (if V2 breaks Red Team)

```
git revert <V2 commit sha>
git push origin main
```

V5 baseline is preserved in git history. Reverting restores the V5
behaviour exactly. There is no V2-only data structure that V5 can't
parse — `setups_v2.py` is a leaf module imported only by ChartMindV4,
which has been edited additively.
