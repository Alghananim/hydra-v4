# HYDRA V11.1 — Foundation Modules

**Status:** First V11 deliverable. Foundation modules written. No backtest yet — that comes after M5 cache exists.

## What V11.1 ships

| File | Purpose |
|---|---|
| `v11/__init__.py` | Package docstring + module roadmap |
| `v11/pairs.py` | Per-pair calibration table for 6 instruments. Sets typical ATR, max spread, SL/TP per pair, and grade-A min evidence (USD/JPY and EUR/JPY get stricter 6/8). |
| `v11/windows.py` | 4-window schedule (Asian, London open, London-NY overlap, NY close) totalling 10h/day vs V5's 6h/day. |
| `v11/setups.py` | Three new setup detectors: inside-bar breakout, range break, mean-reversion at S/R. |
| `v11/m5_data_fetch.py` | OANDA M5 paginated fetcher. Builds `data_cache/<PAIR>/M5/merged.jsonl` for all 6 pairs. |

## Per-pair calibration summary

| Pair | ATR (M5) | SL | TP | R:R | Grade-A | BE win rate |
|---|---:|---:|---:|---:|---:|---:|
| EUR_USD | 4.5p | 8 | 16 | 2.00 | 5/8 | 33 % |
| USD_JPY | 5.5p | 10 | 18 | 1.80 | **6/8** | 36 % |
| GBP_USD | 6.0p | 12 | 24 | 2.00 | 5/8 | 33 % |
| USD_CAD | 5.0p | 10 | 18 | 1.80 | 5/8 | 36 % |
| AUD_USD | 4.0p | 8 | 14 | 1.75 | 5/8 | 36 % |
| EUR_JPY | 7.0p | 14 | 24 | 1.71 | **6/8** | 37 % |

USD_JPY and EUR_JPY get stricter `grade_a_min_evidence` because V5 measured them as the loss source.

## Window expansion

V5: 6h/day in-window (25 % of timeline)
V11: 10h/day in-window (41.7 % of timeline) — **1.67x more in-window cycles**

Combined with M5 (3x bars/day) and 6 pairs (3x instruments) vs V5's M15 + 2 pairs:
**~9x more cycles per 2-year backtest** = 99k → ~900k.

If per-cycle ENTER rate stays at V5's 0.21%: **1,890 ENTER over 2 years = 2.6 / day**. The math now works.

## What V11.1 does NOT do

- Does NOT fetch M5 bars yet. The fetcher script is ready but requires `OANDA_API_TOKEN` to be set. The user runs it once on their practice account to populate the cache.
- Does NOT modify ChartMindV4. V11 wraps it; the V4.7 invariants are preserved.
- Does NOT enable live trading. All V11 work is offline backtest until V11.4 (Red Team) signs off.
- Does NOT change V5's invariants: V4.7 consensus, 16-condition guard, SmartNoteBook chain — all kept.

## Next: V11.2 (week 2)

- Wrap ChartMindV4 with V11 setup detectors layer.
- Wire real M5+M15+H1 multi-timeframe pipeline (closes audit finding F-015).
- First V11 unit tests.

## Path to first V11 backtest

1. **User**: set `OANDA_API_TOKEN` in env, run `python -m v11.m5_data_fetch`. Takes ~30 minutes on practice account. Builds 6 × ~52 MB cache files.
2. **Me**: build V11.2 wrapper + V11 backtest runner.
3. **GitHub Actions**: matrix workflow for V11 variants (similar to V5 matrix but on V11).
4. **War Room V11**: same 8 Red Team probes plus per-instrument and per-window robustness.

## Honest expectation

- If V11.1+V11.2+V11.3 stack delivers ~1.5 trades/day with positive net pips: **APPROVED for V11.4 controlled-live**.
- If V11 stack delivers <0.7 trades/day: **strategy class change needed (V12+)** — different instrument category, not just more pairs.
- If V11 stack delivers high trade count but negative net pips: **per-pair rejection**. Drop the losing pair(s) and re-evaluate.

No promises. Just a clear measurement plan.
