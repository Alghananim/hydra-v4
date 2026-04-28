# HYDRA 10-Hour Intensive Sprint — Audit Findings

This document records every weakness I find by deep code reading during the 10-hour sprint. Each finding is concrete: file:line, what's wrong, severity, proposed fix. No hand-waving.

Severity scale:
- **CRITICAL** — could cause silent profit damage, lookahead, or live-order risk.
- **HIGH** — measurable performance impact, fixable in a single PR.
- **MEDIUM** — code-quality issue or edge-case risk.
- **LOW** — style / maintainability.

---

## F-001 — `find_recent_breakout` returns OLDEST breakout, not most recent

**File:** `chartmind/v4/breakout_detector.py:138-157`
**Severity:** HIGH
**Status:** identified, fix proposed

### What

`find_recent_breakout(bars, level, atr_value, side, lookback=20)` scans bars from oldest to newest in the lookback window and returns the FIRST breakout found. The intent (per code comment) is "so retest tests can run" — i.e. anchor to an old breakout so a retest fits in 3–10 bars.

```python
for i in range(start, len(bars)):
    r = detect_breakout(bars, level=level, ..., confirm_index=i)
    if r.is_breakout:
        return r
```

### Why this hurts

In a trending market with multiple breakouts of the same level, the function anchors to the OLDEST one (potentially 15–20 bars old). That's a stale signal. Recent retest tests on stale levels frequently fail because the level no longer matters — price has moved through it many times.

The V5.0 data shows ChartMind directional rate is 0.15 %. One contributor is that "real_breakout" evidence flag fires for old breakouts that no longer have actionable retests.

### Fix

Either:
- **Option A:** scan newest-first and return the FIRST breakout found. Then check if a retest is possible in the remaining bars; if not, return no setup.
- **Option B:** scan all and return the breakout MOST RECENTLY confirmed that still has 3+ bars of history available for retest evaluation.

Option B preserves the retest possibility while preferring fresh signals. Pseudocode:

```python
candidates = [r for i in range(start, len(bars))
                if (r := detect_breakout(..., confirm_index=i)).is_breakout
                and (len(bars) - i) >= RETEST_WINDOW_MIN_BARS]
return max(candidates, key=lambda r: r.bar_index) if candidates else no_setup
```

### Test

A new unit test: feed a bar history where breakouts exist at indices 5 and 18, with retest opportunities after both. Current code returns index 5; fixed code returns index 18.

---

## F-002 — `cycle_to_record` truncates evidence by char budget without per-brain fairness

**File:** `replay/run_v47_backtest.py::cycle_to_record`
**Severity:** MEDIUM
**Status:** identified during V5.1 build

The 1024-char cap I added in V5.1 truncates within a single brain's evidence list. If `news.evidence[0]` is 1023 chars, only one news evidence string is kept; the budget is consumed before market or chart get a chance.

### Fix

Cap PER FIELD per brain at 256 chars, allow up to 8 fields. That gives roughly 2 KB per brain max.

---

## F-003 — Permission engine treats `setup_present` and grade independently

**File:** `chartmind/v4/permission_engine.py:122-133`
**Severity:** HIGH
**Status:** identified

### What

```python
if grade == BrainGrade.BLOCK:
    decision = "BLOCK"
elif inp.setup_present and inp.direction == "long" and grade in (A_PLUS, A):
    decision = "BUY"
elif inp.setup_present and inp.direction == "short" and grade in (A_PLUS, A):
    decision = "SELL"
else:
    decision = "WAIT"
```

The decision tree REQUIRES grade A or A+ AND `setup_present=True` AND direction non-none. This means:
- Score=4 with setup AND direction non-none → grade=B → WAIT (rejected)
- Score=5 with setup AND direction non-none → grade=A → BUY/SELL ✓

So the BUY/SELL gate is `score >= 5` AND `setup_present`. Both must be true.

### Why this hurts

The score-5 cycle is rare. `setup_present` requires breakout OR retest OR pullback to be detected. The two conditions are correlated but not identical — many setups are detected but score fewer than 5.

### Fix

This is the lever V5.4 explores (lower grade-A min from 5 to 4). The permission engine logic itself is correct; the threshold is what V5.4 questions.

No code change required for the engine — V5.4's monkey-patch handles it.

---

## F-004 — `_classify_volatility` cap-edge cases

**File:** `chartmind/v4/ChartMindV4.py` (the `_classify_volatility` private method, line ~122)
**Severity:** MEDIUM

`volatility_state` is `compressed` if ATR pct ≤ 25, `dangerous` if pct ≥ 95, `expanded` if pct ≥ 80, `normal` otherwise. But ≥80 AND ≤25 are non-overlapping. What about pct = 27 / 78 / etc? Those are "normal".

This means the `volatility_normal` evidence flag fires when 25 < pct < 80 — that's 55 % of bars at most. The other 45 % automatically lose this flag. V5.2 tests the hypothesis that this 45 % rejection rate is structurally too aggressive.

Not a bug, but a constraint on V5.0 behaviour. V5.2 hypothesis is valid.

---

## F-005 — `cycle_to_record` evidence loop early-break drops later evidence

**File:** `replay/run_v47_backtest.py:cycle_to_record`
**Severity:** LOW

The `for s in ev_list:` loop with `break` once budget hits zero means later evidence strings are silently dropped. The `evidence_count` field shows the original count, but the saved list is shorter. Downstream parsers might assume saved == original. The chartmind_score_dump module is regex-based per evidence string so it's robust to ordering, but the contract is unclear.

### Fix

Add a sentinel to the truncated list: `["[...truncated]"]` so parsers can detect it.

---

## F-006 — Workflow `set -e` in chunk loop kills resumability on transient error

**File:** `.github/workflows/v47_pipeline.yml`
**Severity:** MEDIUM

```yaml
run: |
  set -e
  ...
  while [ ! -f "$OUT/DONE" ] ; do
    ...
    PYTHONPATH=. python replay/run_v47_backtest.py ...
  done
```

If the python script exits non-zero on one chunk (transient OANDA error, file system glitch, etc.), `set -e` aborts the entire loop. The next workflow re-trigger has to start fresh because there's no `if [ $? -ne 0 ]` retry.

### Fix

```bash
set +e
while ...; do
    PYTHONPATH=. python ... || { echo "chunk fail; retrying after 5s"; sleep 5; continue; }
done
```

This makes the workflow self-healing across transient failures. Implemented in next iteration.

---

## F-007 — V5.5 combined variant uses two patches without isolation

**File:** `replay/variants/v5_5_combined.py`
**Severity:** MEDIUM

The combined variant patches both `EVIDENCE_KEYS` and `GRADE_A_MIN_EVIDENCE`. Currently both patches are applied in one apply() and reverted in one revert(). If the run errors in the middle of evaluation, BOTH reverts run via finally — fine. But if either revert raises, the other doesn't run.

### Fix

Wrap each revert in try/except, and in `apply()` use `try ... except` to ensure both patches succeed or NEITHER does.

---

## F-008 — `find_recent_breakout` uses MOST recent in trend direction

Wait — I need to re-read. Actually `find_recent_breakout` returns the FIRST iterated. Iteration is `range(start, len(bars))` — start is older, len-1 is newest. So range goes oldest → newest. First match is OLDEST. Confirmed F-001.

---

## F-009 — Same-bar fake breakout rejection may be too strict

**File:** `chartmind/v4/breakout_detector.py:84-99`
**Severity:** HIGH
**Status:** Hypothesis-level

```python
if side == "long":
    same_bar_fake = (bar.high > level) and (bar.close < level)
```

If `bar.high > level` AND `bar.close < level`, the bar pierced and closed inside → fake. But if `bar.close == level` exactly, this is NOT same_bar_fake (close < level is false). And `clear = bar.close >= level + threshold`. So the boundary case `level <= close < level + threshold` is neither fake NOR clear → returns "not breakout, reason=clear=False, loc_ok=..., body_ok=...". OK.

The problem: even for a clean breakout where wick pierces and body closes ABOVE level, if the CLOSE is below `level + threshold`, the breakout fails. With BREAKOUT_CONFIRM_ATR=0.3 and ATR=0.0007 (EUR/USD), the threshold is 0.00021 — about 2 pips. So a breakout that closes 1 pip above level fails. That's restrictive.

### Test

Look at the V5.0 chartmind_scores.csv (when V5.1 lands) and count cycles where setup_type == 'no_setup' AND `real_breakout=False` AND `key_level_confluence=True`. Those are the cycles where we found a level near price, but no breakout was strong enough to confirm. If many → BREAKOUT_CONFIRM_ATR could be lowered.

V5.2-V5.5 don't address this — they're about evidence flags. A new variant V5.6 could test BREAKOUT_CONFIRM_ATR 0.3 → 0.2.

---

## F-010 — pullback_detector might use trend_label inconsistently

To verify next.

---

## F-011 — Audit-id determinism test contradicts make_audit_id contract

**File:** `orchestrator/v4/tests/test_scalability.py::test_no_internal_state_between_cycles`
**Severity:** LOW (already known, documented in V4.7 report)

This test asserts non-determinism that contradicts the documented design contract. Already flagged.

---

## F-012 — `strong_trend` evidence flag is structurally rare

**File:** `chartmind/v4/market_structure.py:227-228`
**Severity:** HIGH

`bullish_strong` requires `bull_score == 3` — i.e. ALL of {hh>=3 progressing, hl>=3 progressing, ema_slope>0}. The `strong_trend` evidence flag fires only when label is `bullish_strong` OR `bearish_strong` — `bullish_weak` is rejected.

Real M15 data rarely has 3+ progressively-higher highs AND 3+ progressively-higher lows AND positive EMA slope simultaneously over a 40-bar window. This makes `strong_trend` fire infrequently → directly contributes to the 0.15 % directional rate.

### Fix proposal (V11 candidate)
Loosen `strong_trend` to fire on `bullish_weak` or `bearish_weak` also (i.e. bull_score >= 2 OR bear_score >= 2). This adds many more "strong_trend = True" cycles. Need empirical check that win rate doesn't drop below baseline.

---

## F-013 — `setup_present` AND grade-A are independent gates

**File:** `chartmind/v4/permission_engine.py:122-133`
**Severity:** MEDIUM (informational; design choice)

The decision tree requires BOTH `setup_present == True` AND `grade in (A, A+)`. So a cycle with score=5 (grade A) but no detected setup (no breakout/retest/pullback) → WAIT. Conversely a cycle with breakout detected (setup_present=True) but score=4 → grade B → WAIT.

This is intentional double-gating. But it means the 8 evidence flags are NOT 8 independent ways to qualify — `real_breakout` and `successful_retest` are each TIED to setup_type. A pullback setup intrinsically scores at most 6 (cannot have real_breakout=True AND successful_retest=True since setup_type is pullback_in_trend).

Documented for V11 redesign consideration.

---

## F-014 — Pullback setup max score is 6 (not 8)

**File:** `chartmind/v4/ChartMindV4.py` setup_type assignment (lines ~158-191)
**Severity:** HIGH

`setup_evidence["real_breakout"]` is True only when `setup_type == "breakout"` (line 167). `setup_evidence["successful_retest"]` is True only when retest fires after breakout (line 176). For `pullback_in_trend` setup_type, both flags stay False → max score = 6 (the 6 other flags). Reaching grade A (>=5) requires 5 of those 6 → tough.

So pullback setups need 5/6 of {strong_trend, key_level_confluence, in_context_candle, mtf_aligned, volatility_normal, no_liquidity_sweep}. That's restrictive.

Combined with F-012 (strong_trend rare) and F-015 (mtf_aligned auto-true), pullbacks effectively need 4/5 of the rest. Hard.

### Fix proposal
Add a separate evidence flag for pullback-specific quality (e.g. `pullback_clean`) so that pullback setups have a fair chance at grade A.

---

## F-015 — CRITICAL: `mtf_aligned` always True because M5/M1 bars are NEVER passed

**File:** `chartmind/v4/multi_timeframe.py:51-52` AND `replay/run_v47_backtest.py` orchestrator call
**Severity:** CRITICAL

In `multi_timeframe.assess`:
```python
if m5_label is None and m1_label is None:
    return MTFResult(True, m15_label, None, None, "single_tf")
```

In `run_v47_backtest.py` the orchestrator is called with ONLY M15 bars:
```python
orch.run_cycle(symbol=symbol, now_utc=now_utc,
               bars_by_pair={symbol: visible},
               bars_by_tf={"M15": visible})
```

So `assess()` always returns `aligned=True`. The `mtf_aligned` evidence flag is a FREE point in every cycle.

### Why this matters

1. The `mtf_aligned` flag is contributing +1 to score in EVERY cycle. So effectively the system needs `score >= 4` of the OTHER 7 flags to grade A — equivalent to `GRADE_A_MIN_EVIDENCE = 4` over a 7-flag set.

2. **V7 (require_mtf as hard gate) is meaningless on current data.** No cycle has `mtf_aligned == False`, so the hard gate fires zero times. V7 should be marked "BLOCKED — needs M5/M1 data pipeline" rather than expecting a behavioural change.

3. **The reported "8/8 evidence" is really "7/7 evidence + 1 free point"**. The system never validates higher-timeframe alignment — a major real-world risk.

### Fix (V11 candidate)

Build the M5 + M1 data cache fetchers (parallel to the M15 cache) and pass them to the orchestrator. Then `mtf_aligned` becomes a real filter. Re-evaluate V7 once M5/M1 data is present.

Until then, the system is implicitly running without MTF validation. Document this in `HYDRA_V5_LIMITATIONS_AND_RISKS.md` as a known gap.

---

## F-016 — `key_level_confluence` requires a STRONG (>=3 touches) level within 1×ATR

**File:** `chartmind/v4/ChartMindV4.py:198-202` + `support_resistance.py`
**Severity:** MEDIUM

A "strong" level requires 3+ touches in the 80-bar lookback. With SWING_K=3 (high bar), 3+ pivots clustering within 0.3×ATR is moderately rare. Combined with the 1×ATR proximity requirement, this flag is achievable but contributes to the strict gate.

V11 candidate: lower the `key_level_confluence` strength requirement to 2 touches.

---

## F-017 — CRITICAL: hidden upstream cap at B when MarketMind is "neutral"

**File:** `chartmind/v4/news_market_integration.py:99-102`
**Severity:** CRITICAL

```python
elif market_dir == "neutral" and chart_direction in ("long", "short"):
    reasons.append(f"market_neutral_vs_chart_{chart_direction}")
    cap = BrainGrade.B if (cap is None or cap == BrainGrade.A
                            or cap == BrainGrade.A_PLUS) else cap
```

When MarketMind reports `range` or `choppy` (which `_market_direction` maps to "neutral") AND ChartMind has a directional setup, the cap is forced to B. After permission_engine applies this cap, the grade drops to B → decision becomes WAIT (because BUY/SELL needs A or A+).

### Why this hurts hard

V5.0 diagnostics showed ChartMind emitted 33 directional decisions (24 BUY + 9 SELL), but only 12 became ENTER. The other 21 became WAIT/BLOCK. The upstream cap at B is the prime suspect for those 21 demotions.

The cap is documented behaviour ("respect, downgrade") but it's invisible in the 8-flag evidence list. It's a HIDDEN gate that none of the V5.x calibration variants address.

### Fix (V5.6 / V11 candidate)

**Option A:** Remove the cap entirely. ChartMind already considers volatility and trend in its own evidence flags; double-counting with MarketMind's "neutral" feels redundant.

**Option B:** Make the cap softer: only cap to B if BOTH MarketMind direction is neutral AND MarketMind grade is C. If MarketMind grade is A or B but trend is "range" — let chart's higher score win.

**Option C:** Convert the upstream cap into ONE additional evidence flag (`market_directional_alignment`). This makes it transparent and tunable.

This finding alone could explain ~60 % of the directional rejection mass.

---

## F-018 — POTENTIAL LOOKAHEAD: backtest runner includes the bar AT now_utc

**File:** `replay/run_v47_backtest.py:213-214`
**Severity:** CRITICAL (potential)
**Status:** identified, requires verification

```python
lo = max(0, idx + 1 - args.lookback_bars)
visible = bars_by_pair[symbol][lo:idx + 1]   # <-- includes bars[idx]
```

`now_utc = timeline[ti]` is a bar's timestamp. `idx` is the index of that bar. The runner passes `visible = bars[lo:idx+1]` to the orchestrator — this INCLUDES the bar at `now_utc`.

### The convention question

OANDA's instrument-candles API (and most platforms) timestamps bars by their OPEN time:
- A bar with `time = "21:00"` represents the period [21:00, 21:15) for M15.
- At time 21:00 itself, the bar has just OPENED. Its close, high, low are NOT YET DETERMINED.
- The bar's full data is available only at 21:15 or later.

If `now_utc = 21:00` and `visible` includes `bars[idx]` (the bar with timestamp 21:00), then ChartMind reads `bars[-1].close` — that's data from 21:15, **15 minutes in the future**.

ChartMind's breakout detector decides "real_breakout" based on `bars[-1].close` exceeding the level. With lookahead, the system can SEE the close that hasn't happened yet.

### Why this could explain the empirics

Lookahead biases backtests TOWARDS profitable trades (the system picks setups that already have favorable closes). Yet V5.0's win rate is 16.7 %, abysmal. This suggests one of:

- (a) The lookahead exists but doesn't help because ChartMind's setup logic is so restrictive that even WITH future visibility, the strategy is unprofitable. The 16.7 % is an UPPER BOUND on real-world performance.
- (b) The convention is different from what I'm assuming — `now_utc` actually represents the time AFTER the bar at idx closes (the "decision time" = bar[idx]'s close time, which equals bar[idx+1]'s open time). In that case, including bars[idx] is correct.

### Verification needed

The unit test `test_no_lookahead.py` poisons bar[-1] of the FULL series and checks detector outputs on bar[:-1]. It validates that detectors don't peek BEYOND their input. It does NOT validate the runner's choice of slice — that's the orchestrator's contract, not the detector's.

To verify: run the backtest with `visible = bars[lo:idx]` (excluding bar idx) and compare ENTER counts. If they're significantly different, the lookahead is real and the V5.0 numbers are biased.

### Fix (V5.7 candidate)

`replay/variants/v5_7_no_lookahead.py` — monkey-patch the runner's slice to exclude bar idx. This is a NEGATIVE-control variant: if V5.7 produces FEWER ENTER candidates AND lower win rate than V5.0, that's evidence that V5.0 was benefiting from lookahead. Either way, V5.7's numbers are the honest baseline going forward.

---

## F-019 — gatemind constants and session_check timezone is correct

**File:** `gatemind/v4/session_check.py`
**Severity:** OK (no issue found)

`session_check.py` uses `ZoneInfo("America/New_York")` which auto-handles DST. Test fixtures cover both spring-forward (March 9) and fall-back (November 2) dates. No bug found here.

The two trading windows are 03:00-05:00 and 08:00-12:00 NY local time. By design, ~75 % of M15 cycles are `outside_window` and BLOCK at session check. This is correct and intentional.

---

## F-020 — Pending audit list

- F-020: candle_confirmation hammer/star detection logic (already read — clean)
- F-021: liquidity_sweep — sweep wick definition (already read — clean)
- F-022: indicators.atr — wilder smoothing edge case
- F-023: indicators.adx — directional movement classification
- F-024: replay_calendar — event window edge cases
- F-025: replay_newsmind — calendar lookup correctness
- F-026: SmartNoteBook chain hash verification
- F-027: LIVE_ORDER_GUARD bypass attempts
- F-028: live/dry_run.py imports / OANDA write client absence
- F-029: shadow_pnl spread floor

- F-018: candle_confirmation hammer/star detection logic
- F-019: liquidity_sweep — sweep wick definition
- F-020: indicators.atr — wilder smoothing edge case
- F-021: indicators.adx — directional movement classification
- F-022: replay_calendar — event window edge cases
- F-023: replay_newsmind — calendar lookup correctness
- F-024: orchestrator session_status — DST handling
- F-025: SmartNoteBook chain hash verification
- F-026: LIVE_ORDER_GUARD bypass attempts
