# HYDRA V4 — Five-Minds Integration Report

**التاريخ:** 27 أبريل 2026
**الحالة:** ✅ **العقول الخمسة مرتبطة كجسم واحد** — Orchestrator V4 جاهز للتجميد
**القاعدة:** ٥ phases × ٢٠ Agent personas × ٩٤ integration test + ٥٣٨ brain test = **٦٣٢ test كلها خضراء**

---

## ١) كيف تم ربط العقول الخمسة

النظام يعمل الآن كجسم حيّ. الـ Orchestrator V4 (`orchestrator/v4/HydraOrchestratorV4.py`) هو **النخاع الشوكي** — يربط العقول الخمسة المُجمَّدة في dependency injection pattern:

```
                  Symbol + now_utc + bars_by_pair + bars_by_tf
                                    │
                                    ▼
                       ┌─────────────────────────────┐
                       │  HydraOrchestratorV4         │
                       │  (نخاع شوكي - الجهاز العصبي)│
                       │  cycle_id, sequencing,       │
                       │  loud failure propagation    │
                       │  threading.RLock for safety  │
                       └─────────────┬───────────────┘
                                     │
                                     ▼
                       ┌─────────────────────────────┐
                       │  NewsMindV4 (جهاز الإنذار) │
                       │  evaluate(pair, now_utc)    │
                       │  → BrainOutput              │
                       └─────────────┬───────────────┘
                                     │ news_out
                                     ▼
                       ┌─────────────────────────────┐
                       │  MarketMindV4 (الإحساس بالبيئة)│
                       │  evaluate(pair, bars,       │
                       │    now_utc, news_output=)   │
                       │  → MarketState              │
                       └─────────────┬───────────────┘
                                     │ market_out
                                     ▼
                       ┌─────────────────────────────┐
                       │  ChartMindV4 (العين)        │
                       │  evaluate(pair, bars_tf,    │
                       │    now_utc, news, market)   │
                       │  → ChartAssessment          │
                       └─────────────┬───────────────┘
                                     │ chart_out (3 BrainOutputs ready)
                                     ▼
                       ┌─────────────────────────────┐
                       │  GateMindV4 (القلب الأمني) │
                       │  3/3 + A/A+ + NY + kill-flag│
                       │  evaluate(news, market,     │
                       │    chart, now_utc, symbol)  │
                       │  → GateDecision             │
                       └─────────────┬───────────────┘
                                     │ gate_decision
                                     ▼
                       ┌─────────────────────────────┐
                       │  SmartNoteBookV4 (الذاكرة) │
                       │  - DECISION_CYCLE record    │
                       │  - GATE_AUDIT record        │
                       │  chain-hashed JSONL+SQLite  │
                       └─────────────┬───────────────┘
                                     │
                                     ▼
                            DecisionCycleResult
                            (returned to caller)
```

---

## ٢) مسار القرار من NewsMind إلى SmartNoteBook

`HydraOrchestratorV4.run_cycle()` ينفّذ **١٠ خطوات صارمة**:

```
1. _validate_inputs(symbol, now_utc, bars_by_pair, bars_by_tf)
   • now_utc tz-aware UTC (raise on naive)
   • now_utc not future > 5min (clock drift tolerance)
   • bars are non-None mappings

2. cycle_id = mint_cycle_id(now_utc)        # UUID مع ts prefix

3. news_out = NewsMind.evaluate(pair, now_utc)
   • timings_ms["news"] measured

4. market_out = MarketMind.evaluate(pair, bars_by_pair, now_utc, news_output=news_out)
   • يستهلك سياق NewsMind

5. chart_out = ChartMind.evaluate(pair, bars_by_tf, now_utc,
                                   news_output=news_out, market_output=market_out)
   • يستهلك سياق News + Market

6. gate_decision = GateMind.evaluate(news_out, market_out, chart_out, now_utc, symbol)
   • 3/3 unanimity + A/A+ + NY session + no kill-flag

7. final_status = _gate_outcome_to_final(gate_decision.gate_decision)
   • PURE 1:1 enum→string mapping (NO conditional gates)

8. with self._notebook_lock:                 # threading safety
       dcr = SmartNoteBook.record_decision_cycle(...)   # DECISION_CYCLE
       gar = SmartNoteBook.record_gate_audit(decision_cycle_id=dcr.record_id)  # linked

9. result = DecisionCycleResult(cycle_id, symbol, timestamp_utc, timestamp_ny,
                                 session_status, news_out, market_out, chart_out,
                                 gate_decision, dcr.record_id, gar.record_id,
                                 final_status, final_reason, errors=[], timings_ms)

10. _log.info("cycle_complete cycle_id=%s symbol=%s final=%s reason=%s")
    return result
```

---

## ٣) كيف يتم التحقق من output كل عقل

كل عقل يطبّق **fail-CLOSED** داخلياً ويُنتج `BrainOutput`-compatible:

| العقل | input validation | output validation |
|---|---|---|
| **NewsMind** | tz-aware now_utc (line 118) | NewsMindV4.py:286-297 يُرجع BrainOutput دائماً، حتى عند الفشل |
| **MarketMind** | bars dict + tz-aware (line 78, 104) | MarketState (BrainOutput subclass) — fail_closed على line 80 |
| **ChartMind** | bars_by_tf dict, M15 required (line 91) | ChartAssessment — fail_closed على lines 71-77, 92, 101, 114 |
| **GateMind** | 3 BrainOutputs، tz-aware (lines 64-70) | GateDecision (frozen), 8-rule short-circuit ladder |
| **SmartNoteBook** | الـ DCR/GAR contracts | append-only chain hash، LedgerWriteError loud |

**Orchestrator يتحقق إضافياً:**
- `isinstance(out, BrainOutput)` بعد كل brain call → MissingBrainOutputError إذا None/wrong type
- لا يلمس `.gate_decision` enum إلا في `_gate_outcome_to_final` (1:1 map)

---

## ٤) كيف يطبق GateMind القواعد

GateMind فيه **٨ قواعد short-circuit** (`gatemind/v4/rules.py`):

| Rule | الفحص | على فشل |
|---|---|---|
| **R1** Schema | كل BrainOutput صالح | `BLOCK(schema_invalid)` |
| **R2** Session | `now_ny` في {03:00-05:00, 08:00-12:00} | `BLOCK(outside_new_york_trading_window)` |
| **R3** Grade | كل grade في {A, A+} | `BLOCK(grade_below_threshold)` |
| **R4** Brain block | لا brain.should_block | `BLOCK(brain_block)` |
| **R5** Kill flag | لا kill-class flag | `BLOCK(kill_flag_active)` |
| **R6** Direction | كل directions متفقة | `BLOCK(directional_conflict)` |
| **R7** Unanimous WAIT | الكل WAIT | `WAIT(unanimous_wait)` |
| **R8** ENTER | الكل ENTER نفس الاتجاه + R1-R6 نجحت | `ENTER_CANDIDATE` |

**القاعدة:** Orchestrator لا يلمس هذه القواعد. يستلم النتيجة فقط.

---

## ٥) كيف يسجل SmartNoteBook كل شيء

كل decision cycle يخلق **سجلين مرتبطين**:

### DECISION_CYCLE Record
```json
{
  "record_id": "<UUID>",
  "record_type": "DECISION_CYCLE",
  "timestamp_utc": "2026-04-27T13:30:00Z",
  "timestamp_ny": "2026-04-27T09:30:00",
  "sequence_id": 42,
  "chain_hash": "<HMAC-SHA256>",
  "prev_hash": "<previous chain_hash>",
  "symbol": "EUR_USD",
  "session_window": "morning_3_5",
  "newsmind_output": {full BrainOutput dict},
  "marketmind_output": {full MarketState dict},
  "chartmind_output": {full ChartAssessment dict},
  "gatemind_output": {full GateDecision dict},
  "final_status": "ENTER_CANDIDATE | WAIT | BLOCK",
  "blocking_reason": "<reason if BLOCK>",
  "evidence_summary": [list of evidence strings],
  "risk_flags": [list of flags],
  "data_quality_summary": {per-mind dq},
  "model_versions": {per-mind versions}
}
```

### GATE_AUDIT Record (linked to DECISION_CYCLE via parent_record_id)
```json
{
  "record_id": "<UUID>",
  "record_type": "GATE_AUDIT",
  "parent_record_id": "<DECISION_CYCLE.record_id>",
  "audit_id": "gm-<ts>-<symbol>-<hash>",
  "gate_decision": {full GateDecision dict},
  "audit_trail": [ladder evaluation],
  "model_version": "gatemind-v4.0"
}
```

**ضمانات:** chain_hash مع HMAC (فعّل بـ `HYDRA_NOTEBOOK_HMAC_KEY`) → forge-resistance. `verify_chain_for_day()` يكشف tampering.

---

## ٦) ماذا يحدث إذا فشل عقل

| السيناريو | السلوك |
|---|---|
| NewsMind raises Exception | كل brain له fail-CLOSED داخلي يُرجع BrainOutput(BLOCK). Orchestrator يمرّر BLOCK إلى المرحلة التالية. final = BLOCK. |
| NewsMind يُرجع None أو non-BrainOutput | `MissingBrainOutputError` raised في run_cycle. Orchestrator يُرجع DecisionCycleResult(ORCHESTRATOR_ERROR) + يسجّل في SmartNoteBook كـ BLOCK مع `blocking_reason="orchestrator_error:MissingBrainOutputError"`. |
| MarketMind بدون cross-asset bars | MarketState(grade=B, data_quality="missing"). GateMind R3 → BLOCK. |
| ChartMind invalid schema | فشل يُكتشف من GateMind R1 → BLOCK(schema_invalid). |
| GateMind raises | fail_closed → GateDecision(BLOCK). |
| SmartNoteBook write fails | **after O1 hardening**: try/except → DecisionCycleResult(BLOCK, blocking_reason="smartnotebook_record_failure:..."). Cycle data NOT lost. |

---

## ٧) كيف تم منع silent failure

١. **كل brain له fail-CLOSED داخلي** يُرجع BLOCK BrainOutput (لا exception silently swallowed).
٢. **Orchestrator لا يلف brain.evaluate() في try/except واسع** — يدع الـ BLOCK BrainOutputs تمرّ. الـ try/except الوحيد للأخطاء غير المتوقّعة (non-BrainOutput exceptions).
٣. **`MissingBrainOutputError`** raised إذا brain يُرجع None → propagation فورية.
٤. **SmartNoteBook write failure** يُحوَّل إلى DecisionCycleResult(BLOCK) — لا exception silently lost (O1 hardening).
٥. **`_log.info("cycle_complete...")`** عند كل return → audit trail.
٦. **`errors` list** في DecisionCycleResult — لا فشل بدون توثيق.

---

## ٨) كيف تم منع Claude override

١. **GateMind لا يستدعي LLM** في الـ ladder الـ ٨ قواعد. القرار deterministic ١٠٠٪.
٢. **Claude is downgrade-only** — `LLMOverride` enum يحتوي فقط `{NO_CHANGE, DOWNGRADE_TO_WAIT, DOWNGRADE_TO_BLOCK}`. لا `UPGRADE` أبداً.
٣. **`apply_llm_review` يرفض suggestion="upgrade"** بـ `PermissionError`.
٤. **Orchestrator's `_gate_outcome_to_final`** هو 1:1 enum→string map (NO conditional). أي محاولة لرفع WAIT→ENTER عبر تعديل GateDecision ستفشل في `DecisionCycleResult.__post_init__` (ENTER_CANDIDATE invariant).
٥. **`test_no_override_gate.py` (4 tests) + `test_claude_safety.py` (5 tests)** يثبتان أن لا path يسمح برفع القرار.

---

## ٩) كيف تم منع live orders

١. **`orchestrator_constants.FORBIDDEN_IMPORTS`** يحظر: `oanda`, `requests`, `urllib`, `httpx`, `socket`, `subprocess`, `aiohttp`, `anthropic`, `openai`.
٢. **Static scan في `test_no_live_order.py`** يفشل إذا أي ملف في `orchestrator/v4/*.py` يستورد منهم.
٣. **GateMind و SmartNoteBook كلاهما frozen** بدون broker SDK.
٤. **No `submit_order` / `place_order` / `buy_market`** في أي ملف (regex check).
٥. **`DecisionCycleResult`** و **`TradeCandidate`** لا يحويان `order_id` / `lot_size` / `execution_status`.

التنفيذ الفعلي مسؤولية **Risk/Execution layer** (out of scope في V4).

---

## ١٠) نتائج اختبارات الربط

```
Total V4 tests:
  NewsMind V4:      49 tests
  MarketMind V4:    116+ tests
  ChartMind V4:     120 tests
  GateMind V4:      138 tests
  SmartNoteBook V4: 115 tests
  ─────────────────────────
  Subtotal:         538 tests

  Orchestrator V4:   94 tests (79 build + 15 hardening)
  ─────────────────────────
  Total HYDRA V4:   632 tests
```

### ١٥ سيناريوهات Integration (test_evaluate_e2e.py)

| # | السيناريو | المتوقّع |
|---|---|---|
| 1 | كلهم A+ BUY في NY window | ENTER_CANDIDATE BUY |
| 2 | كلهم A SELL في NY | ENTER_CANDIDATE SELL |
| 3 | Mixed A و A+ BUY | ENTER_CANDIDATE BUY |
| 4 | كلهم WAIT | WAIT(unanimous_wait) |
| 5 | 2 BUY + 1 WAIT | BLOCK(incomplete_agreement) |
| 6 | 2 BUY + 1 SELL | BLOCK(directional_conflict) |
| 7 | ChartMind grade=B | BLOCK(grade_below_threshold) |
| 8 | NewsMind kill_flag | BLOCK(kill_flag_active) |
| 9 | ChartMind invalid type | MissingBrainOutputError → BLOCK |
| 10 | خارج NY window | BLOCK(outside_new_york_trading_window) |
| 11 | DECISION_CYCLE recorded | جميع الـ ٤ outputs محفوظة |
| 12 | GATE_AUDIT linked | parent_record_id يطابق |
| 13 | cycle_id unique | UUID4 مع ts prefix |
| 14 | لا writes خارج SmartNoteBook | static check |
| 15 | لا oanda/requests imports | static check |
| **16 (hardening)** | Real R1 schema_invalid path | BLOCK(schema_invalid) |

---

## ١١) ماذا كسر Red Team

Red Team هاجم ١٨ vectors. **٣ نجحوا قبل hardening:**

| Attack | Severity | الحالة |
|---|---|---|
| **A6**: SmartNoteBook write failure on happy path | MEDIUM | مُصلَح في **O1** (try/except + return BLOCK) |
| **A10**: Concurrent run_cycle no thread-safety | MEDIUM | مُصلَح في **O2** (`threading.RLock`) |
| **A5**: No future-timestamp sanity | LOW | مُصلَح في **O5** (5-min tolerance) |

**Multi-Reviewer كشف ٦ إضافية:**
- O3: final_status divergence (FIXED — `orchestrator_error:` prefix)
- O4: scenario 09 mislabel (FIXED — renamed + added test_16)
- O6: timing measurement test was tautological (FIXED — real time.sleep test)
- O7: Magic numbers + dead imports (FIXED — constants + cleanup)
- O8: No INFO log at decision boundary (FIXED — `_log.info("cycle_complete...")`)
- O9: Stricter injection (FIXED — `strict=True` flag)

**Red Team final verdict (post-hardening): A** — system held under attack.

---

## ١٢) ماذا تم إصلاحه

كل O1-O9 مُصلَح بـ:
- diff واضح (~140 سطر إضافي في HydraOrchestratorV4.py)
- ١٥ regression test جديد في `test_orchestrator_hardening.py` + `test_evaluate_e2e.py::test_16`
- صفر regressions في الـ ٥ frozen brain test suites

---

## ١٣) قابلية التطوير

النظام مصمَّم بمبدأ **dependency injection**:

```python
HydraOrchestratorV4(
    smartnotebook_base_dir=...,
    newsmind=NewsMindV4() or custom,
    marketmind=MarketMindV4() or custom,
    chartmind=ChartMindV4() or custom,
    gatemind=GateMindV4() or custom,
    smartnotebook=SmartNoteBookV4(...) or custom,
    strict=True  # production
)
```

**يمكن إضافة لاحقاً:**
- ✅ أزواج جديدة (GBPUSD، AUDUSD) — `symbol` parameter بدون كود إضافي
- ✅ Backtester V4 — يستهلك Orchestrator في loop مع historical bars
- ✅ Risk/Execution layer — يستهلك `DecisionCycleResult.gate_decision.trade_candidate`
- ✅ Dashboard — يقرأ من SmartNoteBook reports
- ✅ Live monitoring — `_log.info` boundary

**يتطلب refactor طفيف:**
- إضافة عقل سادس (مثل MacroMind) — `run_cycle` فيه hardcoded for 5 brains. يحتاج plugin registry.

---

## ١٤) ما الذي بقي قبل الانتقال للمراحل التالية

١. **Run_HYDRA_V4.bat** — script تشغيل بنقرة واحدة (موجود الآن في Desktop)
٢. **Freeze_Integration_V4.bat** — يجمّد المرحلة بـ git tag `hydra-v4.0-integrated` (موجود)
٣. **All files** folder reorganization — اختياري للوضوح، لا ضرورة للكود

---

## ١٥) القرار النهائي

**HYDRA V4 Five-Minds Integration: COMPLETE** ✅

النظام:
- ✅ ٥ عقول مُجمَّدة + Orchestrator V4 جاهز للتجميد
- ✅ الجسم الحيّ: news → market → chart → gate → notebook
- ✅ ٦٣٢ test (٥٣٨ brain + ٩٤ orchestrator)
- ✅ Red Team verdict: A (post-hardening)
- ✅ Multi-Reviewer 5-personas + Truth Verification + Scalability check
- ✅ Zero broker calls, zero LLM upgrade, zero silent failures
- ✅ Thread-safe, fail-CLOSED, audit-chain-hashed
- ✅ Dependency-injectable for tests + production
- ✅ Forward-compatible for backtest, dashboard, execution layer

**جاهز للمرحلة التالية**: Backtester V4 على بيانات OANDA حقيقية مع `verify_chain` لكل decision cycle.

---

## إحصائيات HYDRA V4 الكلية النهائية 🎉

| Component | حالة | Tests | Tag |
|---|---|---|---|
| BrainOutput contract | 🔒 Locked | — | shared |
| **NewsMind V4** | 🔒 Frozen | 49 | `newsmind-v4.0-frozen` |
| **MarketMind V4** | 🔒 Frozen | 116+ | `marketmind-v4.0-frozen` |
| **ChartMind V4** | 🔒 Frozen | 120 | `chartmind-v4.0-frozen` |
| **GateMind V4** | 🔒 Frozen | 138 | `gatemind-v4.0-frozen` |
| **SmartNoteBook V4** | 🔒 Frozen | 115 | `smartnotebook-v4.0-frozen` |
| **Orchestrator V4** | 🔒 جاهز للتجميد | **94** | `orchestrator-v4.0-integrated` (pending) |
| **HYDRA V4 (overall)** | 🟡 جاهز للتجميد | **632** | `hydra-v4.0-integrated` (pending) |

**العقول الخمسة الآن مرتبطة كجسم واحد حيّ، لا خمسة أعضاء مفككة.**
