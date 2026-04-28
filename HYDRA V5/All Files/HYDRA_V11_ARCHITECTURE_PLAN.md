# HYDRA V11 — Architectural Redesign Plan

**Status:** Approved for design after V5/V10 calibration tree exhausted. Honest premise: **2 trades/day on M15 + 2 pairs is mathematically impossible**. V11 changes the math.

---

## 1. The math problem V11 must solve

### V5.0 measured (the truth)

```
99,298 cycle backtest (2 years × 2 pairs × M15)
ENTER candidates:    53
in-window cycles:    25,000  (25% of timeline by design)
ENTER rate:          53 / 25,000 = 0.21% per in-window cycle
trades / day:        53 / 730 = 0.073
```

### V5 calibration ceiling (best case stacking V5.4 + V5.6 + V8)

```
ENTER ceiling:       ~400 (loosen all gates that aren't dangerous)
trades / day:        ~0.55
```

### V11 target

```
trades / day:        ≥ 1.5  (revised honest target; 2/day is hard)
profit:              +500 to +1500 pips / year
win rate:            ≥ 40 % (excl timeout)
drawdown / net:      < 0.6
```

## 2. What V11 changes vs V5

V11 is **NOT** another calibration tweak. It's a structural redesign:

| Dimension | V5 | V11 | Multiplier |
|---|---|---|---|
| Timeframe | M15 | **M5** | × 3 (more bars per day) |
| Pairs | 2 (EUR/USD, USD/JPY) | **6** (add GBP/USD, USD/CAD, AUD/USD, EUR/JPY) | × 3 |
| Trading windows | NY 03-05 + 08-12 (6h) | **London-NY overlap, Asian open, NY close** (10h) | × 1.67 |
| ChartMind setups | breakout/retest/pullback only | **add inside-bar, range-break, mean-reversion** | × 2-3 |
| Multi-timeframe | M5/M1 (unused) | **M5 entry, M15 trend, H1 bias** (real pipeline) | quality |
| Per-pair calibration | none | **per-pair thresholds and SL/TP scaling** | risk-aware |

Combined cycle count multiplier: **3 × 3 = 9x more cycles**. From 99k to ~900k cycles in same 2-year window.

If the per-cycle ENTER rate stays at 0.21% (no logic improvement): 900k × 0.0021 = **1,890 trades / 730 days = 2.6 / day**. The math works.

## 3. V11 module breakdown

### V11.1 — M5 data pipeline
- New OANDA fetcher for M5 bars on all 6 pairs.
- ~1.5M bars total over 2 years × 6 pairs = ~750 MB cached. Use Git LFS.
- M5 cache scripts: same pattern as M15 cache.

### V11.2 — Instrument expansion
- Add 4 pairs: GBP/USD, USD/CAD, AUD/USD, EUR/JPY.
- Per-pair calibration table: ATR scale, typical spread, SL/TP geometry.
- Update `chartmind/v4/chart_thresholds.py` to read per-pair config.

### V11.3 — Multi-timeframe pipeline
- Real M5 entry + M15 trend + H1 bias.
- `multi_timeframe.assess` with all three actually populated.
- F-015 closed.

### V11.4 — Setup detector additions
- Inside-bar breakout (often missed by current breakout_detector — small consolidation followed by directional bar).
- Range-break (different from breakout: ranges have two boundaries).
- Mean-reversion at S/R (counter-trend at strong levels).

### V11.5 — Trading window expansion
- Add Asian open: 00:00-02:00 UTC (high JPY pair activity).
- Add London open: 07:00-08:00 UTC (high EUR/GBP pair activity).
- Add NY close: 19:00-21:00 UTC (USD pair activity).
- Total: ~10h/day window.

### V11.6 — Per-pair risk + SL/TP
- USD/JPY: 12-pip SL / 18-pip TP (R:R 1.5)
- EUR/USD: 8-pip SL / 16-pip TP (R:R 2.0)
- GBP/USD: 12-pip SL / 24-pip TP (R:R 2.0)
- USD/CAD: 10-pip SL / 18-pip TP (R:R 1.8)
- AUD/USD: 8-pip SL / 14-pip TP (R:R 1.75)
- EUR/JPY: 14-pip SL / 24-pip TP (R:R 1.7)

Each pair has its own SL/TP based on M5 ATR.

### V11.7 — V11 War Room & Red Team
- Same 8 probes as V5 (no lookahead, costs deducted, segmented, per-pair, per-window, drawdown floor, looser modes don't explode DD).
- New probe: **per-instrument robustness** — every pair must individually be ≥ 0 net pips.
- New probe: **per-window robustness** — each of 4 trading windows individually ≥ 0.

## 4. V11 development plan (4 weeks)

| Week | Deliverable | Test |
|---|---|---|
| 1 | M5 data pipeline + 4 new pair caches | Backtest runs on M5 data without errors |
| 2 | ChartMind setup detector additions + MTF wiring | All chartmind tests pass; no behaviour drift on M15 |
| 3 | Per-pair calibration + window expansion | First V11 backtest produces ≥ 500 ENTER candidates |
| 4 | War Room V11 + Red Team + V11 final report | Promotable variant identified, or honest rejection |

## 5. V11 → V12 if V11 doesn't reach target

If V11 produces ≥ 0.7 trades/day BUT ≤ 1.5: that's still 4-10x V5.0. Acceptable as MVP for live paper.

If V11 fails to clear Red Team (per-pair regression somewhere): V12 considers:
- Different broker/instruments (CFD on indices, commodities)
- Different strategy class (mean-reversion, statistical arb)
- Different timeframe (M1 — but data volume becomes huge)

## 6. What V11 keeps from V5

- V4.7 architectural fix (ChartMind directional voice + News/Market vetoers).
- 16-condition live safety guard.
- LIVE_ORDER_GUARD + dry-run + per-day token + kill-switch.
- HMAC chain SmartNoteBook.
- War Room toolkit (extended).
- Iteration protocol.
- Red Team pattern.

V11 inherits everything that worked in V5 and changes only the things measurement showed are insufficient.

## 7. Honest framing

V5 produced a profitable but slow system: 0.07 trades/day with 40 % win rate and +103 pips over 2 years on the small sample.

V11's job is to **scale that profitability** through more opportunities, not to invent a new strategy.

If V11 succeeds: 1.5 trades/day × 40 % win × 1.5 R:R × ~70 pips/year/trade gross → ~150-300 pips/year net per pair × 6 pairs ≈ 900-1800 pips/year. That's roughly 9 % - 18 % return at 1 % risk per trade. Not 150 %, but **realistic and positive**.

The 150 % target requires either much higher leverage (dangerous) or a fundamentally different strategy class (out of V11 scope, V12+).

---

## Decision

**V11 starts now.** No more V5 calibration. The data has spoken — V5's logic is sound but its surface area is too small.

Next concrete step: design + implement V11.1 (M5 data pipeline) on disk. When user clicks deploy, V11 begins iterating in cloud the same way V5 did.
