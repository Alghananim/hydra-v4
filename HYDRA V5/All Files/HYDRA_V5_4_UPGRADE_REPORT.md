# HYDRA V5.4 — Lower Grade-A Minimum from 5/8 to 4/8

**Theme:** The big single knob.

## 1. The motivation

V5.0 diagnostics showed:
- ChartMind grade B: 6,716 cycles (these are score 3-4)
- ChartMind grade A: 60 cycles
- Loosening grade A from "score ≥ 5" to "score ≥ 4" promotes ALL score-4 cycles to A.

If even 30% of those 6,716 cycles produce winning trades, this is a 30× scale-up of profitable trades — the dominant lever in the system.

## 2. Hypothesis

Lowering grade A from score ≥ 5 to score ≥ 4 unlocks ~5,500 additional candidates with comparable win rate. If win rate at score 4 is similar to score 5, this is a strict improvement.

## 3. The risk in plain language

If score-4 setups have systematically WORSE win rate than score-5 setups (as one would naively expect), we add many losers and net pips worsens. The shadow simulator answers definitively.

## 4. Code

`replay/variants/v5_4_lower_a_min.py`. Sets `chart_thresholds.GRADE_A_MIN_EVIDENCE = 4` for the duration of one backtest. Reverts on exit.

## 5. Decision criteria (strict because this is the biggest knob)

**APPROVED if:**
- ENTER > 200 (significant scale-up)
- Win rate (excl timeout) ≥ 30 %
- Net pips after cost > 0
- Drawdown / net pips ratio < 0.6
- Red Team 8/8

**REJECTED if:** any of the above fails.

## 6. Why this might be the answer

The original V3 system used a 12-AND chain — statistically unreachable. V5.0 uses 5/8 — barely reachable (60 of 22k cycles). V5.4 uses 4/8 — reachable enough to be useful but still strict.

There's a sweet spot in evidence strictness. The honest test is whether 4/8 is in that sweet spot.

## 7. Why this might NOT be the answer

Looking at V5.0's own data: the 13 trades that DID fire were all at grade A or A+. They had win rate 16.7 %. So even at the strict end, the underlying trades aren't winning. Loosening to grade B would in the worst case make the win rate WORSE.

The deciding factor: V5.1's chartmind_scores.csv will tell us if score 4 cycles tend to have OTHER missing flags that are correlated with losses. If yes, V5.4 produces bad trades. If the missing flags are independent of outcome, V5.4 is fine.

## 8. Decision tree

```
V5.4 ENTER > 200 AND net pips > V5.0?
├── YES → and Red Team 8/8 → APPROVED, contributes to V10
├── YES → but Red Team fails (probably P5 per-pair) → REJECTED, V5.5 tries
├── NO  → and ENTER very high but net pips negative → REJECTED, going looser hurts
└── NO  → ENTER barely changes → V5.4 lever is dead, V6 redesigns instead
```
