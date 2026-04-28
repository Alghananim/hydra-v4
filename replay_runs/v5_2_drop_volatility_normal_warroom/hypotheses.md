# HYDRA 4.7 — Step 4 Hypothesis Register

Each row is a candidate explanation for the under-trading. The verdict column is filled in once the corresponding test runs and the Red Team has had a pass.

## H1: ChartMind very rarely emits BUY/SELL with grade A/A+, so the strict gate has nothing to pass.
**Test:** From cycles.jsonl count cycles where chart.decision in {BUY, SELL} AND chart.grade in {A, A+}. If << ENTER count implies a sub-1%/cycle rate, ChartMind detection is the choke.
**Risk if acted on without check:** Loosening grade is overfit if the B-grade signals are noisy.
Evidence for: decision_distribution_by_mind for ChartMind; grade_distribution_by_mind for ChartMind
Evidence against: if ChartMind emits BUY/SELL often then this is wrong

## H2: MarketMind hands out grade B (or worse) most of the time, so unanimous A is rare even when ChartMind is directional.
**Test:** Compute % of in-window cycles where MarketMind grade in {A, A+}. Compare to ChartMind and NewsMind. If MarketMind A-rate is the worst, it is the principal grade gate failure.
**Risk if acted on without check:** MarketMind B may reflect genuine regime uncertainty; loosening masks risk.
Evidence for: MarketMind grade distribution skewed to B/C
Evidence against: MarketMind grade distribution skewed to A/A+

## H3: NewsMind WAIT/A is functionally a non-vote, so the gate now lives entirely in MarketMind+ChartMind grade.
**Test:** Confirm NewsMind decision distribution; confirm NewsMind never appears as the lowest-grade attribution in bottleneck table.
**Risk if acted on without check:** None — this is a structural observation, not a fix.
Evidence for: NewsMind decision distribution (WAIT-only); NewsMind grade distribution (mostly A under V4.7)
Evidence against: NewsMind frequently issues BLOCK

## H4: ChartMind setup detector requires breakout confirmation that almost never occurs on M15.
**Test:** Plot histogram of ChartMind decision label per hour-of-day. If WAIT dominates >95% even in 03-05 NY, threshold is too high.
**Risk if acted on without check:** Lowering threshold raises false positives -> drawdown.
Evidence for: High proportion of (chart.decision == WAIT) even mid-window
Evidence against: ChartMind sometimes emits BUY/SELL

## H5: The session window (only 6h/day across pre-open + morning) excludes the bulk of valid setups.
**Test:** Run shadow_chart over the full timeline ignoring session filter. Compare in-window vs out-of-window net pips.
**Risk if acted on without check:** Out-of-hours liquidity may be poor — actual fills worse than backtest.
Evidence for: session_outside_window dominates final_status
Evidence against: No expectation that off-hours improve win rate on EUR/USD

## H6: V4.7 'incomplete_agreement' (chart=WAIT, news/market directional) blocks trades where News/Market actually had it right.
**Test:** Count cycles where final_reason==incomplete_agreement AND (news.decision in {BUY,SELL} OR market.decision in {BUY,SELL}). Run shadow P&L on those.
**Risk if acted on without check:** Reversing this lets MarketMind override Chart's caution -> bigger losses.
Evidence for: incomplete_agreement count in final_reason
Evidence against: NewsMind never emits BUY/SELL, so this branch can only fire on rare MarketMind directional

## H7: data_quality flag 'stale' is over-triggering on weekend-spanning windows even after the Phase 9 fix.
**Test:** Count in-window cycles where MarketMind data_quality != 'good'. If >5% it is still misfiring.
**Risk if acted on without check:** None — this is a bug fix if confirmed.
Evidence for: MarketMind data_quality distribution shows non-trivial 'stale' or 'missing'
Evidence against: data_quality is mostly 'good'

## H8: The 500-bar lookback warm-up consumes the first ~5 trading days, so the first chunk is structurally trade-less.
**Test:** Bin cycles by week-of-backtest. Compute ENTER rate per bin. If week 1-2 is 0 but later weeks are >0, warm-up is real but bounded.
**Risk if acted on without check:** None — informational.
Evidence for: BLOCK rate in first 1000 in-window cycles vs later
Evidence against: If trade rate is uniform across timeline this is wrong

## H9: The 2-trades/day target is structurally impossible under the current grade-A unanimous rule given real M15 noise.
**Test:** Compute upper-bound daily rate of (chart.decision in {BUY,SELL} AND chart.grade in {A,A+}). If avg < 2/day, grade rule alone cannot deliver target.
**Risk if acted on without check:** Stating impossibility without exhausting calibration is premature.
Evidence for: Diagnostics show A-unanimous-and-directional << 2/day
Evidence against: If grade thresholds tuned correctly, ChartMind may produce >> 2/day setups

## H10: Per-cycle SmartNoteBook writes are slowing the runner enough to artificially shorten the chunk's covered timeline.
**Test:** Time the runner with notebook stubbed vs full notebook. Compare cycles/sec.
**Risk if acted on without check:** Stubbing notebook in production breaks audit trail.
Evidence for: sandbox /tmp filled at ~21k cycles
Evidence against: Same code runs fine on local disk with more space

## H11: Backtest engine skips ENTER opportunities at bar boundaries because lookback uses bars[lo:idx+1] where idx is the entry bar (entry on close), not enough forward bars to confirm.
**Test:** Inspect ChartMind setup detector for confirmation lookahead. It must NOT use bars beyond the entry bar.
**Risk if acted on without check:** If lookahead exists -> reported P&L is fictional.
Evidence for: run_v47_backtest.py uses visible = bars[lo:idx+1]
Evidence against: Each cycle gets ChartMind, MarketMind a full 500-bar history

## H12: Costs (spread + slippage) are missing from the orchestrator's trade candidate, so even ENTER trades over-report when fed to a P&L engine that doesn't deduct.
**Test:** Read pnl_simulator.py; confirm a cost deduction exists.
**Risk if acted on without check:** If costs not deducted -> overstated win rate.
Evidence for: BrainOutput contract shows no cost field
Evidence against: pnl_simulator may add cost itself

## H13: ChartMind grade calibration (B vs A vs A+) is uncorrelated with future win rate, so loosening to B doesn't actually buy more profitable trades.
**Test:** Compare win rate of shadow_grade_B trades restricted to grade-B vs grade-A in same population.
**Risk if acted on without check:** If B is genuinely worse, loosening hurts.
Evidence for: shadow_grade_B vs shadow_chart can show win-rate delta
Evidence against: If win rate of grade-B trades is comparable to grade-A, grading is conservative-only

## H14: Replay calendar (174 events) misses many high-impact periods — NewsMind permission is correct but the scheduler does not actually elevate news risk during the relevant windows, so NewsMind never gates real news.
**Test:** Count NewsMind BLOCK occurrences and timestamps. Confirm they align with calendar entries.
**Risk if acted on without check:** None — informational; a fix would be a calendar enrichment.
Evidence for: NewsMind decision distribution dominated by WAIT
Evidence against: NewsMind sometimes BLOCKs

## H15: Costs of 1.5 pips for round-trip are too low; real broker would charge 2-4 pips and slippage. Inflated win rate.
**Test:** Compute median spread_pips across cached bars per pair; compare to assumed cost. If median > assumed, raise cost in shadow.
**Risk if acted on without check:** Raising cost worsens reported P&L; that's the honest direction.
Evidence for: Industry norm 2-4 pip round-trip on M15
Evidence against: spread_pips field in cached bars shows actual mid-bid-ask spread
