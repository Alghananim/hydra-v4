# HYDRA V10 — Final System Report

**Status:** Awaiting empirical evidence from V5.2-V9 variant runs. V10 is constructed dynamically by `replay/variants/v10_final.py::apply()` based on which prior variants were promotable.

## 1. The honest decision tree

V10 is **NOT** a fixed configuration. It is a **decision rule** applied to V5.2-V9 results:

```
For each variant V in [V5.2, V5.3, V5.4, V5.5, V6, V7, V8]:
    if V satisfies promotion_criteria:
        V10 incorporates V's change
    else:
        V's change is rejected, NOT in V10

V9 hardening is always included.

If NO variant is promotable:
    V10 = V5.0 baseline + V9 hardening only
    Verdict: "Calibration alone cannot fix V5.0; ChartMind redesign
              required outside V10 scope."
```

## 2. The four possible V10 outcomes

| Outcome | When | What V10 looks like |
|---|---|---|
| **STRONG V10** | Multiple V5.x-V8 promotable, compose well | V10 = V5.4 + V8 + V9 (typical) |
| **MODERATE V10** | One V5.x or V8 promotable | V10 = V5.X + V9 |
| **NARROW V10** | Only V8 promotable | V10 = V5.0 logic + V8 exit levels |
| **NONE V10** | Nothing promotable | V10 = V5.0 + V9 hardening; V11 redesigns ChartMind |

## 3. The V10 acceptance criteria (mandatory)

V10, whatever its composition, must clear all of:

- `replay_runs/v10_final/state.json::counters.ENTER_CANDIDATE > 53` (better than V5.0)
- `shadow_pnl.json::summary_by_mode.shadow_2_of_3.win_rate_excl_timeout >= 35 %`
- `shadow_pnl.json::summary_by_mode.shadow_2_of_3.net_pips_after_cost > 0`
- `shadow_pnl.json::summary_by_mode.shadow_2_of_3.max_drawdown_pips / net_pips_after_cost in absolute < 0.6`
- `red_team.json::passed >= 8`
- `gatemind/v4/tests`: 143/143 pass
- Per-pair: EUR/USD net pips > 0 AND USD/JPY net pips ≥ 0

If any criterion fails, V10 is **REJECTED** and the report's final line reads:

```
HYDRA V10 status: REJECTED — calibration tree exhausted; ChartMind redesign
required for any future improvement. Live trading remains DISABLED.
```

If all pass, the final line reads:

```
HYDRA V10 status: APPROVED for paper-trading observation period (30 days
on practice OANDA account). Live capital deployment requires user
explicit approval after observation.
```

## 4. What V10 still does NOT promise

- Cannot promise 2 trades / day. The data may genuinely show this is unreachable.
- Cannot promise 150 % return. Net pips are the honest measure.
- Cannot promise live execution. V10 is an offline system; live requires the writer client and a user-driven arming + token flow per session.

## 5. Future work after V10

- **V11:** ChartMind setup-detector redesign (NOT calibration). New entry logic based on what the V5.1 chartmind_scores.csv revealed about why setups fail.
- **V12:** Multi-timeframe strategy redesign (e.g. M15 entries triggered by H1 S/R reactions).
- **V13:** Instrument set redesign (drop USD/JPY, add EUR/GBP or USD/CAD with different volatility profiles).

V10 does not commit to any of these. It states them as the obvious next research questions.
