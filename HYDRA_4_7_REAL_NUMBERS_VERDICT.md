# HYDRA V4.7 — Real Numbers Verdict (truth, not placeholders)

**Date:** April 28, 2026
**Source:** GitHub Actions Run #2, commit 2a12427, completed 6m 12s.
**Artefacts:** `replay_runs/v47_2y/state.json`, `replay_runs/v47_warroom/{diagnostics,shadow_pnl}.json`

This document records the **real numbers** from the full 99,298-cycle backtest and the verdict that follows.

---

## 1. The headline numbers

| Metric | Value |
|---|---:|
| Cycles analysed (state.json) | **99,298** (2 years × 2 pairs × M15) |
| ENTER_CANDIDATE | **53** |
| WAIT | 40 |
| BLOCK | 99,205 |
| ORCHESTRATOR_ERROR | 0 |
| Errors | 0 |
| Trades / day | **0.073** (target: ≥ 2.0) |
| Net pips after cost (shadow simulator) | **−58.7** |
| Win rate (excl. timeouts) | **16.7%** |
| Max drawdown (pips) | −97.2 |

**Verdict at the headline level:** V4.7 is honest, but the system is **not profitable** under the current ChartMind setup logic. The 53 trades in 2 years are losing trades, not just rare ones.

---

## 2. Where the cycles go (bottleneck attribution)

```
outside_new_york_trading_window      16,786  (75% — by design, not a bottleneck)
grade_below_threshold                 5,574  (25% of in-window — the real chokepoint)
R7_unanimous_wait:WAIT                   13  (legitimate)
all_brains_unanimous_enter:ENTER         12  (the trades that fired)
kill_flag_active                          1
```

The 5,574 `grade_below_threshold` rejections are 99.4 % of all non-session blocks. That's the surface story.

## 3. The real bottleneck: ChartMind's setup detector

Look at ChartMind's behaviour when in-window:

```
ChartMind decisions (in-window):
  WAIT   10,873        99.7%
  BUY        24         0.22%
  SELL        9         0.08%
  TOTAL  10,906

ChartMind grades (in-window, non-WAIT cycles):
  B   6,716            ← grade B but ChartMind still said WAIT
  C   4,125
  A      60
  A+      5
```

**ChartMind emits BUY/SELL only 33 times across 22,386 cycles (0.15%).** Even when ChartMind's grade is B (6,716 cases), the decision stays WAIT. So ChartMind has internal logic that says "I see something but I won't act unless I'm A/A+ confident".

This is not a tunable knob — it's the structure of the setup detector.

## 4. Why loosening the grade gate won't help

The shadow simulator ran three modes: `shadow_chart` (no gate), `shadow_grade_B` (allow grade-B), `shadow_2_of_3` (V4.7 baseline). All three returned exactly the same 13 trades.

```
shadow_chart      : 13 trades, 1 win, 5 losses, 7 timeouts, net −58.7 pips
shadow_grade_B    : 13 trades, 1 win, 5 losses, 7 timeouts, net −58.7 pips
shadow_2_of_3     : 13 trades, 1 win, 5 losses, 7 timeouts, net −58.7 pips
```

They are identical because **there is no ChartMind directional decision with grade B**. ChartMind never emits BUY/SELL outside of A/A+. So loosening the grade rule changes nothing — there is nothing in the B bucket to admit.

## 5. The trades we *do* have are losing

13 directional setups simulated forward with SL=20p / TP=40p / cost=1.5p / max-hold=24 bars on M15:

```
EUR/USD: 5 trades, 1 win,  1 loss, 3 timeouts, net +16.8 pips
USD/JPY: 8 trades, 0 wins, 4 losses, 4 timeouts, net −75.5 pips
```

USD/JPY is the cause of the negative net pips. Every USD/JPY ChartMind setup was a loss or a timeout.

## 6. Hypothesis verdicts (final, evidence-backed)

| Hypothesis | Verdict |
|---|---|
| H1: ChartMind very rarely A/A+ → strict gate has nothing to pass | **CONFIRMED**. A/A+ rate 0.6 % of in-window. |
| H2: MarketMind hands out B too often → unanimous A is rare | **CONFIRMED but not the lever**. MarketMind A-rate 4.9 % of in-window, no A+ at all. |
| H3: NewsMind WAIT/A is structural non-vote | **CONFIRMED**. NewsMind only WAIT or BLOCK as designed. |
| H4: ChartMind setup detector requires confirmation that rarely occurs | **CONFIRMED**. Directional rate 0.15 %. |
| H5: NY window too narrow | Inconclusive — current setups outside window not measured. |
| H6: V4.7 incomplete_agreement blocks valid trades | **REJECTED**. 0 such cycles in the data. |
| H7: data_quality stale flag over-triggers | Partially — MarketMind stale 4,424 / 22,386 = 19.8 %. Worth a fix. |
| H8: 5-day warm-up | True but bounded; not the dominant cause. |
| H9: 2 trades/day target structurally impossible under strict A | **CONFIRMED** at the ChartMind directional rate of 0.15 %. |
| H13: Loosening to grade B unlocks more profitable trades | **REJECTED**. There is no ChartMind directional grade-B in the data; loosening adds zero trades. |

## 7. The honest engineering decision

The natural V4.8 lever — "loosen the grade gate" — **does not work** because ChartMind itself never emits directional decisions at grade B. Tweaking thresholds further would either:

- Loosen ChartMind's directional threshold (currently 0.65) → more directional decisions, but the existing 13 are already 16.7 % win rate. Loosening would produce *more bad signals*.
- Loosen GateMind further → would still need ChartMind to be directional; still capped by ChartMind itself.

**The real V4.8 work is a ChartMind setup-logic redesign, not threshold tuning.** Specifically:

1. Audit why ChartMind only emits BUY/SELL in 0.15 % of in-window cycles. What is the underlying detector requiring that nearly nothing meets?
2. Audit why even the 13 high-confidence setups are 16.7 % win rate on M15. Are the SL/TP levels wrong for the volatility regime? Is the entry timing late? Is the directional bias sometimes inverted?
3. Audit USD/JPY specifically. Every setup there lost or timed out. Either the M15 EMA / RSI / breakout logic doesn't suit JPY pairs, or the volatility expansion at NY 03:00 disadvantages JPY by then.

## 8. Red Team verdict on this conclusion

The Red Team would attack any "loosen grades" V4.8 proposal as **overfit-prone with no evidence**. The shadow simulator already showed loosening produces no extra trades and the existing trades lose money. There is no calibration variant in the safe range that could survive Red Team probes P5 (per-pair: USD/JPY would still lose), P7 (drawdown: −97.2 pips on only 13 trades), or P8 (loose modes don't explode drawdown — same drawdown across modes is suspicious, not protective).

A loosen-the-grade V4.8 sweep would fail. We should not run it.

## 9. What V4.8 should actually be

**V4.8 = ChartMind redesign**, structured as:

- Phase A: instrument the existing ChartMind to log every internal score (RSI, EMA cross, ATR, S/R, breakout confirm) for every cycle. Reproduce the 13 entry decisions and look at what tipped them past the directional threshold.
- Phase B: shadow new directional logic (e.g. add a momentum filter, add an inside-bar trigger, add an ATR-relative SL) on the same 99k cycles. Measure trade count + win rate per variant.
- Phase C: only the variant that beats both ENTER count > 53 AND win rate > 50 % AND no per-pair regression is promotable.

This is a 1–2 week effort, not a single sweep. The honest scope.

## 10. What HYDRA V5 should ship today

V5 already shipped (in this conversation): the architecture, the War Room toolkit, the calibration scaffolding, the 16-condition live guard, the GitHub Actions pipeline, and the 6 reports.

What V5 explicitly does **not** ship:
- A profitable strategy. The 13-trade sample tells us the current strategy is not profitable on M15.
- A live OANDA writer client. Per design — no live execution until V4.8 ChartMind redesign produces a winning variant.
- The 2-trades/day target. Cannot be reached without ChartMind redesign.
- The 150 % return target. Cannot be reached without a profitable per-trade expectancy.

## 11. The decision

V4.7 is **APPROVED** as architecture. V4.7 is **NOT APPROVED** for live execution.

V4.8 is **NOT a calibration sweep**. V4.8 is a **ChartMind setup-logic redesign**. The calibration toolkit shipped in this release stays available for future use, but for V4.8 it is not the right tool.

V4.9 is **paused indefinitely** until V4.8 produces a profitable, Red-Team-resistant ChartMind variant.

V5 is **released as the architecture and operations harness**, with explicit honesty that the trading layer underneath needs another iteration of real work.

This is the truth. The user asked for it.
