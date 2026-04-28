# HYDRA V4.7 — Architectural Fix Report

**Date:** April 28, 2026
**Author:** Mansur Alghananim (with engineering assistant)
**Status:** Architectural fix verified live; partial 2-year backtest ran out of sandbox disk before completion. Full re-run requires moving SmartNoteBook to a larger volume.

---

## 1. Why V4.7 was needed

V4.6 ran the frozen orchestrator over 730 days of real M15 data on EUR/USD and USD/JPY (49,649 bars × 2 pairs = **99,298 cycles**). The headline result was honest and damning:

- **0 ENTER_CANDIDATE** out of 99,298 cycles.
- 95 cycles where all three brains achieved A or A+ grade (the original gate).
- Of those 95, every single one was rejected at R6 ("incomplete_agreement" or "directional_conflict").

Root cause was an **architectural collision between two contracts that the V4 build phases had locked in independently**:

| Component | Contract |
|-----------|----------|
| `newsmind/v4/NewsMindV4.py` (around line 213) | NewsMind only ever returns `WAIT` or `BLOCK`. It is a **veto brain**, not a directional brain. |
| `gatemind/v4/consensus_check.py` (pre-V4.7) | R6 required all three brains to issue the **same directional decision** (BUY or SELL) to enter. |

The two are mutually exclusive. NewsMind cannot satisfy "all three say BUY" because it cannot say BUY. The empirical 0/99,298 result was the inevitable consequence.

The user instruction that authorised the architectural change:

> "اكتشف النقص اكتشف الثغرات وعمل بعمق حتى توصل للهدف المطلوب"
> ("Discover the gaps and work deeply until the required target is reached.")

> "كمل الي نحتاجه انت واالفريق حتى تحقق المطلوب ممنوع الترجع"
> ("Continue what's needed until the required result is achieved. No turning back.")

---

## 2. The V4.7 architectural reconciliation

The fix lives in `gatemind/v4/consensus_check.py::consensus_status()`. The new contract:

- **ChartMind is the directional voice.** It detects the technical setup (BUY or SELL or WAIT).
- **NewsMind and MarketMind are vetoers.** They block in two ways:
  - `BLOCK` decision (already caught by R3/R4 upstream of consensus_check).
  - **An OPPOSING directional decision** to ChartMind's. (`directional_conflict`.)
- A `WAIT` decision from News or Market is not a veto — it is "no objection".

### New decision table

| News | Market | Chart | Returned label | Outcome at R6/R7/R8 |
|------|--------|-------|----------------|---------------------|
| any  | any    | any (one is BLOCK) | `any_block` | BLOCK |
| WAIT | WAIT   | WAIT  | `unanimous_wait` | WAIT |
| WAIT | WAIT   | BUY   | `unanimous_buy` | **ENTER_CANDIDATE BUY** |
| WAIT | WAIT   | SELL  | `unanimous_sell` | **ENTER_CANDIDATE SELL** |
| BUY  | WAIT   | BUY   | `unanimous_buy` | **ENTER_CANDIDATE BUY** |
| BUY  | BUY    | BUY   | `unanimous_buy` | **ENTER_CANDIDATE BUY** |
| BUY  | WAIT   | SELL  | `directional_conflict` | BLOCK |
| SELL | any    | BUY   | `directional_conflict` | BLOCK |
| BUY  | BUY    | WAIT  | `incomplete_agreement` | BLOCK (Chart's caution wins) |

The table covers every case the live system can produce. The `incomplete_agreement` row preserves a sensible default: if News and Market are calling for direction but Chart is unsure, we respect Chart's caution and stay out.

---

## 3. Verification

### 3.1 Unit-level reload test

After applying the fix and clearing all `__pycache__/` directories, a Python REPL evaluation produced the expected outcomes for every entry in the table above. Specifically:

```
news=WAIT, mkt=WAIT, chart=BUY  -> ('unanimous_buy', 'BUY')
news=WAIT, mkt=WAIT, chart=SELL -> ('unanimous_sell', 'SELL')
news=WAIT, mkt=WAIT, chart=WAIT -> ('unanimous_wait', None)
news=BUY,  mkt=BUY,  chart=BUY  -> ('unanimous_buy', 'BUY')
news=BUY,  mkt=BUY,  chart=WAIT -> ('incomplete_agreement', None)
news=BUY,  mkt=BUY,  chart=SELL -> ('directional_conflict', None)
```

### 3.2 Existing test suite

```
gatemind/v4/tests          : 143 passed (0.27s)
orchestrator/v4/tests      : 102 passed, 1 failed
```

The single failing orchestrator test is **pre-existing and unrelated to V4.7**:
- Test: `orchestrator/v4/tests/test_scalability.py::test_no_internal_state_between_cycles`
- It asserts `r1.gate_decision.audit_id != r2.gate_decision.audit_id` for two cycles with **identical inputs**.
- `gatemind/v4/audit_log.py::make_audit_id` is deterministic by design (its docstring: *"Deterministic audit_id from time + symbol + content fingerprint"*) and its tests in `test_audit_trail.py` rely on that.
- Verified independently: with the V4.7 fix reverted in memory, the same audit_ids match. The test contradicts the design contract.
- Logged for later cleanup — not blocking.

---

## 4. Partial 2-year backtest (V4.7 active)

A fresh chunked run was launched with the V4.7 fix in place over the same 730-day window (2024-04-28 → 2026-04-28). Each chunk had a 35-second wall-clock budget; results are checkpointed and resumable.

### 4.1 Where the run reached

| Metric | Value |
|--------|-------|
| Timeline length | 49,649 timestamps (× 2 pairs = 99,298 cycles) |
| Resume index reached | **10,380 / 49,649 (20.9 %)** |
| ENTER_CANDIDATE | **9** |
| WAIT | 4 |
| BLOCK | 20,747 |
| Orchestrator errors | 0 |

The process was terminated by an environment failure, not a code failure. SmartNoteBook writes a record per cycle (HMAC chain + JSONL ledger + SQLite mirror). After ~20,000 cycles, the sandbox `/tmp` partition filled. The runner reported:

```
LedgerWriteError: SQLite mirror failed for record_id=8c243634-...:
database or disk is full
```

After that point, the bash sandbox itself became unresponsive (`no space left on device` blocking even environment setup). Recovery requires either:

1. Running the backtest on a host with more local disk (the user's Windows laptop has ample space), or
2. Pointing `SmartNoteBookV4` at the user's workspace folder with a checkpoint-rotation policy, or
3. Stubbing the SmartNoteBook for backtest mode (write only ENTER cycles).

### 4.2 Linear projection (caveats below)

If the rate observed in the first 20.9 % continues:

- **9 ENTER × (49,649 / 10,380) ≈ 43 candidates over 2 years** ≈ **0.059 trades/day**.

**This is far below the user's 2-trades/day target.** It does, however, prove the V4.7 architecture works — the same window produced 0 candidates under V4.6 logic.

### 4.3 Why this projection is unreliable

1. The first 20.9 % includes a cold-start period (~5 days of M15 warm-up) where MarketMind/ChartMind cannot grade above B because indicators have not converged.
2. Trade density depends on calendar event clustering (FOMC, NFP, ECB) — those are not uniformly distributed across the 2 years.
3. The current ChartMind grading thresholds were tuned against synthetic data; real-data grading distribution may shift once the system runs end-to-end.

The honest reading is "≥9 trades over 2 years on real data, V4.7 architecture confirmed live." Anything sharper requires the full run.

---

## 5. Files changed in this phase

| File | Change |
|------|--------|
| `gatemind/v4/consensus_check.py` | Replaced `consensus_status()` with V4.7 logic (ChartMind = directional voice, News/Market = vetoers via opposing direction or BLOCK). |

No other source files were modified during V4.7. All previous phases' invariants (BrainOutput I1-I9, LIVE_ORDER_GUARD, no-lookahead, secret protection, HMAC chain) are untouched.

---

## 6. Outstanding work to reach the 2-trades/day target

These are tracked honestly — none of them are guaranteed to deliver the target, but each closes a known gap:

1. **Re-run the full 2-year backtest end-to-end on the user's Windows laptop**, where disk is not the bottleneck. This produces a real 2-year ENTER count, win rate, P&L curve, and drawdown.
2. **Run the existing P&L simulator** (`replay/pnl_simulator.py`) on the resulting ENTER records with conservative SL/TP assumptions to compute honest return %.
3. If the trade count is below 2/day, the gating layers to revisit are (in order of expected impact):
   - **Grade threshold** — currently rejects everything below A. The data shows A/A+ unanimous is rare (95 cycles in 99,298 under V4.6 measurement). Loosen to A/A+/B with a ChartMind weight, or report two backtests side by side (strict and relaxed).
   - **ChartMind setup detector sensitivity** — its `BUY`/`SELL` threshold may be too high for M15 in this volatility regime.
   - **Trading window width** — the two NY windows total 6 hours/day. Some valid setups will fall outside.
4. **Fix the pre-existing audit-id test** (`test_no_internal_state_between_cycles`) so the orchestrator suite is clean.
5. **Stub SmartNoteBook for backtest mode** to keep the per-cycle ledger from blowing up disk in long replays.

These items become V4.8.

---

## 7. Summary

| Question | Answer |
|----------|--------|
| Does the V4.7 fix compile and reload cleanly? | Yes. |
| Do the existing GateMind tests still pass? | 143/143 pass. |
| Did the architectural fix unlock real ENTER candidates on real data? | Yes — 9 candidates in the first 20.9 % of a window that produced 0 under V4.6. |
| Is the system at 2 trades/day yet? | No. Partial-run projection ≈ 0.059/day. The architecture is now correct; the calibration is the next problem. |
| Are any V4-locked invariants broken? | No. Only `consensus_check.py` changed. |

V4.7 is the correct architectural shape. V4.8 is calibration on real data.
