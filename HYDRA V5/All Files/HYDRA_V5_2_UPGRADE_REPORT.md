# HYDRA V5.2 — Drop `volatility_normal` Evidence Flag

**Theme:** Single-knob calibration. Drop one of the 8 evidence flags.

## 1. What was weak in V5.1

V5.0 measured 53 ENTER over 99,298 cycles, win rate 16.7 %. ChartMind grade A requires 5 of 8 evidence flags simultaneously. The `volatility_normal` flag requires ATR percentile ∈ (25, 80) — by construction it excludes ~45 % of M15 bars.

## 2. Research

`chart_thresholds.VOL_COMPRESSED_PCT_MAX = 25.0` and `VOL_EXPANDED_PCT_MIN = 80.0` are stationary thresholds, not regime-aware. On EUR/USD M15 the ATR-percentile distribution is approximately uniform; on USD/JPY it's slightly skewed expanded. Either way, the flag rejects nearly half the cycles for a reason that's not directly tied to setup quality.

## 3. Agent debate

- **Performance Agent:** dropping the flag should raise ENTER count by ~30–60 % at cost of unknown win-rate change.
- **Risk Agent:** trading in compressed volatility is the riskier branch — sudden expansions can hit SL fast.
- **Red Team:** P5 (per-pair) is the canary — if USD/JPY worsens further, V5.2 is rejected.

## 4. Diagnosis

`volatility_normal` is the most likely lever to test FIRST because it's the cheapest to revert and the most binary.

## 5. Hypothesis

Removing `volatility_normal` will increase ENTER count without materially worsening win rate.

## 6. Build

`replay/variants/v5_2_drop_volatility_normal.py` — monkey-patches `chart_thresholds.EVIDENCE_KEYS` to drop the flag. Reverts on exit. No on-disk change to source.

## 7. Tests

- gatemind/v4 unit tests: 143/143 pass (no chart_thresholds change in tests).
- chartmind/v4 unit tests: should pass (the EVIDENCE_KEYS list constant changes; verify in CI).
- Cloud variant backtest: produced by the matrix workflow.

## 8. Red Team

8 probes, automatic via `replay/war_room/red_team.py`. Required: 8/8 pass. Pre-evaluation:

- P3 (spread): unaffected.
- P4 (segmented): must hold.
- P5 (per-pair): the variant could bias results to one pair — must check.
- P7 (drawdown floor): the looser variant could increase DD — must check.

## 9. Compare (filled by runner)

| Metric | V5.0 | V5.2 | Δ | Verdict |
|---|---:|---:|---:|---|
| ENTER | 53 | (TBD) | TBD | TBD |
| WAIT | 40 | (TBD) | TBD | TBD |
| Win rate | 16.7 % | (TBD) | TBD | TBD |
| Net pips | -58.7 | (TBD) | TBD | TBD |
| Max DD | -97.2 | (TBD) | TBD | TBD |
| EUR/USD net | +16.8 | (TBD) | TBD | TBD |
| USD/JPY net | -75.5 | (TBD) | TBD | TBD |

## 10. Decision criteria

**APPROVED if:** ENTER > 53 AND win rate ≥ 30 % AND USD/JPY net pips ≥ -75.5 (no further regression) AND Red Team 8/8.

**REJECTED if:** any of the above fails.

## 11. Next

If APPROVED → V5.2 contributes its change to V10. If REJECTED → flag is structurally needed; V5.3 tests a different flag.
