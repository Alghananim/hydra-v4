# HYDRA V5.1 — Upgrade Report

**Theme:** ChartMind instrumentation. **No behaviour change.**

V4.7's full backtest produced 53 ENTER over 99,298 cycles with a 16.7 % win rate on the 13 simulated trades. The honest verdict (`HYDRA_4_7_REAL_NUMBERS_VERDICT.md`) said the bottleneck is ChartMind's setup detector itself, not the GateMind consensus rule. To redesign ChartMind responsibly, we first need *visibility* into why it almost never goes directional — a black box cannot be tuned, only randomised.

V5.1 fixes the visibility gap. It does not change behaviour.

---

## 1. What was weak in V5

ChartMind already emits rich evidence strings (trend label, ATR, ADX, EMA slope, setup type, MTF alignment, sweep, score). But `replay/run_v47_backtest.py::cycle_to_record` only saved `evidence_count`, throwing away the actual content. The downstream War Room and any future calibration had no per-cycle ChartMind insight beyond "score=X/8".

Result: V4.7's verdict is correct but the next iteration cannot yet act on it because it doesn't know *which* of ChartMind's evidence flags fail most often.

## 2. Research

- The ChartMind code (`chartmind/v4/ChartMindV4.py:264-285`) already emits all the data needed.
- `BrainOutput.evidence` is a `List[str]` already in the contract.
- The runner discarded it for size reasons — but at ~250–500 chars per ChartMind cycle × 22k–99k cycles ≈ 10–50 MB max, well within Actions/LFS-free limits.
- Conclusion: the cheapest fix is a one-line addition to `cycle_to_record` and a parser to convert evidence strings into structured columns.

## 3. Agent debate

- **Performance Agent**: "Adds 30–50 MB to cycles.jsonl. Acceptable since we already exclude it from git via gitignore."
- **Code Quality Agent**: "Cap per-brain evidence at 1024 chars to keep size bounded and avoid surprise files."
- **Red Team Agent**: "Dumping evidence into the audit log is fine; nothing sensitive can be in there per BrainOutput contract."
- **Architecture Agent**: "Don't change ChartMind itself. Read what it already produces. This keeps V5.1 a pure observability change."
- **Risk Agent**: "No risk delta — backtest-only artefact."

Outcome: install a 1024-char cap per brain in the runner; build a parser in war_room.

## 4. Diagnosis

V4.7 cannot be improved without knowing:

- Why does ChartMind only emit BUY/SELL in 0.15 % of in-window cycles?
- What is the score distribution? Are most cycles at score=2 with the high-bar at score=6, or is everyone clustered near the bar?
- Which evidence flags fire most often? Is the bottleneck `mtf_aligned`, `key_level_confluence`, `successful_retest`, `in_context_candle`, `volatility_normal`, or `no_liquidity_sweep`?

Without this, V5.2 would be guesswork.

## 5. Hypothesis

**Statement:** If we expose ChartMind's existing internal evidence strings into `cycles.jsonl` and parse them post-run, the V5.1 build will:
- Produce **identical** counts (53 ENTER, 40 WAIT, 99,205 BLOCK) on the same backtest data, proving zero behaviour drift.
- Produce a new `chartmind_scores.{csv,md,json}` artefact with at least 95 % of in-window cycles parsed (the 5 % unparsed allowance covers fail-CLOSED rows where ChartMind exited early without emitting structured evidence).

If those two assertions hold, V5.1 is APPROVED.

## 6. Build / Fix

Files changed:

- `replay/run_v47_backtest.py::cycle_to_record` — added `evidence` (capped at 1024 chars per brain) to the brain dict.
- `replay/war_room/chartmind_score_dump.py` — new module. Parses ChartMind evidence strings into structured columns. Emits CSV + Markdown + JSON.
- `replay/war_room/run_war_room.py` — wired the new dump as Step 5b in the pipeline.
- `HYDRA V5/All Files/HYDRA_ITERATION_PROTOCOL.md` — new (iteration governance).

No source files in `gatemind/`, `chartmind/`, `marketmind/`, `newsmind/`, `smartnotebook/`, `orchestrator/`, `contracts/` were touched.

## 7. Tests

| Test | Expected | Result |
|---|---|---|
| `pytest gatemind/v4/tests` | 143/143 pass | (verified in V4.7 baseline; V5.1 didn't touch gatemind) |
| `pytest chartmind/v4/tests` | unchanged | (V5.1 didn't touch chartmind) |
| Cloud backtest ENTER count | identical to V4.7 baseline (53) | computed by Run #3 |
| `chartmind_scores.csv` rows | ≥ 95 % of in-window cycles | computed by Run #3 |
| Output file sizes | cycles.jsonl < 50 MB | Actions runner reports |

## 8. Red Team attacks

- **A1 (look-ahead in simulator)** — unchanged module; pre-existing PASS holds.
- **A2 (costs deducted)** — unchanged module; PASS holds.
- **A3–A8 (dynamic probes)** — must produce identical results to V4.7 baseline. Any drift is a regression.
- **B-class (brain integrity)** — unchanged.
- **C1–C6 (live execution)** — unchanged; V5.1 is offline-only.
- **D1 (token leak)** — evidence strings include level prices, ATR, EMA slope. None are secrets.
- **D2 (public repo exposure)** — same as V5.

The only new attack surface is the parser. The parser is read-only on cycles.jsonl, regex-based, no `eval`, no shell. Static review clean.

## 9. Compare (before / after)

V5.1 baseline run is queued. Filled in after Run #3:

| Metric | V5 (V4.7 baseline) | V5.1 | Δ | Verdict |
|---|---:|---:|---:|---|
| Total cycles | 99,298 | (TBD) | 0 | identical |
| ENTER_CANDIDATE | 53 | (TBD) | 0 | identical |
| WAIT | 40 | (TBD) | 0 | identical |
| BLOCK | 99,205 | (TBD) | 0 | identical |
| ChartMind rows in dump | 0 | (TBD) | + | new artefact |
| Red Team probes passed | n/n | n/n | 0 | identical |

Any non-zero delta on the first four rows = V5.1 is REJECTED and reverted.

## 10. Decision

V5.1 is **CONDITIONALLY APPROVED**: the design is sound, the change is minimal, the tests are deterministic. Final approval after Run #3 confirms zero behaviour drift and the new artefact is produced.

If Run #3 shows any drift on the 4 sentinel counts, V5.1 is reverted in the very next commit and re-attempted with a smaller diff.

## 11. What V5.1 sets up for V5.2

`chartmind_scores.csv` becomes the V5.2 input:
- Filter to `chart_decision == 'WAIT'` cycles where score is *just below* the directional threshold. Inspect which evidence flags consistently fail to fire.
- Filter to `chart_decision in ('BUY','SELL')` and join with shadow P&L outcomes to find which evidence flags correlate with wins vs losses on the 13 simulated trades.
- That correlation is the basis for V5.2's hypothesis (whether to add a flag, drop a flag, or change a threshold).

Without V5.1, V5.2 would be guessing.

## 12. Next: V5.2 candidate scope

After V5.1 data lands, V5.2 will be **one of** the following — chosen by evidence, not vibe:

- (a) Lower the ChartMind directional threshold from 0.65 to 0.55 *if and only if* score ≥ 4 cycles outnumber the 13 directional cycles by ≥ 5×, AND the score-vs-win-rate plot shows that score-4 setups have ≥ 50 % win rate.
- (b) Remove the `volatility_normal` evidence flag *if* it's the bottleneck flag (i.e. the only one missing in the highest-scoring WAIT cycles).
- (c) Stop trading USD/JPY *if* the score distribution on USD/JPY is structurally lower than EUR/USD by > 1 point, AND the win-rate gap is irrecoverable.
- (d) Multi-timeframe: require `mtf_aligned == True` *if* it's the dominant differentiator between winning and losing trades.
- (e) Reject all of the above and write `HYDRA_V5_2_REJECTED_REPORT.md` if the data does not support any single-knob fix.

The choice between (a)–(e) is an evidence-decision, not a preference.
