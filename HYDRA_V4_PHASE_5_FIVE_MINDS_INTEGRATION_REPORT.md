# HYDRA V4 — PHASE 5 FIVE-MINDS INTEGRATION FINALIZATION REPORT

**Generated:** 2026-04-27
**Scope:** Verify and document the final integration of all five minds into HYDRA V4. No trading-logic changes. No new features. Read-only verification of existing integration code + test coverage mapping.
**Verdict (TL;DR):** ✅ **The five minds are integrated, and the integration is testable, traceable, and fail-closed by design.** Closure of Phase 5 still requires running the Phase 2 verify batch to confirm test execution; no trading logic was modified during this phase.

---

## 1. How the Five Minds Are Connected

The orchestrator `HydraOrchestratorV4` (`orchestrator/v4/HydraOrchestratorV4.py`) is the spinal cord of the system. It owns five injected dependencies (one per mind) and runs them in a strict, sequential pipeline. Each mind is constructed independently and passed to the orchestrator constructor; the orchestrator never instantiates trading logic itself.

```
HydraOrchestratorV4
  ├── newsmind:      NewsMindV4
  ├── marketmind:    MarketMindV4
  ├── chartmind:     ChartMindV4
  ├── gatemind:      GateMindV4
  └── smartnotebook: SmartNoteBookV4
```

Constructor (line 116):
```python
def __init__(
    self,
    smartnotebook_base_dir: Optional[Path] = None,
    *,
    newsmind:    Optional[NewsMindV4]    = None,
    marketmind:  Optional[MarketMindV4]  = None,
    chartmind:   Optional[ChartMindV4]   = None,
    gatemind:    Optional[GateMindV4]    = None,
    smartnotebook: Optional[SmartNoteBookV4] = None,
    strict: bool = False,
)
```

`strict=True` refuses silent default construction — any unset mind raises `OrchestratorError`. This forbids the system from quietly running with a default-built brain.

---

## 2. The Full Decision Flow

Every call to `run_cycle(symbol, now_utc, bars_by_pair, bars_by_tf)` executes the sequence below. Each stage propagates its output as input to the next. The order is fixed.

```
                        ┌─────────────────────────────────────────────┐
                        │ Inputs validated:                            │
                        │   - symbol non-empty                         │
                        │   - now_utc tz-aware UTC                     │
                        │   - bars_by_pair / bars_by_tf not None       │
                        └────────────────────┬────────────────────────┘
                                             │
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ Stage 1 — NewsMindV4.evaluate(symbol, now)  │
                        │   Output: BrainOutput (news_out)            │
                        │   isinstance check → MissingBrainOutputError│
                        │   on type mismatch                          │
                        └────────────────────┬────────────────────────┘
                                             │  news_out
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ Stage 2 — MarketMindV4.evaluate(             │
                        │     symbol, bars_by_pair, now,               │
                        │     news_output=news_out)                    │
                        │   Output: MarketState (BrainOutput subtype)  │
                        │   isinstance check                           │
                        └────────────────────┬────────────────────────┘
                                             │  market_out
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ Stage 3 — ChartMindV4.evaluate(              │
                        │     symbol, bars_by_tf, now,                 │
                        │     news_output=news_out,                    │
                        │     market_output=market_out)                │
                        │   Output: ChartAssessment (BrainOutput sub.) │
                        │   isinstance check                           │
                        └────────────────────┬────────────────────────┘
                                             │  chart_out
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ Stage 4 — GateMindV4.evaluate(               │
                        │     news_out, market_out, chart_out,         │
                        │     now, symbol)                             │
                        │   Output: GateDecision (frozen verdict)      │
                        │   isinstance check                           │
                        └────────────────────┬────────────────────────┘
                                             │  gate_decision
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ Stage 5 — SmartNoteBookV4 records             │
                        │     DECISION_CYCLE + GATE_AUDIT records.     │
                        │   Failure → marks cycle as BLOCK with        │
                        │   SMARTNOTEBOOK_RECORD_FAILURE_PREFIX.       │
                        │   No silent skip.                            │
                        └────────────────────┬────────────────────────┘
                                             │
                                             ▼
                        ┌─────────────────────────────────────────────┐
                        │ DecisionCycleResult (frozen dataclass)       │
                        │   final_status ← gate_decision (1:1 mapping) │
                        │   No override path exists                    │
                        └─────────────────────────────────────────────┘
```

The 1:1 mapping (`_gate_outcome_to_final` in HydraOrchestratorV4.py:300) is the only place where the gate outcome becomes the final cycle status. There is no code path that lets the orchestrator override the gate.

---

## 3. Schemas / Contracts Used

| Contract | File | Enforced via |
|---|---|---|
| `BrainOutput` | `contracts/brain_output.py` | Frozen dataclass; `__post_init__` enforces invariants I1–I9 |
| `MarketState` | `marketmind/v4/models.py` | Subclass of BrainOutput; brain_name must be `"marketmind"` |
| `ChartAssessment` | `chartmind/v4/models.py` | Subclass of BrainOutput; brain_name must be `"chartmind"` |
| `GateDecision` | `gatemind/v4/models.py` | Frozen dataclass with audit_id, gate_decision enum, blocking_reason |
| `DecisionCycleResult` | `orchestrator/v4/decision_cycle_record.py` | Frozen dataclass; `__post_init__` enforces final-status invariants |
| Anthropic JSON | `anthropic_bridge/response_validator.py` | stdlib JSON-schema validator with strict enum enforcement |

**BrainOutput invariants (I1–I9):**
- I1 brain_name in {newsmind, marketmind, chartmind, gatemind, smartnotebook}
- I2 decision in {BUY, SELL, WAIT, BLOCK}
- I3 data_quality in {good, stale, missing, broken}
- I4 confidence in [0, 1]
- I5 grade ∈ {A_PLUS, A} requires `len(evidence) >= 1` AND `data_quality == "good"`
- I6 should_block=True requires grade == BLOCK
- I7 grade == BLOCK requires decision == "BLOCK"
- I8 timestamp_utc must be tz-aware UTC
- I9 reason non-empty

These invariants run at construction time. **An invalid output cannot leave a brain.**

---

## 4. How GateMind Receives and Validates All Three Mind Outputs

`GateMindV4.evaluate(news_out, market_out, chart_out, now_utc, symbol)` runs a strict ladder defined in `gatemind/v4/rules.py`:

1. **Schema validation** (`gatemind/v4/schema_validator.py`) — every input must be a valid `BrainOutput` subtype with the correct `brain_name`. Failure → `BLOCK` with `REASON_SCHEMA_INVALID`.
2. **Brain-block check** — if any input has `should_block=True` or `grade == BLOCK`, return `BLOCK` with `REASON_BRAIN_BLOCK`.
3. **NY-window check** (`session_check.is_in_ny_window`) — outside `03:00–05:00` or `08:00–12:00` New York local → `BLOCK` with `REASON_OUTSIDE_NY` (Hardening Requirement #11).
4. **Grade threshold** — every brain must be `A` or `A+`; any `B` / `C` → `BLOCK` with `REASON_GRADE_BELOW`.
5. **Consensus check** (`consensus_check.py`) — all three minds must agree on direction (3/3). Conflict → `BLOCK` with `REASON_NO_CONSENSUS`.
6. **Kill-flag check** — `KILL_FLAG_ACTIVE` env / file → `BLOCK` with `REASON_KILL_FLAG`.

Only when every check passes → `ENTER_CANDIDATE` with `direction = unanimous_direction`.

**Strict mode confirmed:**
- 3/3 unanimous required ✓
- A or A+ only ✓
- Any B or lower → BLOCK ✓
- Missing brain output → caught by orchestrator isinstance check before reaching gate
- Conflict → BLOCK ✓
- Outside NY → BLOCK ✓

---

## 5. How SmartNoteBook Records the Full Cycle

The orchestrator calls `_record_to_smartnotebook(...)` (line 320). It writes two linked records per cycle:

| Record type | Content |
|---|---|
| `DECISION_CYCLE` | cycle_id, symbol, timestamp_utc, all three brain outputs, gate decision, final_status, final_reason, errors |
| `GATE_AUDIT` | audit_id, gate_decision, direction, blocking_reason, approval_reason, session_status, the per-brain grades + decisions + risk_flags |

The records are linked by `decision_cycle_record_id` and `gate_audit_record_id` returned to the `DecisionCycleResult`. SmartNoteBook chain-hashes every record (HMAC-SHA256 if `HYDRA_NOTEBOOK_HMAC_KEY` is set; plain SHA256 otherwise — a warning is logged in the latter case).

**Full per-cycle record fields (all required by Phase 5 spec):**

| Field | Source |
|---|---|
| cycle_id | `mint_cycle_id(now_utc)` |
| symbol | input |
| timestamp_utc | input |
| timestamp_ny | `now_utc.astimezone(NY_TZ)` |
| session_status | `gate_decision.session_status` |
| newsmind_output | `news_out` (full BrainOutput snapshot) |
| marketmind_output | `market_out` (full MarketState snapshot) |
| chartmind_output | `chart_out` (full ChartAssessment snapshot) |
| gatemind_output | `gate_decision` (full GateDecision snapshot) |
| smartnotebook_record_id | `decision_cycle_record_id` |
| final_status | `_gate_outcome_to_final(gate_decision)` |
| final_reason | `gate_decision.approval_reason` or `blocking_reason` |
| errors | accumulated during cycle |

✓ Every required field is recorded.

---

## 6. What Happens When a Mind Fails

| Failure type | Behaviour | Test |
|---|---|---|
| Brain raises an exception inside its `_evaluate_inner` | Brain's outer `evaluate()` catches → returns `BrainOutput.fail_closed(...)` with `grade=BLOCK`, `decision=BLOCK`, `data_quality=broken` | Per-brain `test_hardening.py` |
| Brain returns a non-BrainOutput object | Orchestrator isinstance check raises `MissingBrainOutputError` → cycle records `ORCHESTRATOR_ERROR` and returns `BLOCK` | `test_evaluate_e2e.py::test_09` |
| Brain returns `BrainOutput` with `grade=BLOCK` | GateMind detects `should_block` → `BLOCK` with `REASON_BRAIN_BLOCK` | `test_evaluate_e2e.py::test_08` |
| Brain returns `BrainOutput` with `grade=B` or below | GateMind detects threshold → `BLOCK` with `REASON_GRADE_BELOW` | `test_evaluate_e2e.py::test_07` |
| Brain raises an unexpected exception that the brain's own fail-closed didn't catch | Orchestrator outer `try/except` records `ORCHESTRATOR_ERROR`, writes SmartNoteBook entry, returns `BLOCK` | `test_fail_closed_propagation.py` |
| SmartNoteBook write fails (disk-full, chain corruption) | Orchestrator catches → final_status forced to `BLOCK` with `SMARTNOTEBOOK_RECORD_FAILURE_PREFIX` marker. **No silent skip.** | `test_smartnotebook_recording.py` |

**No silent failure path exists.**

---

## 7. What Happens When Outputs Conflict

GateMind's `consensus_check.py` requires unanimous direction across the three brains.

| Scenario | Result |
|---|---|
| News BUY, Market BUY, Chart BUY | ENTER_CANDIDATE direction=BUY |
| News SELL, Market SELL, Chart SELL | ENTER_CANDIDATE direction=SELL |
| News BUY, Market BUY, Chart WAIT | BLOCK (not 3/3) |
| News BUY, Market BUY, Chart SELL | BLOCK (conflict) |
| All WAIT | WAIT (final_status), not ENTER |
| Any BLOCK | BLOCK |

Tests: `test_evaluate_e2e.py::test_05` (two-buy-one-wait → BLOCK), `test_06` (two-buy-one-sell → BLOCK).

---

## 8. How Silent Failures Are Prevented

| Safeguard | Where | Effect |
|---|---|---|
| Output-type isinstance after each brain call | Orchestrator lines 220–264 | Wrong type → `MissingBrainOutputError` |
| Outer try/except wraps the whole brain pipeline | Orchestrator lines 271–296 | Unexpected exception → `ORCHESTRATOR_ERROR` cycle, BLOCK, SmartNoteBook entry |
| BrainOutput invariants in `__post_init__` | `contracts/brain_output.py` | Invalid output cannot exist as a Python object |
| GateMind schema_validator | `gatemind/v4/schema_validator.py` | Schema-invalid input → BLOCK |
| SmartNoteBook write try/except → BLOCK marker | Orchestrator lines 332–367 | Write failure → BLOCK with marker; never silently skipped |
| `_log.exception(...)` at every fail-closed boundary | Throughout | Stack-trace recorded with cycle_id |

Every failure path either raises or converts to BLOCK + a recorded reason.

---

## 9. How Live Orders Are Prevented

Six layers, all confirmed in Phase 1 audit and re-checked in Phase 3:

1. `LIVE_ORDER_GUARD_ACTIVE = True` module flag.
2. `_GUARD_BURNED_IN` sentinel captured by closure — cannot be flipped at runtime.
3. Each of seven order methods (`submit_order`, `place_order`, `close_trade`, `modify_trade`, `cancel_order`, `set_take_profit`, `set_stop_loss`) calls `assert_no_live_order(...)`.
4. `__init_subclass__` re-wraps blocked methods on every subclass.
5. `OandaReadOnlyClient` uses stdlib `urllib.request` only (no `requests` library); endpoint allowlist permits GET to `/v3/instruments/...` and `/v3/accounts/{id}/{instruments|summary}` only.
6. Account-ID match: the path account-ID must equal `self._account_id`; mismatched calls raise.

Tests: `live_data/tests/test_live_order_guard.py` (8 tests).

The orchestrator never imports anything that could create a write-capable broker client. All bar data flows through `OandaReadOnlyClient` (read-only) or, in replay, through the local JSONL cache.

---

## 10. Integration Test Mapping (16 Required Scenarios)

| # | Required scenario | Existing test | File |
|---|---|---|---|
| 1 | All three minds BUY A/A+ in NY → ENTER | `test_01_all_aplus_buy_in_window` | `test_evaluate_e2e.py` |
| 2 | All three minds SELL A/A+ in NY → ENTER | `test_02_all_a_sell_in_window` | `test_evaluate_e2e.py` |
| 3 | All three WAIT → WAIT | `test_04_all_wait` | `test_evaluate_e2e.py` |
| 4 | NewsMind BLOCK → BLOCK | `test_08_news_kill_flag` | `test_evaluate_e2e.py` |
| 5 | MarketMind B → BLOCK | covered by grade-threshold tests | `gatemind/v4/tests/test_grade_enforcement.py` |
| 6 | ChartMind B → BLOCK | `test_07_chartmind_grade_b` | `test_evaluate_e2e.py` |
| 7 | Missing mind output → BLOCK or error | `test_09_chart_returns_invalid_brain_output_type` | `test_evaluate_e2e.py` |
| 8 | Invalid schema → BLOCK or error | `test_16_real_schema_invalid_propagates_to_block` | `test_evaluate_e2e.py` |
| 9 | Conflicting directions → BLOCK | `test_05` (two-buy-one-wait), `test_06` (two-buy-one-sell) | `test_evaluate_e2e.py` |
| 10 | Outside NY window → BLOCK | `test_10_outside_ny_window` + `test_ny_session.py` | `test_evaluate_e2e.py` + dedicated file |
| 11 | Claude override attempt → rejected | dedicated file | `test_claude_safety.py` |
| 12 | Orchestrator cannot bypass GateMind | dedicated file | `test_no_override_gate.py` |
| 13 | SmartNoteBook logs every mind output | `test_11_decision_cycle_carries_4_snapshots` + dedicated file | `test_evaluate_e2e.py` + `test_smartnotebook_recording.py` |
| 14 | SmartNoteBook logs every blocking reason | `test_smartnotebook_recording.py` | dedicated |
| 15 | No OANDA live order path | `test_no_live_order.py` | dedicated |
| 16 | Red Team malformed outputs fail safely | `test_orchestrator_hardening.py` | dedicated |

**Coverage: 16/16 scenarios have at least one existing test.**

⚠️ **Test execution status: PENDING.** The Phase 2 verify batch (`Phase2_Verify.bat`) has not been run. The mapping above is structural (test-file presence + function names); actual pass/fail counts require running the batch.

---

## 11. Red Team Findings

I attempted to break the integration via mental adversarial testing. Each attack is matched against an existing defense.

| Attack | Defense | Result |
|---|---|---|
| Inject a fake brain that returns `dict` instead of BrainOutput | Orchestrator isinstance check (line 223–225) | ❌ blocked — MissingBrainOutputError |
| Inject a brain that always returns A grade with empty evidence | BrainOutput I5 invariant | ❌ blocked at construction time |
| Inject a brain that returns BLOCK with decision=BUY | BrainOutput I7 invariant | ❌ blocked |
| Inject a brain that raises an exception | Brain `evaluate()` outer try/except → fail_closed BrainOutput | ❌ blocked → BLOCK |
| Bypass GateMind by setting `final_status=ENTER_CANDIDATE` directly on DecisionCycleResult | DCR `__post_init__` requires `gate_decision.gate_decision.value == "ENTER_CANDIDATE"` | ❌ blocked |
| Submit naive (non-tz-aware) `now_utc` | DCR `__post_init__` requires `timestamp_utc.utcoffset() == 0` | ❌ blocked |
| Make SmartNoteBook write fail (disk full) and watch the cycle silently succeed | Orchestrator forces final_status=BLOCK with marker | ❌ no silent success |
| Try to call `submit_order` on the OANDA client | LIVE_ORDER_GUARD assert_no_live_order | ❌ blocked |
| Subclass `OandaReadOnlyClient` and override `submit_order` | `__init_subclass__` re-wraps | ❌ blocked |
| Try to fetch `/v3/accounts/{other_account}/orders` | account-ID mismatch raises | ❌ blocked |
| Try `requests.post` from anywhere in the codebase | No `requests` import in code; stdlib `urllib.request` only | ❌ no library available |
| Have Anthropic return `{"suggestion": "upgrade"}` | bridge whitelist (`agree/downgrade/block` only) | ❌ blocked |
| Have Anthropic return non-JSON free text | bridge requires `tool_use.input` to be a dict | ❌ blocked |
| Have a brain return outputs at different (later) timestamp than now_utc | downstream consumers reference DCR.timestamp_utc, not brain timestamps; replay engine uses `assert_no_future` to validate | ❌ logically isolated |
| Submit input outside NY window expecting trade | session_check.is_in_ny_window → REASON_OUTSIDE_NY | ❌ blocked |
| Two brains agree BUY, one brain WAIT — argue this is "majority" | consensus_check requires unanimous (3/3) | ❌ blocked |
| Submit cycle with kill-flag active | rules.py kill-flag check → REASON_KILL_FLAG | ❌ blocked |

**Result: no integration bypass found.** All 17 attack scenarios are blocked by existing code.

---

## 12. Fixes Applied

**None in Phase 5.** Phase 5 is a verification phase per the user's spec ("Do not build new trading logic. Do not change GateMind rules. Do not change risk."). The integration is already complete from prior phases (per the freeze-report history).

If the Phase 2 verify batch reveals any failing tests, those will be addressed in a Phase 5 follow-up step. No code was modified during this phase.

---

## 13. Was Trading Logic Changed?

**No.** The following were untouched in Phase 5:
- All five brains
- Orchestrator cycle logic
- GateMind ladder, consensus_check, session_check, schema_validator
- contracts/brain_output.py
- LIVE_ORDER_GUARD
- OandaReadOnlyClient
- Anthropic bridge
- Replay engine
- Configs (events.yaml, keywords.yaml)

**Phase 5 was strictly read-only verification.**

---

## 14. Phase 5 Closure Decision

### Closure rule (from user's spec):
- All five minds connected — ✅
- Orchestrator runs the full decision cycle — ✅
- GateMind cannot be bypassed — ✅
- SmartNoteBook records the full decision cycle — ✅
- Invalid/missing/conflicting outputs fail-closed — ✅
- No live order path triggered — ✅
- Tests pass or failure documented — ⚠️ test execution still pending Phase 2 verify batch
- Red Team findings addressed — ✅ (no findings; integration is robust)
- Report written in English — ✅ (this file)
- Git status clear — ⏳ Phase 1 + Phase 2 commits still pending
- Commit if changes made — N/A (no changes)

### **VERDICT: ⚠️ PHASE 5 ANALYSIS COMPLETE, FORMAL CLOSURE DEPENDS ON TEST EXECUTION.**

Structurally, the five-minds integration is finalized. The orchestrator runs all five brains in the required sequence. Every failure mode is handled. Every required record field is captured. No live-order path is reachable. Sixteen-of-sixteen integration scenarios have existing tests.

**The single open dependency is running `Phase2_Verify.bat`** to convert "tests exist and look right" into "tests pass with N green / 0 failed."

---

## 15. Phase 6 Readiness

**❌ Not yet ready.** Required gates before Phase 6:

1. Run `Phase2_Cleanup.bat` (queued from Phase 2).
2. Run `Phase2_Verify.bat` (queued from Phase 2). Capture `PHASE2_VERIFY.txt`.
3. If any tests fail, fix and re-run. If all green, capture pass count.
4. Resolve the Phase 1 git-state issue: commit the 14 untracked dirs/files plus the modified `contracts/brain_output.py` and `.gitignore`. Tag `phase-1-baseline-freeze` (or per the strict-fidelity Option B from Phase 1 report).
5. Optionally tag `phase-5-five-minds-integration-finalization` after the cleanup commit lands.
6. Push to a private GitHub remote — strongly recommended given the project still has zero off-laptop backup.

Only after these steps should Phase 6 begin.

---

## 16. Honest Bottom Line

The integration is real, not a fake connection. Five separate frozen brains feed each other through typed contracts, with isinstance gates after every hand-off, and a final 1:1 mapping from gate verdict to cycle final-status. Every failure mode produces a recorded BLOCK rather than a silent success. Every required field in the per-cycle record is present.

The risk remaining is operational, not architectural:
- The codebase is mostly untracked in git (Phase 1 finding).
- Tests have not been executed end-to-end in this conversation; we have structural confidence but not a green run.

Both are fixable by running the queued Phase 2 batches and committing.
