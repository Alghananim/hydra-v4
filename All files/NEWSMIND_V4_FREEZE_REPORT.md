# NewsMind V4 — Freeze Report

**التاريخ:** 27 أبريل 2026
**الحالة:** ✅ **مُجمَّد (Frozen v4.0)**
**القاعدة:** كل كسور Red Team أُصلحت + ٤٩ اختبار يمرّ + صفر regressions.

---

## ١) مسار البناء (Phase A → E)

| المرحلة | الوكيل | النتيجة |
|---|---|---|
| A | V3 Legacy Audit | ✅ KEEP/REJECT/REBUILD لكل ملف V3 |
| B | Architecture + Contracts | ✅ Desktop\HYDRA V4 جاهز + BrainOutput contract |
| C | Build (24 file، ~2,600 LOC) | ✅ stdlib RSS + YAML loaders + Claude schema + 30 tests |
| D | Red Team هاجم | كسر ٤ نقاط (HIGH×1، MEDIUM×3) + bonus |
| Hardening | إصلاح + اختبارات إضافية | ✅ ٤٩ اختبار، صفر regressions |
| E | تجميد | ✅ هذا التقرير |

---

## ٢) ما تم استخراجه من V3

### KEEP (نسخ مع تعديل imports فقط)
- `freshness.py` — حالة عُمر الخبر، sane defaults
- `permission.py` — مصفوفة قرار + fail-CLOSED على الاستثناءات
- `chase_detector.py` — دالة pure لكشف chase social

### REBUILD من الصفر
- `sources.py` → stdlib `urllib + xml.etree`، أربع مصادر RSS حقيقية + JSON calendar
- `event_scheduler.py` → يحمّل `events.yaml` فعلاً (V3 ما حمّله أبداً)
- `intelligence.py` → `surprise_score` من `pip_per_sigma` بدل regex
- `NewsMindV4.py` → orchestrator نظيف بدون 3 nested try/except
- `llm_review.py` → Anthropic schema بـ `tool_choice` + audit_hash (downgrade-only)

### REJECT (لم يُنقَل)
- ٥ stub fetchers (`_do_fetch return []`)
- 17 من 27 حدث في `events.yaml` (احتفظنا فقط بـ EUR/USD + USD/JPY tier 1+2)
- حقول `published_at, received_at, conflicting_sources, sources_checked` (over-engineered)
- مسار LLM "approve/upgrade" (enum يحصره downgrade-only)
- Hardcoded `confidence=0.95` في V3 (الآن مشتق من حقائق ملاحَظة)

---

## ٣) ما بُني فعلياً (٢٤ ملف)

```
Desktop\HYDRA V4\
├── ENGINEERING_PROTOCOL.md       # القواعد الصارمة
├── README.md                     # وصف المشروع
├── NEWSMIND_V4_FREEZE_REPORT.md  # هذا الملف
├── contracts\
│   ├── __init__.py
│   └── brain_output.py           # BrainOutput contract — invariants
├── config\news\
│   ├── events.yaml               # 10 events (EUR/USD + USD/JPY فقط)
│   └── keywords.yaml             # كلمات مفتاحية حسب الزوج
└── newsmind\
    ├── __init__.py
    └── v4\
        ├── __init__.py
        ├── NewsMindV4.py         # Orchestrator
        ├── models.py             # NewsItem, NewsVerdict, EventSchedule
        ├── sources.py            # stdlib RSS + JSON calendar
        ├── config_loader.py      # YAML loader (with mini-YAML fallback)
        ├── event_scheduler.py    # blackout windows + active events
        ├── freshness.py          # KEEP من V3
        ├── permission.py         # KEEP من V3
        ├── chase_detector.py     # KEEP من V3
        ├── intelligence.py       # REBUILD: surprise from yaml
        ├── llm_review.py         # Anthropic adapter (v4.0 unwired by design)
        └── tests\
            ├── __init__.py
            ├── conftest.py
            ├── test_contract.py        # 11 tests
            ├── test_sources.py         # 8 tests
            ├── test_blackout.py        # 8 tests
            ├── test_evaluate_end_to_end.py  # 5 tests
            └── test_hardening.py       # 17 tests (Red Team fixes)
```

---

## ٤) Red Team — ما اكتشف وما أُصلح

### ٤ كسور مؤكدة (الكل مُصلَح + اختبارات ترصد)

| # | الخطورة | المشكلة | الإصلاح | الاختبار |
|---|---|---|---|---|
| **R1** | 🔴 HIGH | `is_in_blackout("EUR/USD", t)` يرجع False بسبب slash → blackout مكسور | `_normalize_pair` يُزيل `/`, `-`, `_`, مسافات + regex `^[A-Z]{6}$` | 4 tests |
| **R2** | 🟡 MEDIUM | `data_quality="good"` لـ items >6h عمر — كل المصادر "ok" لكن بلا أخبار جديدة | إضافة guard: لو `not summary.items and any_source_status_ok → "stale"` | 2 tests |
| **R3** | 🟡 MEDIUM | `BrainOutput(grade=A_PLUS, evidence=[""])` يقبل (string فارغ) | invariant: `[e for e in evidence if isinstance(e,str) and e.strip()]` | 4 tests |
| **R4** | 🟡 MEDIUM | `_affects_pair` يرجع True لأي source غير معروف → junk → grade A | `_KNOWN_PAIR_SOURCES` allowlist + fail-closed للمصادر غير المعروفة إلا لو فيها `affected_assets` صريحة | 4 tests |

### كسور إضافية (مُصلَحة)
- **R5**: `keywords.yaml` غير موجود يُبتلَع بصمت → الآن يُرفع FileNotFoundError
- **R6**: Test order contamination في `test_sources.py` → `importlib.reload` أُزيل
- **R7**: `llm_review.py` dead code → موثَّق رسمياً كـ `OPTIONAL v4.1`، TODO في orchestrator

---

## ٥) النتائج النهائية

```
============================== 49 passed ==============================

Breakdown:
  test_contract.py       : 11   (BrainOutput invariants)
  test_sources.py        :  8   (RSS, JSON, errors, no feedparser)
  test_blackout.py       :  8   (NFP/FOMC windows, A requires 2 confirmations)
  test_evaluate_e2e.py   :  5   (orchestrator, yaml loading, fail-closed)
  test_hardening.py      : 17   (R1-R7 regression guards)

  Tests added per Red Team fix: +17
  Tests baseline (post-build):   32
  Tests final (post-fix):        49
  Regressions:                    0
```

---

## ٦) ملاحظات صريحة (ما NewsMind V4 لا يستطيعه وحده)

١. **لا يفتح صفقة** — هذا دور GateMind. NewsMind V4 يُنتج `BrainOutput` فقط (BUY/SELL/WAIT/BLOCK + grade + evidence).
٢. **`surprise_score = 0.0` في live path** — A+ غير قابل للتحقيق على بيانات حية حتى نُضيف معايرة `pip_per_sigma` تاريخياً. **هذا fail-safe by design**.
٣. **Anthropic LLM unwired في v4.0** — بـ design. يمكن وصله في v4.1 بعد ما GateMind V4 يكون جاهز (لأن LLM downgrade-only يعمل فوق GateMind، مو داخله).
٤. **٥ مصادر RSS موصّلة** — Federal Reserve, ECB, BoJ, Faireconomy calendar, Forexlive. **لم تُختبَر live** (لا internet في sandbox). الاختبار الحقيقي على لابتوبك بعد المزامنة.
٥. **events.yaml** يحتوي ١٠ أحداث محتارة (NFP, CPI, FOMC, Powell, GDP، ECB rate, Lagarde, BoJ rate, Ueda، Fed minutes). يمكن توسيعها لاحقاً.

---

## ٧) القرار

**جاهز للانتقال إلى MarketMind V4.**

NewsMind V4:
- ✅ صمد أمام ٤ هجمات Red Team بعد الإصلاح
- ✅ contract enforced (A/A+ يحتاج evidence + good data)
- ✅ fail-CLOSED افتراضي
- ✅ stdlib only (لا feedparser، لا depend خارجي ثقيل)
- ✅ events.yaml يُحمَّل فعلاً
- ✅ tests شاملة (49)
- ✅ Red Team approved للتجميد

**التوصية**: أبقِ NewsMind V4 مُجمَّداً. لا تعديلات لاحقة على هذا العقل **حتى تُكمَل العقول الأربعة الباقية**. أي إصلاح يأتي من اكتشافات في GateMind/SmartNoteBook integration ينعكس **بـ commit منفصل بعد ربط النظام الكامل**.

**الخطوة التالية**: MarketMind V4، نفس البروتوكول (Audit → Build → Red Team → Freeze).

---

## ملحق: التوقيعات

- Git tag مقترح: `newsmind-v4.0-frozen`
- Commit hashes (في `Documents\hydra-v3` بعد المزامنة): tba بعد المزامنة الفعلية إلى Desktop\HYDRA V4 git repo (الحالي بيئة مستقلة).
- Test command: `cd Desktop\HYDRA V4 && python -m pytest newsmind\v4\tests\ -v`

**كلمة المنسّق:**
بُني بصرامة. هوجم بصرامة. صلح بصرامة. اختُبر بصرامة. الآن مجمَّد.
