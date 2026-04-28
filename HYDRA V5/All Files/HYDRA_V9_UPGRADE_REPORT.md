# HYDRA V9 — Pre-Final Hardening

**Theme:** No behaviour change. Production-readiness pass.

## 1. What V9 adds

V9 is the LAST variant before V10. It guarantees no regression and sets up for production with:

- Per-cycle latency timing (orchestrator, plus per-brain).
- NaN guards on all indicator outputs.
- Negative-ATR / absurd-value guards.
- Mutation guards on bars list.
- Explicit assertion logging in failure paths.

## 2. The single sentinel test

V9 must produce **exactly the same** numbers as its baseline (whichever variant V5.2-V8 was approved). Any non-zero delta = regression. The variant runner verifies this automatically.

## 3. What V9 sets up for V10

V10 composes the approved V5.x-V8 changes plus V9's hardening. V9's "no drift" guarantee means V10's behaviour is fully predictable.

## 4. Code

`replay/variants/v9_hardening.py` — currently a no-op stub. The hardening lives in source files committed alongside V9 (latency wrappers, NaN asserts).

## 5. Decision criteria

**APPROVED if:** ENTER count exactly equal to baseline AND Red Team probes all still pass.

**REJECTED if:** any drift.
