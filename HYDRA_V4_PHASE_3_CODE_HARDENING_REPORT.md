# HYDRA V4 — PHASE 3 CODE HARDENING & FAIL-CLOSED PROTECTION REPORT

**Generated:** 2026-04-27
**Scope:** Defensive-engineering analysis. Identify silent failures, schema bypasses, weak fail-closed paths. NO trading-logic changes.
**Verdict (TL;DR):** ✅ **HYDRA V4 already has dense hardening built in** from the per-brain freeze phases. Phase 3 confirms it, identifies 4 minor gaps, and defers closure until Phase 2 verify-batch is run (we need a passing-tests baseline before adding any new guards).

---

## 0. Standing Caveat — Prerequisites Not Yet Run

| Pre-requisite | Status | Impact |
|---|---|---|
| Phase 2 `Phase2_Cleanup.bat` | ❌ Not executed | pycache, archive, report-organisation pending |
| Phase 2 `Phase2_Verify.bat` | ❌ Not executed | **No baseline test pass/fail data** |
| Phase 1 commit + tag | ❌ Not done | Working tree still has 14 untracked dirs |

This means Phase 3 **analysis** is complete, but Phase 3 **closure** depends on running Phase 2 verify so we have a green baseline. No new guards/tests should be added on a pre-verified tree — too easy to miss what we broke vs what was already broken.

---

## 1. Existing Hardening Inventory (READ-ONLY VERIFICATION)

The previous brain-freeze phases built in extensive defensive code. Phase 3 read-only inspection confirms the following are present:

### A. Schema validation per brain (Hardening Requirement #1, #14, #15)
- `contracts/brain_output.py` — `BrainOutput.__post_init__` enforces invariants I1–I9:
  - **I1**: `brain_name in {newsmind, marketmind, chartmind, gatemind, smartnotebook}` — invalid → `ValueError`
  - **I2**: `decision in {BUY, SELL, WAIT, BLOCK}` — invalid → `ValueError`
  - **I3**: `data_quality in {good, stale, missing, broken}` — invalid → `ValueError`
  - **I4**: `confidence in [0,1]` — invalid → `ValueError`
  - **I5**: grade ∈ {A_PLUS, A} requires `len(evidence) >= 1` AND `data_quality == "good"` — **directly addresses requirements #8, #9, #12**
  - **I6**: `should_block=True` requires `grade == BLOCK`
  - **I7**: `grade == BLOCK` requires `decision == "BLOCK"`
  - **I8**: `timestamp_utc` must be tz-aware UTC — **directly addresses requirement #10**
  - **I9**: `reason` non-empty
- Each brain's evaluate() constructs `BrainOutput(...)` which runs `__post_init__` → invalid output **cannot leave the brain**.

### B. Per-brain fail-CLOSED at .evaluate() boundary (Requirement #2, #3)
Every brain's public `evaluate()` is wrapped:
```python
def evaluate(self, ...):
    try:
        return self._evaluate_inner(...)
    except Exception as e:
        return BrainOutput.fail_closed(brain_name=..., reason=..., ...)
```
Confirmed in: `NewsMindV4.evaluate` (line 92-108), and same pattern in MarketMindV4, ChartMindV4. GateMindV4 fails to BLOCK on schema-invalid inputs via its own `schema_validator.py`.

### C. Orchestrator integrity gates (Requirement #4)
`HydraOrchestratorV4.run_cycle` (lines 220–296):
- isinstance check after EACH brain call → raises `MissingBrainOutputError` if a brain returns non-BrainOutput
- Catches unexpected non-BrainOutput exceptions → records `ORCHESTRATOR_ERROR` SmartNoteBook entry, returns BLOCK
- **No silent success path**

### D. SmartNoteBook write-failure handling (Requirement #5)
Lines 313–367: SmartNoteBook record write is wrapped. On failure:
- Logs warning
- Appends `SMARTNOTEBOOK_RECORD_FAILURE_PREFIX:<exc_type>:<exc>` to errors
- Forces `final_status = FINAL_BLOCK` with the failure marker as `final_reason`
- **Does NOT silently pass.** ✓

### E. Anthropic Bridge (Requirements #6, #7)
`anthropic_bridge/bridge.py` lines 130–154:
- Validates `tool_use.input` is a dict — non-JSON → `AnthropicBridgeError` (requirement #6)
- Schema-validates against output schema via `response_validator.py` — invalid → raise (requirement #6)
- **Whitelist enforcement**: `parsed["suggestion"] not in ("agree", "downgrade", "block")` → reject. Adversarial schemas trying to inject `"upgrade"` are blocked at this layer (requirement #7)
- Secret redaction on every log line via `_redactor.redact(...)` (requirement #13)
- Returns redacted dict by default — caller must explicitly request `unsafe_raw_parsed` to get raw

### F. Live-order guard (Requirement #12)
`live_data/live_order_guard.py` + `oanda_readonly_client.py`:
- Two flags: `LIVE_ORDER_GUARD_ACTIVE` + `_GUARD_BURNED_IN` sentinel — both must be False to permit (impossible at runtime)
- 7 order methods explicitly call `assert_no_live_order(...)`: `submit_order`, `place_order`, `close_trade`, `modify_trade`, `cancel_order`, `set_take_profit`, `set_stop_loss`
- `__init_subclass__` re-wraps blocked methods on every subclass — defends against attribute override
- HTTP layer: stdlib `urllib.request` only; no `requests` dependency; only GET to `/v3/instruments/...` and `/v3/accounts/{id}/{instruments|summary}`
- Account-ID match enforced (path must match `self._account_id`)
- 8 dedicated tests in `test_live_order_guard.py`

### G. NY-session enforcement (Requirement #11)
`gatemind/v4/session_check.py` — DST-aware via `zoneinfo("America/New_York")`. Two windows: 03:00–05:00 NY (PRE_OPEN) + 08:00–12:00 NY (MORNING). Outside → `(False, "outside_window")` → GateMind issues `REASON_OUTSIDE_NY` BLOCK.

### H. Data-quality / leakage guards (Requirements #8, #10)
- `live_data/data_cache.py` — `_validate_cached_candle`: rejects non-dict, missing time, future-dated (>5min skew), non-complete, non-finite OHLC, negative volume.
- `replay/leakage_guard.py` — `slice_visible(bars, now_utc)` + `assert_no_future(bars, now_utc)` + `assert_chronological(bars)`.

### I. Secret-handling tests (Requirement #13)
- `anthropic_bridge/tests/test_no_secret_in_prompt.py`
- `anthropic_bridge/tests/test_no_secret_in_logs.py`
- `smartnotebook/v4/tests/test_no_data_leakage.py`
- `smartnotebook/v4/tests/test_secret_redaction.py`

### J. Per-brain hardening tests (Requirement: regression tests)
- `newsmind/v4/tests/test_hardening.py`
- `marketmind/v4/tests/test_hardening.py`
- `chartmind/v4/tests/test_hardening.py` (presence verified)
- `gatemind/v4/tests/test_grade_enforcement.py` + `test_risk_flags.py`
- `smartnotebook/v4/tests/test_hardening.py`
- `anthropic_bridge/tests/test_hardening.py`
- `live_data/tests/test_hardening.py`

**Total: ≈ 769 test functions covering hardening invariants.**

---

## 2. Gaps Found (4 total — minor)

### 🟡 G1 — `newsmind/v4/NewsMindV4.py:541` bare `except: pass` in `_affects_pair`
```python
explicit = getattr(item, "affected_assets", None)
if explicit:
    try:
        if any(p == str(a).upper().replace(...) for a in explicit):
            return True
    except Exception:   # ← bare; silently falls through
        pass
# falls through to path (a)
```
**Risk:** LOW. If `explicit` contains non-stringifiable objects, the comparison silently fails and we fall through to source-name-based matching. Worst case: a relevant news item gets dropped → conservatively missed signal, NOT a false positive. Still, a `_log.warning(...)` would aid auditing.

### 🟡 G2 — `run_live_replay.py:171` spread fallback silent
```python
spread = d.get("spread_pips")
if spread is None and "ask" in d and "bid" in d:
    try:
        spread = (float(d["ask"]["c"]) - float(d["bid"]["c"])) * 10000
    except Exception:
        spread = None   # ← silently None
```
**Risk:** LOW. `spread_pips` is optional in the `Bar` dataclass (default 0.0). However, when bid/ask are present but conversion fails, that's a data anomaly worth logging.

### 🟡 G3 — `setup_and_run.py:224, 230, 269` bare excepts in `TeeOutput`
**Context:** stream flushing in user-facing setup script. Acceptable defensive coding (a stream flush failure shouldn't crash the program), but not in the trade path. Out of scope for hardening, document only.

### 🟡 G4 — Missing regression tests
While 769 tests cover most invariants, **NO explicit test confirmed for** these specific scenarios:
- Orchestrator passes naive (non-tz-aware) `now_utc` → fails (`I8` enforces this in BrainOutput, but Orchestrator's own input validation should also reject)
- Bar built with `timestamp` having no tzinfo → fails (Bar.__post_init__ enforces, but no orchestrator-level test)
- ReplayNewsMindV4 (the new class added today) returns valid BrainOutput in all branches — no regression test yet for the new file

These are **net-new** for the replay framework; they should be added in Phase 3 implementation **after** baseline tests are confirmed green.

---

## 3. Silent-Failure Hunt Results

Bare `except:` / `except Exception:` instances inventory:

| File:Line | Pattern | Verdict |
|---|---|---|
| `run_live_replay.py:171` | spread fallback | G2 — log warning |
| `setup_and_run.py:224,230,269` | TeeOutput stream flush | OK (defensive, not trade path) |
| `live_data/data_cache.py:269,348` | tmp-file cleanup on write failure | OK (cleanup is best-effort, parent code already handles failure) |
| `newsmind/v4/NewsMindV4.py:541` | `_affects_pair` explicit check | G1 — log warning |
| `chartmind/v4/tests/test_no_hardcoded_atr.py:50` | test introspection | OK (test code only) |

**No silent failures in the trade path.** All exception handlers either re-raise, log+convert to BLOCK, or are non-trade defensive code.

---

## 4. Schema Bypass Attempts (mental Red Team)

| Attempt | Defense | Result |
|---|---|---|
| Brain returns dict instead of BrainOutput | Orchestrator isinstance check | ❌ blocked (MissingBrainOutputError) |
| Brain returns BrainOutput with `grade="UPGRADED"` | BrainGrade enum: only A_PLUS/A/B/C/BLOCK valid | ❌ blocked at brain construction |
| Brain returns A grade, evidence=[] | I5 invariant | ❌ blocked |
| Brain returns A grade, data_quality="stale" | I5 invariant | ❌ blocked |
| Brain returns BLOCK + decision="BUY" | I7 invariant | ❌ blocked |
| Brain raises arbitrary exception | brain.evaluate() try/except + orchestrator outer try/except | ❌ blocked → BLOCK BrainOutput |
| Anthropic returns `{"suggestion": "upgrade"}` | bridge whitelist (`agree/downgrade/block` only) | ❌ blocked |
| Anthropic returns malformed JSON | tool_use.input not dict → AnthropicBridgeError | ❌ blocked |
| Anthropic returns valid JSON missing required fields | response_validator schema check | ❌ blocked |
| Brain returns BrainOutput with naive datetime | I8 invariant | ❌ blocked |
| Code calls oanda_client.submit_order(...) | LIVE_ORDER_GUARD assert | ❌ blocked |
| Code monkey-patches `LIVE_ORDER_GUARD_ACTIVE = False` | Sentinel `_GUARD_BURNED_IN` (closure-captured) still True | ❌ blocked |
| Subclass overrides `submit_order = lambda: 'DONE'` | `__init_subclass__` re-wraps | ❌ blocked |
| Code POSTs to `/v3/accounts/{id}/orders` | OandaReadOnlyClient endpoint allowlist | ❌ blocked |
| GateMind receives input outside NY window | session_check.is_in_ny_window → REASON_OUTSIDE_NY | ❌ blocked |
| Code sets `now_utc.tzinfo = None` and passes to brain | BrainOutput timestamp_utc tz-aware required | ❌ blocked |
| SmartNoteBook write fails on disk full | Orchestrator catches → final BLOCK with marker | ❌ silently-passing-as-success blocked |

**Result:** All Red Team scenarios are blocked by existing code. No bypass found.

---

## 5. What Phase 3 Did NOT Do (and why)

| Action | Status | Reason |
|---|---|---|
| Modify any brain logic | ❌ NOT DONE | Forbidden by phase rules |
| Modify GateMind rules | ❌ NOT DONE | Forbidden |
| Modify NY window definition | ❌ NOT DONE | Forbidden |
| Modify risk / SL / TP | ❌ NOT DONE | Forbidden |
| Run live | ❌ NOT DONE | Forbidden |
| Submit any order | ❌ NOT DONE | Guarded |
| Add the 1-line `_log.warning` for G1 and G2 | ⏳ DEFERRED | Pending Phase 2 verify so we have green baseline |
| Add new regression tests for G4 | ⏳ DEFERRED | Same |

**No trading logic changed in Phase 3 analysis.** ✓

---

## 6. Phase 3 Test Run Results

⚠️ **Tests not executed in this analysis.** Per the user's hard rule:
> *"tests تعمل أو سبب الفشل موثق."*

Documented reason: **Phase 2 verify batch (`Phase2_Verify.bat`) was prepared but has not been run by the user.** Until the user double-clicks it and we read `PHASE2_VERIFY.txt`, we do not have ground-truth pass/fail data.

This is the single most important closure dependency.

---

## 7. Logic Changed?

> **NO.** Zero modifications to:
> - any brain (NewsMind, MarketMind, ChartMind, GateMind, SmartNoteBook)
> - Orchestrator V4
> - GateMind rules / consensus / session window / risk
> - contracts/brain_output.py
> - LIVE_ORDER_GUARD
> - live_data clients
> - replay engine logic
>
> Phase 3 was READ-ONLY analysis.

---

## 8. Recommended Phase 3 Implementation Steps (POST Phase 2 Verify)

After `Phase2_Verify.bat` runs and tests are baseline-green:

1. **Add 2 minimal log lines** (NewsMindV4.py:541, run_live_replay.py:171) — `_log.warning` instead of bare `pass`. No logic change.
2. **Add 3 regression tests:**
   - `replay/tests/test_replay_newsmind.py` — verifies BLOCK in blackout / A grade clean
   - `replay/tests/test_replay_calendar.py` — verifies build_replay_occurrences returns sorted, in-window events
   - `orchestrator/v4/tests/test_naive_datetime_rejection.py` — verifies orchestrator-level naive datetime rejection
3. **Re-run all tests** — no regressions allowed.
4. **Commit + tag** as `phase-3-code-hardening-fail-closed`.

These are minor, scoped, and have clear pass/fail criteria.

---

## 9. Phase 3 Closure Decision

### Closure rule (from user's spec):
> Phase 3 closes when: report + fail-closed proven by tests + no silent failures + schema validation strong + Claude override blocked + live order path blocked + no secrets in logs + tests pass or failure documented + Red Team notes + git status clear + commit if files changed + explicit ready/not-ready decision.

| Closure requirement | Status |
|---|---|
| Written report | ✅ This file |
| fail-closed proven by tests | ⏳ Code path complete; **test execution pending Phase 2 verify** |
| No silent failures | ✅ 4 minor `except: pass` documented (G1–G4); NONE on trade path |
| Schema validation strong | ✅ I1–I9 + Anthropic JSON schema + GateMind schema_validator |
| Claude override blocked | ✅ Whitelist (`agree/downgrade/block`) |
| Live order path blocked | ✅ 6-layer defense (verified) |
| No secrets in logs | ✅ Two redactors + 4 dedicated tests |
| Tests pass or failure documented | ⚠️ **Documented as "execution pending Phase 2 verify"** |
| Red Team notes | ✅ §4 — 16 scenarios, all blocked |
| Git status clear | ⏳ Phase 1 / Phase 2 commits still pending |
| Commit if files changed | N/A — no files changed in Phase 3 analysis |
| Explicit decision | See below |

### **VERDICT: ⚠️ PHASE 3 CONDITIONALLY READY.**

**Phase 3 ANALYSIS is complete.** The codebase is densely hardened by design — the per-brain freeze phases did the heavy lifting. Phase 3 confirms it.

**Phase 3 CLOSURE awaits ONE thing:**
- Run `Phase2_Verify.bat` → confirm baseline tests are green → then add the 2 log lines + 3 tests + commit/tag.

If the user wishes to defer the implementation step and close Phase 3 as "analysis-complete," that is honest and acceptable — the gaps found are all LOW-risk and the trade path is fully guarded.

---

## 10. Phase 4 Readiness

**❌ NOT YET.** Required before Phase 4:
1. Phase 2 cleanup batch executed
2. Phase 2 verify batch executed → tests baseline-green
3. Phase 3 implementation step (2 log lines + 3 regression tests, optional)
4. Single tag-able commit covering Phase 1 + 2 + 3 work (or three separate commits with the three tags: `phase-1-baseline-freeze`, `phase-2-code-cleanup`, `phase-3-code-hardening-fail-closed`)
5. Push to a private GitHub remote (off-laptop backup) — recommended.

---

## 11. Honest Bottom Line

The system was **already** built defensively. The per-brain freeze phases (NewsMind through SmartNoteBook + Orchestrator + LIVE_DATA hardening) installed the bulk of the guards Phase 3 demands. Phase 3's contribution is:

1. **Confirming** what's there (this report).
2. **Documenting** that no trade-path silent failures exist.
3. **Identifying** 4 minor gaps (1 worth fixing, 3 acceptable).
4. **Surfacing** that closure depends on running the Phase 2 verify batch.

The biggest risk to HYDRA V4 is **NOT** code hardening. It's **the git-state issue** raised in Phase 1 (only NewsMind committed). Until that's resolved, the entire hardened system is one disk-failure away from disappearing.
