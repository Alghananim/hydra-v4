# HYDRA V6 — Per-Pair Calibration

**Theme:** Different threshold for each currency pair. EUR/USD lenient, USD/JPY strict.

## 1. Why per-pair

V5.0 measured: USD/JPY = 0 wins / 8 trades, EUR/USD = 1 win / 5 trades. The two pairs behave differently:

- USD/JPY's pip value is ~$1.0 per 0.01 yen on a standard lot — different sensitivity to news vs EUR/USD's $10 per pip.
- USD/JPY ATR on M15 ~10 pips, EUR/USD ATR ~7 pips — JPY tends to move further per bar.
- USD/JPY is more news-driven (BoJ + JGB yields + carry trade), EUR/USD more flow-driven (US-EU data + sentiment).

Applying the same threshold to both was the V5.0 mistake. V6 fixes that.

## 2. Hypothesis

USD/JPY needs A ≥ 6 evidence flags (stricter); EUR/USD stays at A ≥ 5. This should:
- Reduce USD/JPY trades, hopefully eliminating the worst losers.
- Leave EUR/USD trades unchanged.

## 3. Risk

If USD/JPY has near-zero ENTER under stricter rule, the system loses half its instrument coverage. EUR/USD alone may not sustain 2 trades/day.

## 4. Code

`replay/variants/v6_per_pair_calibration.py`. Patches `ChartMindV4.evaluate` to switch thresholds based on `pair` argument. Reverts on exit.

## 5. Decision criteria

**APPROVED if:**
- USD/JPY net pips ≥ 0 (no longer the loss source)
- EUR/USD net pips not below V5.0 baseline
- Red Team 8/8
- ENTER count not below 25 (to keep instrument coverage meaningful)

**REJECTED if:**
- USD/JPY ENTER drops to 0 (over-stricted)
- EUR/USD regresses (the patch leaked)

## 6. What if V6 also fails?

If USD/JPY has no profitable threshold combination at all, the honest answer is to **drop USD/JPY** and trade EUR/USD only. V6 reports this clearly in its comparison table; the user decides.

## 7. Composition with V5.x

V6 is independent of V5.2-V5.5 changes — it's per-pair, they're per-flag. They compose cleanly. V10 will combine them if both promotable.
