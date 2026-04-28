# HYDRA V5 — Final Approved Baseline

**Date:** April 2026
**Decision:** APPROVED for live paper-trading observation on OANDA practice account.
**Live capital:** explicitly NOT approved.
**Target:** observe V5's behaviour on real-time data for ≥30 days, compare to backtest.

---

## 1. What V5 is

V5 is the V4.7-architecture multi-brain trading system, validated by:
- 99,298-cycle 2-year M15 backtest on EUR/USD + USD/JPY.
- 143/143 GateMind unit tests passing.
- Full War Room investigation with 8 Red Team probes implemented.
- 1000-iteration deep audit with 18 catalogued findings.

## 2. Measured V5 baseline (the truth)

```
Cycles:          99,298
ENTER:               53
Win rate:        40.0 % (excl timeout)
Net pips:        +103.3 (over 2 years)
Trades / day:    0.073
EUR/USD net:     +157.1 pips (good)
USD/JPY net:     -53.8 pips (problematic)
Max DD:          -159.1 pips
Expected value:  +2.5 pips per trade (positive)
```

**Verdict:** profitable per-trade expectancy. Slow but real.

## 3. What V5 is NOT

- Not a 2-trades/day system (math: 0.073 / day)
- Not a 150 % return system (math: ~3 % / year at the measured rate)
- Not approved for live capital
- Not running USD/JPY safely (per-pair regression — V5 ships disabling USD/JPY recommended for paper trading)

## 4. Live paper-trading scope

For 30 days starting on user's first launch:
- OANDA practice account only.
- Read-only data feed (live market prices, NOT cached).
- Run all 5 brains + GateMind + SmartNoteBook per cycle (M15 tick).
- LIVE_ORDER_GUARD intact (6 layers).
- 16-condition `live/safety_guards.py` gate intact.
- Writer client absent → orders NEVER actually submitted.
- Mode `DRY_RUN_WOULD_HAVE_TRADED` records what V5 *would have* done in reality.
- Compare backtest vs paper outcome at end of 30 days.

## 5. Pre-flight before each session

- [ ] OANDA practice account credentials in environment.
- [ ] `replay_runs/dry_run/` directory writeable.
- [ ] Workspace not running V11 backtest in parallel (avoid contention).
- [ ] User aware that this is dry-run observation only, no live capital.

## 6. Launch

Double-click `Run_HYDRA_V5_Paper.bat` on the desktop.

The launcher:
1. Verifies OANDA env vars present.
2. Confirms `HYDRA_LIVE_ARMED` is NOT set (paper mode is unconditional).
3. Runs `live/dry_run.py --duration-minutes 240 --output-dir replay_runs/v5_paper_<date>`.
4. Polls every 5 minutes for 4 hours.
5. Logs every cycle to `dry_run_log.jsonl`.
6. Logs `mode: DRY_RUN_WOULD_HAVE_TRADED` for any cycle that would have placed an order in armed mode.

Stop anytime with Ctrl+C. Resume by re-running the .bat — output appends to the same file.

## 7. What to watch for

| Observation | Interpretation |
|---|---|
| Cycle log shows live data being read every 5 min | Pipeline alive ✓ |
| Brains return BrainOutput per cycle | System integrated ✓ |
| GateMind decision recorded | Gate logic alive ✓ |
| SmartNoteBook has new entries | Audit trail intact ✓ |
| `live_order_attempted_total == 0` | Safety guards working ✓ |
| Periodic `DRY_RUN_WOULD_HAVE_TRADED` | Real candidates appearing |
| Repeated `final_status: BLOCK` reasons | Same patterns as backtest |

## 8. After 30 days — the 4 possible verdicts

1. **Live behaviour matches backtest.** Trades / day, win rate, blocked rates within ±20 % of measured. → V5 system is real. Decision: write live OANDA writer client (separate audit), then start V4.9 controlled-live with 0.05 % risk.

2. **Live behaviour worse.** Fewer ENTER candidates than backtest predicted. → backtest had hidden lookahead bias. Investigate.

3. **Live behaviour better.** More ENTERs, higher win rate. → calibration was conservative. Consider relaxation.

4. **Bug observed.** Crash, freeze, infinite loop in dry-run. → fix before any live consideration.

## 9. Things V5 ships with that paper trading exercises

- 5-brain pipeline (NewsMind, MarketMind, ChartMind, GateMind, SmartNoteBook)
- V4.7 consensus rule (ChartMind directional + News/Market vetoers)
- Real-time data via OandaReadOnlyClient
- 16-condition safety_guards (G01-G16)
- HMAC-chain audit ledger
- Per-cycle latency timing

## 10. Things V5 does NOT exercise

- OANDA write API (intentional)
- High-leverage margin (intentional)
- Multi-pair beyond EUR/USD + USD/JPY (data not in cache)
- M5 timeframe (V11 work, deferred)

## 11. Final verdict

V5 is the **honest MVP**. It is the best calibrated, tested, audited version of the system that the data supports. It is not the dream version. The dream version requires V11 (M5 + 6 pairs) which itself requires data fetching the user has not yet done.

V5 paper trading buys real-world data while V11 work continues in the background.

This is the engineering truth.
