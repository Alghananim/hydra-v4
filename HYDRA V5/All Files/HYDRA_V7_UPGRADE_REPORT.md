# HYDRA V7 — MTF Alignment as Hard Gate

**Theme:** Change one of 8 evidence flags from "scoreable" to "required".

## 1. Why MTF as hard gate

Multi-timeframe alignment is the strongest single predictor of M15 follow-through in most institutional literature. V5.0 treated `mtf_aligned` as one evidence flag of 8. V7 makes it required: if M15 disagrees with H1, no entry — regardless of how many other flags fire.

## 2. Hypothesis

V7 trades fewer cycles but trades better ones. Win rate up, net pips up, drawdown down.

## 3. Risk

If MTF misaligned in > 70 % of in-window cycles, V7 reduces ENTER count to near zero and the system is structurally non-viable on M15.

## 4. Code

`replay/variants/v7_require_mtf.py`. Patches `permission_engine.decide` to cap the grade at B when `mtf_aligned == False`. Reverts on exit.

## 5. Decision criteria

**APPROVED if:**
- Win rate > 50 % (this is the primary metric for V7)
- ENTER ≥ 50 (modest — V7 trades quality not quantity)
- Net pips > V5.0 baseline
- Red Team 8/8

**REJECTED if:**
- ENTER < 20 (system non-viable)
- Win rate not above 35 % (the gate didn't filter enough noise)

## 6. Composition with prior versions

V7 stacks well with V5.4 (lower a-min) — together they create "lots of trades, but only when MTF agrees". This composition is in V10's plan.
