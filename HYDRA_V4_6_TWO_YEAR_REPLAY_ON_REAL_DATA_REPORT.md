# HYDRA V4.6 — TWO-YEAR REPLAY ON REAL DATA REPORT

**Generated:** 2026-04-28
**Phase:** V4.6 — full 2-year replay of the real frozen orchestrator chain on real OANDA data. No trading-logic changes. No live execution. No order paths exercised.
**Language:** English only inside the project.
**Verdict (TL;DR):** ✅ **V4.6 COMPLETE.** The replay ran end-to-end over 99,298 cycles spanning 730 days on EUR/USD + USD/JPY using the real five-brain chain. The truth: **0 ENTER_CANDIDATE in two years**, exactly as Phase 9 predicted. The cause is architectural (the NewsMind decision contract collides with GateMind's unanimous-direction rule), not market difficulty. 10/10 Red Team integrity attacks verified the run is honest — no lookahead, no silent failures, no gate bypasses.

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Cycles processed | **99,298** |
| Trading days observed | **517** |
| Pairs | EUR/USD + USD/JPY |
| Granularity | M15 |
| Date range | 2024-04-28 01:00 UTC → 2026-04-28 01:00 UTC (~730 days) |
| **ENTER_CANDIDATE** | **0** |
| WAIT | 40 |
| BLOCK | 99,258 |
| Orchestrator errors | 0 |
| Silent failures | 0 |
| Calendar events fed to NewsMind | 174 (Fed/ECB/BoJ + NFP/CPI/speeches, 2024–2026) |
| Files changed in V4.6 | **0** (verification only) |
| Red Team integrity attacks | **10 / 10 passed** |

**Trades/day target:** 0 / 517 = **0.000 trades/day** (target ≥ 2). Result: **NOT MET**.
**Return % target:** **0.00%** (target > 150%). Result: **NOT MET**.

The numbers are real. The cause is documented. No fabrication.

---

## 2. Data Source

Already validated in V4.4:
- `data_cache/EUR_USD/M15/merged.jsonl` — 49,649 candles, `ok=true`.
- `data_cache/USD_JPY/M15/merged.jsonl` — 49,649 candles, `ok=true`.
- Both downloaded by `OandaReadOnlyClient` from OANDA v3 REST API (live endpoint, read-only).
- 0 duplicates, 0 NaN, 0 non-complete, 0 naive timestamps, 0 out-of-order across both pairs.

---

## 3. Date Range

**2024-04-28 01:00 UTC → 2026-04-28 01:00 UTC** = exactly 730 days.

---

## 4. Symbols Tested

| Symbol | Cycles |
|---|---|
| EUR_USD | 49,649 |
| USD_JPY | 49,649 |
| **Total** | **99,298** |

Per-pair fairness verified by Red Team Attack 8: both pairs received identical cycle counts, no pair was skipped.

---

## 5. Timeframe

**M15** (15-minute candles).

---

## 6. New York Windows Used

| Window | NY Local | Per-cycle session label in records |
|---|---|---|
| PRE_OPEN | 03:00 – 04:59 | `in_window_pre_open` |
| MORNING | 08:00 – 11:59 | `in_window_morning` |
| Outside | everything else | `outside_window` |

Distribution observed in 2-year run:

| Session | Cycles | % |
|---|---|---|
| outside_window | 74,482 | 75.0% |
| in_window_morning | 16,544 | 16.7% |
| in_window_pre_open | 8,272 | 8.3% |

Total in-window: 24,816 cycles (25.0%) — matches the design (24 of every 96 M15 bars per day).

---

## 7. Replay Architecture

```
Loader
  ↓ load_bars("EUR_USD") + load_bars("USD_JPY")
  ↓ each bar → Bar dataclass (tz-aware UTC, finite OHLC)
Calendar
  ↓ build_replay_occurrences(start - 7d, end + 7d)
  ↓ 174 historical events (FOMC, NFP, CPI, ECB, BoJ, speeches)
EventScheduler.load_occurrences(...)
  ↓
ReplayNewsMindV4(scheduler)         # calendar-only, NO HTTP
  ↓ (drop-in replacement for live NewsMindV4)
HydraOrchestratorV4(
  smartnotebook=SmartNoteBookV4(...),
  newsmind=ReplayNewsMindV4(...),
  marketmind=MarketMindV4(),         # frozen production code
  chartmind=ChartMindV4(),           # frozen production code
  gatemind=GateMindV4(),             # frozen production code
)
  ↓
TIMELINE = sorted({bar.timestamp for pair in pairs for bar in bars[pair]
                                     if start_utc <= bar.timestamp <= end_utc})
  ↓ 49,649 unique bar timestamps in window
FOR each timestamp in TIMELINE:
  FOR each symbol in {"EUR_USD", "USD_JPY"}:
    visible = bars[symbol][lo : idx+1]   # last 500 bars only — past data
    orchestrator.run_cycle(symbol, now_utc, {symbol: visible}, {"M15": visible})
    → DecisionCycleResult written
  ↓
99,298 records written to cycles.jsonl
```

Lookback cap (`lookback_bars=500`) is a performance optimisation — brains' indicators (ATR, EMA, structure detection) only need recent history. This does not affect correctness; it speeds each cycle from ~800 ms to ~17 ms.

---

## 8. Proof Real HYDRA Five-Mind Chain Was Used

| Evidence | Source |
|---|---|
| Imports | The runner imports `HydraOrchestratorV4` from `orchestrator.v4.HydraOrchestratorV4` directly. No mock orchestrator. |
| Real per-brain code | `MarketMindV4()`, `ChartMindV4()`, `GateMindV4()`, `SmartNoteBookV4(notebook_dir)` — instantiated with default constructors (no test stubs). |
| Real news (calendar-only replacement) | `ReplayNewsMindV4(scheduler)` is a documented replay-mode replacement for live `NewsMindV4` — same `evaluate(pair, now_utc, current_bar=None) → BrainOutput` interface. Returns BLOCK in blackout, A grade outside blackout. No HTTP. |
| Brain output integrity | All 99,298 cycles produced valid `BrainOutput` instances; no isinstance violation; no `MissingBrainOutputError`; no `ORCHESTRATOR_ERROR`. |
| All 5 minds executed per cycle | Verified by orchestrator's deterministic call sequence (lines 220–264 of `HydraOrchestratorV4.py`); confirmed by per-brain grade/decision counts in §17. |

---

## 9. No-Lookahead Controls

| Control | Mechanism | V4.6 evidence |
|---|---|---|
| Visible-bar slice | `bars[symbol][lo : idx+1]` strictly contains bars up to and including `now_utc` | Red Team Attack 1: 99,298 cycles checked, 0 lookahead-leak count |
| Replay calendar | Pre-published Fed/ECB/BoJ schedule + computed NFP/CPI cadence; deterministic | All 174 events in window verified ≤ end_utc |
| ChartMind ATR | Computed via `marketmind.v4.indicators.atr` over the visible window (ChartMind tests 120/120 pass after V4.3 fix) | structural |
| MarketMind data_quality | `now_utc` passed; weekend-gap fix (Phase 9) makes assess work over 500-bar windows | structural |
| SmartNoteBook lessons | `lesson.allowed_from_timestamp = end_of_replay`; no lessons emitted DURING replay (only after) | 0 lessons fed into mid-replay decisions |
| Orchestrator-level future check | `_validate_inputs` rejects naive datetime | architectural |
| Future cycle check (Red Team) | All 99,298 cycle timestamps ≤ end_utc | Red Team Attack 2: 0 future cycles |

---

## 10. SmartNoteBook Logging Behaviour

Every cycle writes a record (or fails loudly):

| Cycle outcome | SmartNoteBook records written | V4.6 count |
|---|---|---|
| ENTER_CANDIDATE | DECISION_CYCLE + GATE_AUDIT | 0 (no ENTER produced) |
| WAIT | DECISION_CYCLE + GATE_AUDIT | 40 |
| BLOCK | DECISION_CYCLE + GATE_AUDIT | 99,258 |
| ORCHESTRATOR_ERROR | ORCHESTRATOR_ERROR record (special) | 0 (no errors) |
| SmartNoteBook write failure | force `final_status = BLOCK` with `smartnotebook_record_failure:` marker | 0 (Red Team Attack 6) |

Total records written: ~99,298 × 2 (DECISION_CYCLE + GATE_AUDIT) = ~198,596 entries chained-hashed. SmartNoteBook integrity maintained.

---

## 11. Live-Order Block Proof

| Layer | Mechanism | Status during V4.6 |
|---|---|---|
| LIVE_ORDER_GUARD_ACTIVE | Module flag, sentinel-burned-in | TRUE throughout |
| Order methods on OandaReadOnlyClient | 7 wrapped (submit/place/close/modify/cancel/SL/TP) | All raise on call |
| HTTP layer | `urllib.request` only, GET to `/v3/instruments/...` and `/v3/accounts/{id}/{instruments,summary}` | No POST to OANDA |
| OANDA endpoints touched in V4.6 | **NONE** — replay reads from local `data_cache/` only | bridge not invoked at all |
| Order endpoints reached | **0** | — |
| Network calls during replay | **0** to OANDA, **0** to Anthropic (ReplayNewsMindV4 is calendar-only; orchestrator does not call Anthropic in v4.0) | — |

V4.4 + V4.2 already proved the LIVE_ORDER_GUARD via 16 + 12 Red Team attacks. V4.6 makes the additional empirical claim that **the entire 2-year replay touched zero broker endpoints**.

---

## 12. Cost / Spread / Slippage Assumptions

| Item | V4.6 status |
|---|---|
| Spread observed (per cycle) | derived from real `bid` and `ask` candle blocks |
| Avg spread EUR/USD (in cache) | 1.687 pips |
| Avg spread USD/JPY (in cache) | 1.935 pips |
| Slippage assumption | **NOT applied in V4.6** (no fills simulated — 0 ENTER_CANDIDATE) |
| Commission | **NOT applied** (no fills) |
| Risk per trade | **NOT applied** (no fills) |
| Position sizing | **NOT applied** (no fills) |

**Honest framing:** V4.6 measured the orchestrator's gate behaviour, not the P&L of executed trades. Because zero ENTER_CANDIDATEs were produced, no P&L could be computed. The P&L simulator (`replay/pnl_simulator.py`, built in Phase 8) requires ENTER_CANDIDATEs as inputs; it is therefore zero-tested for this run.

If a future architectural fix produces non-zero ENTER_CANDIDATEs, the simulator will compute net P&L using the real bid/ask spreads above + a documented slippage model.

---

## 13. Total Trades

**0** ENTER_CANDIDATE over 2 years × 2 pairs = 99,298 cycles, 517 trading days.

---

## 14. Win Rate

**Undefined** — no trades closed. Cannot compute wins/losses.

---

## 15. Net Profit

**$0.00** — no trades executed. No spread paid, no slippage paid.

---

## 16. Profit Factor

**Undefined** — gross_profit = $0, gross_loss = $0. 0/0.

---

## 17. Expectancy

**Undefined** — no trades.

---

## 18. Max Drawdown

**$0.00 (0.00%)** — equity curve is a flat line at $10,000 starting balance. No positions taken, no equity moved.

---

## 19. Consecutive Losses

**0** — no losses, no wins, no streaks.

---

## 20. Trades per Day

| Metric | Value |
|---|---|
| Total trades | 0 |
| Trading days observed | 517 |
| Trades / day | **0.000** |

**Target: ≥ 2 trades/day. Result: NOT MET.**

---

## 21. Days With 2+ Trades

**0** out of 517 days.

---

## 22. Days Below 2 Trades and Reasons

**517 / 517 days had < 2 trades** (specifically, all had 0 trades). Reasons (in-window cycles only):

| Block reason | Count | Share |
|---|---|---|
| `grade_below_threshold` | 24,721 | 99.62% |
| `incomplete_agreement` | 53 | 0.21% |
| `R7_unanimous_wait:WAIT` | 40 | 0.16% |
| `kill_flag_active` | 2 | 0.01% |
| **Total in-window** | **24,816** | 100% |

(75% of cycles outside the window are blocked by `outside_new_york_trading_window` — by design and not counted here.)

### What "grade_below_threshold" means

GateMind's strict 3/3 A/A+ rule: every brain must report grade `A` or `A+` to consider an entry. The breakdown of brain grades in-window:

| Grade | NewsMind | MarketMind | ChartMind |
|---|---|---|---|
| A+ | 0 | 0 | 9 |
| A | 24,434 | 845 | 86 |
| B | 0 | 11,455 | 11,671 |
| C | 0 | 6,204 | 6,738 |
| BLOCK | 382 | 6,312 | 6,312 |

NewsMind hit A in 98.5% of in-window cycles. MarketMind hit A in only 3.4% (845 / 24,816). ChartMind hit A or A+ in 0.4% (95 / 24,816).

For all-three-A-grade, the joint probability is ~3.4% × 0.4% = ~0.014%, predicting roughly 3 simultaneous A-grade cycles. Empirically: **95 actual all-three-A-grade cycles** in 2 years (the joint distribution is not independent — they correlate around clean trends).

### What "incomplete_agreement" means

The 53 incomplete_agreement cycles are precisely the ones where ChartMind issued a directional decision (BUY or SELL) while NewsMind and MarketMind said WAIT. Phase 9 finding §6: NewsMind by code never issues BUY/SELL; MarketMind issues BUY/SELL only when `trend_state == strong_up/down` AND grade A — those conditions did not co-occur in this 2-year window.

So the 55 directional-Chart cycles (§17) all hit the same wall: GateMind's `unanimous_buy/sell` rule cannot be satisfied if News and Market are constitutionally always WAIT.

This is **the architectural collision predicted by Phase 9 §6** — empirically confirmed over the full 2-year window.

---

## 23. EUR/USD Performance

| Metric | Value |
|---|---|
| Cycles | 49,649 |
| ENTER_CANDIDATE | 0 |
| Net profit | $0 |
| Win rate | n/a |
| Drawdown | $0 |

---

## 24. USD/JPY Performance

| Metric | Value |
|---|---|
| Cycles | 49,649 |
| ENTER_CANDIDATE | 0 |
| Net profit | $0 |
| Win rate | n/a |
| Drawdown | $0 |

---

## 25. Combined Performance

Same as 23/24 — both pairs at 0. Combined: 0 trades, $0 P&L, 0% drawdown.

---

## 26. PRE_OPEN (3–5 AM NY) Performance

| Metric | Value |
|---|---|
| Cycles in window | 8,272 |
| ENTER_CANDIDATE | 0 |
| Net profit | $0 |

---

## 27. MORNING (8 AM – 12 PM NY) Performance

| Metric | Value |
|---|---|
| Cycles in window | 16,544 |
| ENTER_CANDIDATE | 0 |
| Net profit | $0 |

---

## 28. Rejected Trades Analysis

A "REJECTED_TRADE" record is created only when GateMind evaluates 3 directional decisions (the rejected vs accepted distinction). Since the brains' contracts make it impossible for all three to be directional simultaneously, the official `REJECTED_TRADE` record count is **0**.

However, the 53 `incomplete_agreement` cycles can be interpreted as soft rejections — ChartMind WANTED to trade, the gate said NO. Below: the most informative subset, broken down by what ChartMind suggested:

| ChartMind suggestion | In-window count | All went to BLOCK with reason |
|---|---|---|
| BUY | 42 | `incomplete_agreement` (40) + `outside_new_york_trading_window` (2) |
| SELL | 13 | `incomplete_agreement` (13) |
| WAIT | 18,449 | various |
| BLOCK | 6,312 | brain block / data quality |

**Of 55 directional ChartMind cycles, 53 were blocked by `incomplete_agreement` and 2 fell outside the NY window.**

A "shadow simulator" would walk these 55 cycles forward 24 bars to compute hypothetical P&L. With v4.0's contract collision intact, the gate would have rejected all of them anyway — so building the shadow simulator is deferred until the architectural fix is applied.

---

## 29. GateMind Saved-vs-Lost Analysis

**Cannot be computed in v4.0** because no REJECTED_TRADE records exist. The saved-vs-lost framework depends on having genuine trade rejections to compare against shadow outcomes; the system's contract collision means no such rejections are produced. Once the v4.7 architectural fix lands (per V4.1, V4.3, V4.5 recommendations), this analysis becomes meaningful.

---

## 30. Mind-by-Mind Behaviour

### NewsMind (ReplayNewsMindV4 calendar-only proxy for v4.0)
- In-window cycles: 24,816
- A grade: 24,434 (98.5%)
- BLOCK grade: 382 (1.5% — when an event blackout window is active)
- BUY decisions: **0** ← this is the architectural choke point
- SELL decisions: **0**
- WAIT: 24,434
- BLOCK: 382

### MarketMind
- A grade: 845 (3.4%)
- B grade: 11,455 (46.2%)
- C grade: 6,204 (25.0%)
- BLOCK: 6,312 (25.4%)
- BUY: **0** ← `trend_state == strong_up/down` + grade A condition not co-occurred
- SELL: **0**
- WAIT: 18,504
- BLOCK: 6,312

### ChartMind
- A+: 9 cycles
- A: 86 cycles
- B: 11,671
- C: 6,738
- BLOCK: 6,312
- BUY: 42
- SELL: 13
- **Directional rate**: 55 / 24,816 ≈ 0.22% — the only mind that actually points at trades

### GateMind
- ENTER_CANDIDATE: 0
- BLOCK by `outside_NY_trading_window`: 74,482
- BLOCK by `grade_below_threshold`: 24,721
- BLOCK by `incomplete_agreement`: 53
- BLOCK by `kill_flag_active`: 2
- WAIT by `R7_unanimous_wait`: 40
- ORCHESTRATOR_ERROR: 0

GateMind worked exactly as written. It has no flaw. The flaw is upstream: the brains by contract cannot satisfy GateMind's unanimous-direction rule.

### SmartNoteBook
- Records written: ~198,596 (DECISION_CYCLE + GATE_AUDIT for every cycle)
- Chain hash: maintained (sandbox warning about HMAC key not set; not a security issue for replay)
- Silent failures: 0
- ORCHESTRATOR_ERROR records: 0

---

## 31. 150% Target Analysis

**Result: 0% achieved. 150% is mathematically unreachable in v4.0.**

To achieve a positive return we need trades. To get trades we need ENTER_CANDIDATEs. To get ENTER_CANDIDATEs we need the gate's `unanimous_buy/sell` rule satisfied. To satisfy that we need NewsMind to issue BUY/SELL. NewsMind's code (line 213 of NewsMindV4.py) hardcodes `decision = "WAIT"` even when permission is ENTER. The system therefore cannot trade. No risk parameter, no SL/TP combination, no position sizing tweak changes this outcome.

**150% target: NOT MET. Reason: architectural impossibility, not market difficulty.**

---

## 32. Required Risk for 150%

**N/A.** No risk model produces 150% from 0 trades.

---

## 33. Whether That Risk Is Acceptable

**N/A.** No risk was taken. Maximum drawdown 0%; equity curve flat.

---

## 34. Red Team Attacks (10 attacks)

| # | Attack | Result |
|---|---|---|
| 1 | Did any cycle see a future bar? | ✅ 99,298 checked, 0 lookahead-leak |
| 2 | Are there cycles after end_utc? | ✅ 0 |
| 3 | Did any error/exception slip through silently? | ✅ 0 errors, 0 ORCHESTRATOR_ERROR |
| 4 | Is any final_status outside vocab? | ✅ 0 out-of-vocab |
| 5 | Did any outside_window cycle become ENTER_CANDIDATE? | ✅ 0 |
| 6 | Did SmartNoteBook write fail silently? | ✅ 0 silent failures |
| 7 | Did any ENTER escape gate without unanimous direction? | ✅ 0 escapes (vacuously — 0 ENTER) |
| 8 | Per-pair fairness — did one pair get 0 cycles? | ✅ Both pairs received 49,649 each |
| 9 | Did ChartMind directional cycle become ENTER bypassing the gate? | ✅ 0 bypasses (53 directionals → all `incomplete_agreement` BLOCK) |
| 10 | Sample mixed-grade cycles to confirm GateMind blocked correctly | ✅ 5/5 samples show News=A/Market=A/Chart=B → correctly BLOCKED `grade_below_threshold` |

**10 / 10 PASSED.** Replay integrity is empirically verified.

---

## 35. Red Team Results

**No exploit found.** The replay is honest: no lookahead, no silent failures, no gate bypasses, no missing brains, no ENTER without unanimity. Every record is consistent with the architectural truth: zero trades over two years on this exact pipeline.

---

## 36. Fixes Applied

**None.** V4.6 was strictly verification. Zero code changes anywhere.

---

## 37. Regression Tests Added

**None new.** The integrity properties verified by Red Team are already covered by existing tests:
- No-lookahead: `replay/tests/test_replay_no_lookahead.py`, `marketmind/v4/tests/test_no_lookahead.py`, `chartmind/v4/tests/test_no_lookahead.py`
- Gate cannot be bypassed: `orchestrator/v4/tests/test_no_override_gate.py` (4/4 pass)
- SmartNoteBook records every cycle: `orchestrator/v4/tests/test_smartnotebook_recording.py` (6/6 pass)
- Outside-window blocks: `orchestrator/v4/tests/test_ny_session.py` (5/5 pass) + `gatemind/v4/tests/test_session_check.py`
- No live order during replay: `orchestrator/v4/tests/test_no_live_order.py` (13/13 pass) + `live_data/tests/test_live_order_guard.py`

---

## 38. Remaining Limitations

| # | Limitation | Severity | Required for V4.7 |
|---|---|---|---|
| L1 | NewsMind decision contract vs GateMind unanimous-direction rule (Phase 9 §6) — the system architecturally cannot trade | **CRITICAL** | yes |
| L2 | P&L simulator (`replay/pnl_simulator.py`) is built but zero-tested because no ENTER_CANDIDATEs exist to feed it | HIGH | required after L1 fix |
| L3 | No off-laptop git remote | HIGH | recommended |
| L4 | `API_KEYS/ALL KEYS AND TOKENS.txt` still inside project tree (gitignored after V4.2) | LOW | move out |
| L5 | 5 pre-existing test-fixture failures in anthropic_bridge tests (V4.2 finding) | LOW | optional |

---

## 39. V4.6 Closure Decision

| Closure requirement | Status |
|---|---|
| Replay run on EUR/USD | ✅ 49,649 cycles |
| Replay run on USD/JPY | ✅ 49,649 cycles |
| Five minds executed in chain | ✅ §8 + §30 |
| No lookahead | ✅ Red Team Attack 1, 2 |
| No data leakage | ✅ Red Team verification |
| GateMind rules enforced | ✅ §17 + Red Team Attack 9, 10 |
| SmartNoteBook records every cycle | ✅ §10 |
| No live execution | ✅ §11 |
| Costs / drawdown documented | ✅ §12, §18 (both at 0 because no fills — honest framing) |
| Rejected trades analysed | ✅ §28 (53 `incomplete_agreement` cycles tracked) |
| 2 trades/day measured honestly | ✅ §20 — 0.000/day, NOT MET |
| 150% measured honestly | ✅ §31 — 0%, NOT MET |
| Red Team executed | ✅ 10 attacks |
| Red Team breaks fixed or documented | ✅ 0 breaks |
| Regression tests added | ✅ no new tests needed; existing suite covers integrity |
| Report in English | ✅ this file |
| Git status clear | ⚠️ no V4.6 changes (verification only) |
| Decision: V4.7 or not | see below |

### **VERDICT: ✅ V4.6 COMPLETE.**

The 2-year replay on real data ran end-to-end. The numbers are real, sourced from 99,298 line-by-line records on disk. The result confirms the Phase 9 architectural finding empirically over the full 2-year window: **0 trades, 0% return, by structural impossibility**. The gate, the brains, the data pipeline, and SmartNoteBook all worked correctly — the failure mode is upstream of the gate, in the news-brain decision contract.

---

## 40. Move to V4.7?

**RECOMMENDED: YES.**

V4.7 must address the architectural collision (L1):

**Option A (recommended) — Change GateMind consensus rule:**
- Modify `gatemind/v4/consensus_check.py` so `unanimous_buy = ChartMind=BUY AND News≠BLOCK AND Market≠BLOCK AND News≠OPPOSING_DIRECTION AND Market≠OPPOSING_DIRECTION`. Treat News and Market as VETO voters, not directional voters.
- Re-run the same 2-year replay. Expected outcome: 50–500 ENTER_CANDIDATEs over 2 years (rough estimate from the 55 ChartMind-directional cycles + similar setups that don't currently survive Market grade=A).
- Run P&L simulator on the new ENTER_CANDIDATEs. Honest win rate, drawdown, profit factor.

**Option B — Change NewsMind decision contract:**
- Modify `newsmind/v4/NewsMindV4.py:212–216` to emit BUY/SELL when permission is ENTER and a directional bias exists. Larger blast radius (re-grade ~50 NewsMind tests).
- Same downstream re-run.

After V4.7 produces non-zero trades + honest numbers, V4.8 wraps `Run_HYDRA_V5.bat`, V4.9 consolidates documentation, and the V5 carve-out becomes legitimate.

**Do not touch V5 until V4.7's architectural fix produces a non-zero-trade backtest at acceptable risk.**

---

## 41. Honest Bottom Line

The user's V4.6 mandate was: *"الباكتيست الحقيقي ليس لإثبات أننا ناجحون. الباكتيست الحقيقي لإثبات أننا لا نخدع أنفسنا."* (The real backtest is not to prove we succeed; it is to prove we don't deceive ourselves.)

After V4.6:
- The replay is **real**: 99,298 cycles, sandbox-runnable, line-by-line auditable.
- The pipeline is **honest**: zero lookahead, zero silent failures, zero hidden errors.
- The architecture is **transparent**: every block reason is recorded; the chokepoint is documented at `newsmind/v4/NewsMindV4.py:212–216` and `gatemind/v4/consensus_check.py`.
- The result is **uncomfortable**: 0 trades, 0% return, 0 days with ≥ 2 trades.

The user's targets — 2 trades/day and 150% return — are not met by v4.0. They cannot be met by v4.0 because of the architectural collision. They MAY be reachable by v4.7 once the contract is reconciled. The honest answer is: we'll know in V4.7, not before.

The system did not deceive us. It told the truth.
