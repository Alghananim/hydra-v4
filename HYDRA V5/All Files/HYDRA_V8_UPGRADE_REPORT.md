# HYDRA V8 — ATR-Relative SL/TP in Shadow Simulator

**Theme:** Re-evaluate the SAME V5.0 trades with different SL/TP levels.

## 1. Why this isn't a brain change

V5.0 measured 7 of 13 trades as TIMEOUT. The trades didn't lose; they just didn't reach the +40-pip TP within 6 hours. That's symptomatic of TP being too far for M15 volatility.

The brains' decisions weren't wrong. The yardstick was wrong.

V8 changes only `replay/war_room/shadow_pnl.py` parameters: SL=12p (≈0.75×ATR), TP=18p (≈1.5×ATR), max-hold=16 bars (4h). Same 13 trades, different exits.

## 2. Hypothesis

V5.0's 13 ENTER trades, re-simulated with V8 levels, achieve:
- Most timeouts → wins (TP closer)
- Slightly more SL hits (SL also closer)
- Net pips significantly higher because the move that previously timed out at +30 pips now banks at +18.

## 3. Risk

Tighter SL gets hit by noise on M15. If SL hits go from 5/13 to 8/13, net pips falls.

## 4. Code

`replay/variants/v8_atr_relative_sltp.py`. Patches `shadow_pnl.SL_PIPS / TP_PIPS / MAX_HOLD_BARS` for one run. Reverts on exit.

## 5. Decision criteria

**APPROVED if:**
- Win rate (excl timeout) > 35 %
- Timeout rate < 30 %
- Net pips > V5.0 baseline (-58.7)
- Red Team 8/8

## 6. What V8 tells us regardless of approval

If V8 turns V5.0's losing 13 trades into winning trades just by changing exit levels, that's a strong signal: the brains were RIGHT but the strategy's exit logic was wrong. The fix is small.

If V8 doesn't help (timeout rate stays high), the trades didn't have any edge and the brains' decisions are the issue. The fix is bigger.

## 7. Composition

V8 is orthogonal to V5.2-V7 — they change which trades fire; V8 changes how exits work. V10 composes the best of both.
