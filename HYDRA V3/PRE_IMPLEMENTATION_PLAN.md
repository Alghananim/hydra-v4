# HYDRA V3 — تقرير ما قبل التنفيذ

**التاريخ:** 27 أبريل 2026
**الهدف:** فهم النظام بدقة، تحديد الفجوات بين الواقع والمواصفات الجديدة، تصميم باكتيستر احترافي، طلب الإذن قبل أي تنفيذ.
**القاعدة:** لا سطر كود قبل الموافقة على هذا التقرير.

---

## ١) ملخص فهم النظام (بالأدلة من الكود)

### ١.١ البنية المعمارية الفعلية

النظام يتكوّن من ٥ عقول مستقلّة + منسّق + بوابة + ذاكرة + طبقة LLM اختيارية. كل عقل يعمل بمعزل ولا يستورد من عقل آخر. الالتقاء حصري داخل `EngineV3.decide_and_maybe_trade()`.

```
hydra-v3/
├── chartmind/v3/         العقل #١  (٢٥ ملف، ~2,476 سطر)
├── marketmind/v3/        العقل #٢
├── newsmind/v3/          العقل #٣
├── gatemind/v3/          البوابة + alignment + decision_engine
├── smartnotebook/v3/     الذاكرة (SQLite + JSONL)
├── engine/v3/            EngineV3 + safety_rails (12 فحص) + position_sizer
├── llm/                  openai_brain.py حالياً (OpenAI، يحتاج adapter لـ Anthropic)
├── config/news/          YAML: events / sources / narratives / keywords
├── Backtest/             ٢١ ملف — باكتيست **ChartMind فقط** (انظر الفجوة #٣)
└── main_v3.py            نقطة الدخول (حلقة polling)
```

### ١.٢ مدخلات/مخرجات كل عقل (بالأدلة)

| العقل | المدخل | المخرج | المرجع |
|---|---|---|---|
| **NewsMind V3** | `now_utc`, `recent_bars`, `current_bar` + داخلياً `calendar`, `sources` | `NewsVerdict {grade, permission, bias, blackout, ...}` | `newsmind/v3/NewsMindV3.py:87` |
| **MarketMind V3** | `pair`, `news_verdict`, شموع + كروس-أصول (DXY/RORO) | `MarketAssessment {grade, permission, direction, regime, ...}` | `marketmind/v3/MarketMindV3.py:73` |
| **ChartMind V3** | شموع `M15` (إلزامي ≥6) + M5/M1 اختياري + الزوج + الوقت | `ChartAssessment {grade, permission, direction, trade_plan, SL/TP, ...}` | `chartmind/v3/ChartMindV3.py:51-66` |
| **GateMind V3** | `BrainSummary` لكل عقل + account state + signal + news_decision | `GateDecision {final_decision, audit_id, blocking_reasons, ...}` | `gatemind/v3/GateMindV3.py` |
| **SmartNoteBook V3** | كل القرارات + `audit_id` + `mind_outputs` | يخزّن في SQLite + JSONL | `smartnotebook/v3/SmartNoteBookV3.py` |

### ١.٣ قواعد GateMind الحالية (بالنص من الكود)

> **هام جداً:** هذه هي القواعد المُنفَّذة فعلياً في الكود اليوم. ستحتاج تعديلاً لمطابقة مواصفاتك الجديدة.

من `gatemind/v3/decision_engine.py:5-10`:
```
1. Hard BLOCKS — any one fires → block
2. Hard WAITS — any one fires → wait
4. Default: wait
No silent allow. No bypass. B grade always = wait. C grade always = block.
```

من `gatemind/v3/decision_engine.py:79-81`:
```python
if news.grade == "B": waiting.append("news_grade_B")
if market.grade == "B": waiting.append("market_grade_B")
if chart.grade == "B": waiting.append("chart_grade_B")
```

من `gatemind/v3/alignment.py:24-30`:
```python
clear = [d for d in directions if d in ("bullish", "bearish")]
if len(clear) >= 2 and len(set(clear)) == 1:
    # 2 من 3 يكفون لاعتبار الاتفاق "aligned"
    return {"status": "aligned", ...}
```

### ١.٤ الفجوة بين الكود الحالي والمواصفات الجديدة

| البند | المواصفات الجديدة | الكود الحالي | الحكم |
|---|---|---|---|
| B → block | نعم، B = ممنوع | B = wait (انتظار، ليس منع) | **يحتاج تعديل في decision_engine** |
| اتفاق ٣ من ٣ | إلزامي | يكفي ٢ من ٣ | **يحتاج تعديل في alignment.py** |
| A+ أو A فقط | إلزامي | ضمنياً مدعوم (B → wait) لكن غير مفروض كـ block | تأكيد + تشديد |
| عقل واحد B → block | إلزامي | حالياً wait | **يحتاج تعديل** |

### ١.٥ مواقع المشاكل الحرجة من تدقيق سابق (`HYDRA_V3_AUDIT.md`)

١. **NewsMind لا يجلب أخبار**: `newsmind/v3/sources.py:62-90` كل `_do_fetch` ترجع `[]`.
٢. **`engine/v3/main_v3.py:50-60`**: حلقة heartbeat فقط، لا OANDA candles ولا تنفيذ. تعليق صريح: `"For now: idle"`.
٣. **`EngineV3.decide_and_maybe_trade`** يحقن `atr=0.001` و `entry_price=1.0` صلبين (`EngineV3.py:155, 158`) → خطأ منهجي.
٤. **عدّادات الحماية في الذاكرة**: `daily_loss_pct`, `consecutive_losses`, `trades_today` لا تُحفَظ → fail-open عند restart.
٥. **طبقة LLM موصولة لكن `EngineV3.decide_and_maybe_trade` لا يستدعي `review_brain_outputs`** → أيّ مفتاح API يُهدر.
٦. **`integration_proof.py`**: السيناريوهات الخمسة كلها تتوقّع `block` — لا اختبار positive end-to-end.

---

## ٢) خريطة تدفق القرار

### ٢.١ التسلسل لكل دورة (بمراجع الأسطر)

```
┌────────────────────────────────────────────────────────────────────┐
│  EngineV3.decide_and_maybe_trade(pair, recent_bars, account, ...) │
│  (engine/v3/EngineV3.py:124-200)                                  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  ١. NewsMind.evaluate(now_utc, recent_bars)                        │
│     → NewsVerdict {grade, permission, bias, blackout}             │
│     (newsmind/v3/NewsMindV3.py:87)                                │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  ٢. MarketMind.assess(pair, news_verdict, ohlc, cross_assets)      │
│     → MarketAssessment {grade, permission, direction, regime}      │
│     (marketmind/v3/MarketMindV3.py:73)                            │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  ٣. ChartMind.assess(bars_M15, bars_M5, bars_M1, pair, now_utc)    │
│     → ChartAssessment {grade, permission, direction, plan, SL/TP} │
│     (chartmind/v3/ChartMindV3.py:51-66)                           │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ تُحوَّل كل واحدة إلى BrainSummary موحَّد
                              │
┌────────────────────────────────────────────────────────────────────┐
│  ٤. GateMindV3.decide(news_brief, market_brief, chart_brief,       │
│                        account, signal, news_decision)             │
│     ٤.١  alignment.check()      → aligned/conflicting/partial      │
│     ٤.٢  decision_engine.decide() → blocking/waiting/enter        │
│     ٤.٣  risk_check, session, news_gate, execution, state         │
│     → GateDecision {final_decision, audit_id, reasons}            │
│     (gatemind/v3/GateMindV3.py)                                   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
       ┌──────────────────────┴──────────────────────┐
       │                                             │
   final == "enter"                          final != "enter"
       │                                             │
       ▼                                             ▼
┌───────────────┐                          ┌──────────────────┐
│ safety_rails  │                          │ SmartNoteBook    │
│ (12 check)    │                          │ .record_decision │
│ engine/v3/    │                          │ (audit_id +      │
│ safety_rails  │                          │  reasons)        │
│ .py           │                          └──────────────────┘
└───────────────┘
       │
       ▼
┌───────────────┐
│ position_sizer│
│ + broker.exec │
└───────────────┘
       │
       ▼
┌──────────────────┐
│ SmartNoteBook    │
│ .record_decision │
│ (event=trade)    │
└──────────────────┘
```

### ٢.٢ نقاط الإخفاق الحالية في التدفق

- **بعد NewsMind**: لا أخبار حقيقية تصل (مصادر فارغة) → القرار مبني على `calendar` فقط.
- **داخل MarketMind**: `cross_assets` (DXY/SPX/الذهب) غير مُمرَّرة من Engine → assesses with empty fallback.
- **داخل GateMind**: `risk_check` يستلم `atr=0.001` صلب → كل JPY يُرفض كـ stop_too_wide.
- **بعد GateMind**: لا استدعاء لـ `llm.review_brain_outputs` → طبقة LLM معطّلة فعلياً.
- **داخل SmartNoteBook**: العدّادات في RAM، لا persistence على القرص.

---

## ٣) موقع الباكتيستر داخل HYDRA V3

### ٣.١ تحليل الوضع الحالي

موجود حالياً مجلد `Backtest/` (٢١ ملف) فيه:
- `runner.py` — حلقة backtest سليمة لكن **تستخدم ChartMind وحده**، لا تستخدم Engine V3 ولا توافق العقول الخمسة. يقول التعليق صراحة: `Calls ChartMind directly`.
- `data.py` — يجلب بيانات OANDA M15 مع bid/ask، يخزّن في JSONL — **بنية تحتية ممتازة قابلة لإعادة الاستخدام**.
- `calendar.py` — `HistoricalCalendar` لتقويم الأحداث — **مفيد جداً**، يمكن وصله بـ NewsMind.
- `costs.py` — نموذج تكلفة واقعي (spread + slippage) — **نُبقيه**.
- `risk.py`, `session.py`, `regime.py`, `variants.py` — أدوات بحثية، نُبقيها.

### ٣.٢ الفجوة الحرجة

**الباكتيست الحالي يختبر ChartMind فقط، ليس النظام الخماسي.** هذا يعني أن أي نتيجة نحصل عليها لا تعكس قواعدك الجديدة (B → block + ٣ من ٣ اتفاق).

### ٣.٣ التصميم المقترح

نُنشئ مجلداً جديداً `backtest_v2/` (دون لمس `Backtest/` الحالي) بمبدأ صارم:

> **الباكتيست هو HARNESS يُغلِّف Engine V3، ليس نظاماً موازياً.**

```
backtest_v2/
├── __init__.py
├── runner.py              # الحلقة الرئيسية — تُغذّي EngineV3 ببيانات تاريخية
├── data_provider.py       # يعيد استخدام Backtest/data.py (OANDA M15 cached)
├── replay_clock.py        # ساعة افتراضية تتحرك bar-by-bar
├── news_replay.py         # يعيد تشغيل أخبار تاريخية إلى NewsMind (إن توفّرت)
├── cross_asset_replay.py  # DXY/SPX/Gold تاريخية لـ MarketMind
├── account_simulator.py   # محاكي حساب OANDA (balance, positions, fills)
├── broker_replay.py       # broker مزيّف يُغذّي الفّيلز إلى SmartNoteBook
├── metrics.py             # win_rate / PF / DD / per-brain accuracy
├── leak_detector.py       # يضمن لا lookahead — كل bar[t] يرى فقط ≤ t
├── reporter.py            # تقرير قبل/بعد لكل تعديل
├── fixtures/              # سيناريوهات edge cases
└── tests/
    ├── test_no_lookahead.py
    ├── test_engine_parity.py     # نفس Engine المستخدم في live
    └── test_strict_gate_rules.py
```

### ٣.٤ المبدأ الصارم: ZERO DUPLICATION

الباكتيست **لا يحتوي على أي منطق قرار**. كل الذكاء داخل العقول الخمسة + GateMind. الباكتيست:
1. يقرأ شمعة تاريخية من cache.
2. يبني حالة `account` افتراضية.
3. يستدعي `EngineV3.decide_and_maybe_trade(...)` — **نفس الدالة المُستخدمة في live**.
4. يستلم القرار، يحاكي التنفيذ في `BrokerReplay`.
5. يسجّل النتائج في SmartNoteBook (نفس الـ DB سواءً live أو backtest، مع علامة `mode='backtest'`).

هذا يضمن:
- **Production parity**: أي تحسين في live يظهر في backtest فوراً.
- **No data leakage by construction**: كل bar[t] يدخل، Engine يقرّر، ينتقل bar[t+1].
- **Causal integrity**: الـ entry على bar[t]'s close يُنفَّذ على bar[t+1]'s open.

---

## ٤) الملفات اللي راح أراجعها قبل التنفيذ (Read-Only Review)

### ٤.١ مسار القرار (أولوية ١)
- `engine/v3/EngineV3.py` — تأكيد التدفق، تحديد مواقع `atr=0.001`, `entry_price=1.0`
- `engine/v3/safety_rails.py` — جميع الـ ١٢ فحص + شروط الفشل
- `engine/v3/position_sizer.py` — منطق الحجم
- `engine/v3/validation_config.py` — الحدود الصلبة (0.25%/0.5% caps)
- `gatemind/v3/decision_engine.py` — قواعد B→wait (سنغيّرها إلى block)
- `gatemind/v3/alignment.py` — منطق ٢ من ٣ (سنغيّره إلى ٣ من ٣)
- `gatemind/v3/risk_check.py` — كيف يُحسب الـ stop
- `gatemind/v3/news_gate.py` — كيف يُترجم news.permission إلى block

### ٤.٢ منتج كل عقل (أولوية ٢)
- `chartmind/v3/ChartMindV3.py` + `permission_engine.py` — سُلَّم الدرجات
- `marketmind/v3/MarketMindV3.py` + `permission_engine.py`
- `newsmind/v3/NewsMindV3.py` + `permission.py` + `intelligence.py`
- `smartnotebook/v3/SmartNoteBookV3.py` + `storage.py` + `models.py`

### ٤.٣ بيانات + قنوات (أولوية ٣)
- `Backtest/data.py` — كاش OANDA M15
- `Backtest/calendar.py` — HistoricalCalendar
- `Backtest/costs.py` — spread + slippage model
- `newsmind/v3/sources.py` — لماذا `_do_fetch` ترجع `[]` (لإصلاحها مع Anthropic-driven scraping أو RSS feedparser)
- `llm/openai_brain.py` — لكتابة `anthropic_brain.py` بنفس الواجهة

### ٤.٤ تحقّق نهائي (أولوية ٤)
- `engine/v3/integration_proof.py` — ٥ سيناريوهات block فقط (نضيف positive)
- `engine/v3/cert_pre_live.py` — شهادة قبل live

---

## ٥) المخاطر اللي أراها

| # | الخطر | الاحتمالية | الأثر | تخفيف |
|---|---|---|---|---|
| **R1** | تشديد GateMind إلى ٣ من ٣ + لا B = صفر صفقات في الباكتيست | عالية | الباكتيست لا يعطي أرقام، لا قرار | إصلاح أنابيب البيانات أولاً (NewsMind RSS + cross-assets)؛ توقُّع ١٠-٣٠ صفقة/سنة، ليس ٥٠٠ |
| **R2** | بدون أخبار حقيقية، NewsMind دائماً `permission=allow` (fail-safe) → القاعدة الجديدة "كل عقل A أو A+" تصير ChartMind+MarketMind فقط | عالية | الـ "٣ من ٣" يصير "٢ من ٢ + 1 صامت" | يجب توثيق أن NewsMind في mode silent يعتبر "قبول مشروط" أو "missing → block" بصرامة |
| **R3** | بيانات DXY/SPX/الذهب التاريخية غير متوفّرة في `Backtest/data.py` (الكود يقول EUR/USD only) | عالية | MarketMind يفتقد cross-assets → grade C دائماً | إضافة data_provider متعدّد الأصول، أو fallback synthetic DXY (موجود في `marketmind/v3/synthetic_dxy.py`) |
| **R4** | Lookahead bias في الباكتيست — استخدام بيانات bar[t+1] أثناء قرار bar[t] | متوسط | نتائج مُضخَّمة | enforce by structure: signal phase ≠ fill phase. اختبار `test_no_lookahead.py` |
| **R5** | Survivorship bias — ربما 2024-2026 fortunate | منخفض-متوسط | overfitting زمني | walk-forward 8 ربعيات (موجود في scripts) — تطبيقه على Engine V3 الكامل |
| **R6** | تكلفة Anthropic API في الباكتيست — كل صفقة محتملة تستدعي Claude | متوسط | تكلفة ~$2-5 لكل ١٠٠٠ bar مع LLM-on | mock LLM في الباكتيست (يُعيد neutral severity) كخطوة أولى، ثم backtest واقعي مع cache |
| **R7** | تغيير قواعد GateMind بدون دليل = خرق توجيهك | عالية لو لم نلتزم | فقدان الثقة | لن أغيّر شيئاً قبل: (أ) تأكيدك، (ب) إثبات الباكتيست تحسناً |
| **R8** | عدّادات الحماية في RAM → الباكتيست يُسبّب reset غير واقعي | متوسط | DD يبدو أصغر مما هو فعلاً | ربط الباكتيست بـ `notebook.storage` لتخزين العدّادات مثل live |

---

## ٦) الفرضيات الأولية

> **القاعدة:** كل فرضية لازم نختبرها بدليل من الباكتيست. لا قبول بدون تحقّق.

| # | الفرضية | كيف نختبرها |
|---|---|---|
| **H1** | تشديد إلى "ALL 3 must be A/A+" يقلّص الصفقات بنسبة ٨٠-٩٠٪ ويرفع win rate من ~36% إلى ~55%+ | باكتيست متوازي: loose-mode (الكود الحالي) vs strict-mode (المواصفات الجديدة) على نفس البيانات. مقارنة count, WR, PF, DD. |
| **H2** | EUR/USD سيمتلك صفقات strict أكثر بكثير من USD/JPY (سبب: spread أقل + microstructure مناسبة) | تقسيم النتائج per-pair |
| **H3** | بدون LLM (mechanical-only)، النتائج ستكون أسوأ مما كانت في loose-mode (السبب: LLM يخفّض، لا يرفع — وفي strict-mode هو "خطوة احتياطية" أكثر منه فلتر) | باكتيست strict-mechanical vs strict+LLM-on. التوقّع: LLM-on يقلّل ٢-٥٪ صفقات إضافية ويتحسّن WR قليلاً |
| **H4** | إذا NewsMind ساكت (مصادر فارغة)، القاعدة "ALL 3 must agree" فعلياً تصير "ChartMind + MarketMind agree" → ضعف الإحكام | اختبار: قارن نتائج (NewsMind silent) vs (NewsMind injected with calendar-only blackouts) — إذا الفرق كبير، إصلاح NewsMind sources أولوية حرجة |
| **H5** | الـ session filter `kill_asia` (المُثبَت في AUDIT) لا يزال له edge في النظام الخماسي الجديد | تطبيقه كفلتر إضافي في الباكتيست والمقارنة |
| **H6** | `atr=0.001` الصلب في `EngineV3.py:155` يكسر USD/JPY (pip = 0.01)، فبعد إصلاحه USD/JPY يصير قابلاً للتداول | اختبار قبل/بعد الإصلاح على USD/JPY فقط |

---

## ٧) خطة التنفيذ (مقسّمة لـ ٧ مراحل، كل مرحلة لها معيار قبول)

### مرحلة ٠ — Pre-flight (لا تغييرات في الكود)
- [ ] قراءة كل الملفات في القائمة (٤)
- [ ] إنشاء snapshot للـ git (`git tag v3-baseline-pre-engineering`)
- [ ] التأكد إن HYDRA V3 على سطح المكتب بحالته الكاملة (٢٥١ ملف)
- [ ] تشغيل `integration_proof.py` الحالي وحفظ الـ output كأرضية

**معيار القبول:** نفهم كل سطر سنغيّره ولماذا، وعندنا baseline قابل للمقارنة.

### مرحلة ١ — Backtester الأساسي (Mock LLM)
ملفات جديدة في `backtest_v2/`:
- `data_provider.py` — يستخرج EUR/USD + USD/JPY M15 من cache OANDA
- `replay_clock.py` — ساعة تتحرّك bar-by-bar
- `account_simulator.py` — balance/positions/fills (no real broker)
- `runner.py` — يستدعي `EngineV3.decide_and_maybe_trade` لكل bar
- `metrics.py` — count, WR, PF, max-DD
- `tests/test_no_lookahead.py` — يفشل لو شاف bar[t+1] قبل bar[t]

**معيار القبول:** الباكتيست يشغّل على ٦ شهور EUR/USD + USD/JPY بدون lookahead (اختبار يمر)، يولّد تقرير baseline (loose-mode = الكود الحالي).

### مرحلة ٢ — تشديد GateMind حسب المواصفات الجديدة
تعديلات صغيرة وموثَّقة في:
- `gatemind/v3/decision_engine.py`: B → blocking (كان waiting)
- `gatemind/v3/alignment.py`: requires `len(set(directions)) == 1` AND `len(directions) == 3`

كل تعديل خلف flag `strict_mode = True` (default ON). لو احتجنا أن نختبر loose-mode للمقارنة، نمرّر `strict_mode=False`.

**معيار القبول:** الباكتيست strict-mode يعطي < ١٠٪ من عدد صفقات loose-mode، وملف diff واضح يبيّن ما تغيّر.

### مرحلة ٣ — إصلاح أنابيب البيانات الحرجة
- إزالة `atr=0.001` و `entry_price=1.0` من `EngineV3.py:155, 158` — حسابهما من الشموع الحقيقية
- وصل `Backtest/calendar.HistoricalCalendar` إلى NewsMind في وضع الباكتيست
- تمرير cross-assets (DXY/SPX/Gold) إلى MarketMind إذا متوفّرة، وإلا fallback إلى `synthetic_dxy`

**معيار القبول:** USD/JPY يصبح قابلاً للتداول في الباكتيست (لا يُرفض كل صفقة كـ stop_too_wide).

### مرحلة ٤ — Anthropic LLM Adapter
- ملف جديد `llm/anthropic_brain.py` بنفس واجهة `openai_brain.py`
- إضافة `LLM_PROVIDER=anthropic` في `.env.example`
- تعديل `llm/__init__.py` لاختيار المزوّد
- استدعاء `llm.review_brain_outputs` فعلياً من `EngineV3.decide_and_maybe_trade` (إصلاح الفجوة #5 في AUDIT)
- في الباكتيست: استخدم `MockLLM` (يعيد neutral) لتقليل التكلفة الافتراضياً، مع flag للتفعيل الكامل

**معيار القبول:** نداء واحد ناجح من EngineV3 إلى Claude، الرد محفوظ في SmartNoteBook، التكلفة معروفة لكل ١٠٠٠ شمعة.

### مرحلة ٥ — تشغيل الباكتيست الكامل + التقرير
- ٢٤ شهر EUR/USD + USD/JPY
- ٣ سيناريوهات: loose-mode / strict-mechanical / strict+LLM-on
- مقاييس كاملة: count, WR, PF, max-DD, sharpe, per-pair, per-brain accuracy
- walk-forward (8 ربعيات) للتأكد من عدم overfitting

**معيار القبول:** تقرير "قبل/بعد" مع رفض أي تحسين ليس قوياً عبر الـ ٨ ربعيات.

### مرحلة ٦ — تثبيت العدّادات (Persistence Fix)
إصلاح `daily_loss_pct/consecutive_losses/trades_today` لتُحفَظ في SmartNoteBook DB، تُحمَّل عند الإقلاع.

**معيار القبول:** اختبار `restart_in_middle_of_day` يحافظ على العدّادات.

### مرحلة ٧ — مراجعة نقدية ذاتية
- بحث عن lookahead leaks خفية
- تحقّق إن SmartNoteBook يسجّل: قرار كل عقل، الدرجة، السبب، صفقة (مفتوحة/مرفوضة)، PnL، خطأ كل عقل
- تحقّق إن GateMind لا زال يحمي (لا bypass صامت)
- اقتراح الخطوة التالية بناءً على النتائج

**معيار القبول:** تقرير ذاتي صريح: "هل التحسن حقيقي؟ هل في overfitting؟ هل تجاوزنا حدود السلامة؟"

---

## ٨) ما لن أفعله (التزامات صارمة)

- ❌ لن أغيّر قواعد GateMind بدون دليل من الباكتيست
- ❌ لن أبني logic موازٍ في الباكتيست — كله عبر EngineV3
- ❌ لن أقبل نتيجة جميلة بدون walk-forward 8 ربعيات
- ❌ لن أدخل أيّ بيانات مستقبلية في القرار (lookahead = automatic test failure)
- ❌ لن أرفع risk فوق `ABSOLUTE_MAX_RISK_PCT = 0.5%` تحت أي ظرف
- ❌ لن أبدأ المرحلة n+1 قبل أن تجتاز المرحلة n معايير القبول
- ❌ لن أكتب اختبارات تختبر ما كتبته فقط — كل اختبار له adversarial case

---

## ٩) أسئلة قبل البدء

أحتاج موافقتك على ٣ نقاط محورية قبل أكتب أيّ سطر:

1. **هل تؤكّد أن NewsMind في وضع silent (مصادر فارغة) يجب أن يُحسب كـ "missing → block"** بدلاً من سلوكه الحالي (allow بـ fail-safe)؟ هذا أكثر صرامةً ومتوافقاً مع روحك.

2. **هل تؤكد إصلاح `atr=0.001` و `entry_price=1.0` كأولوية حرجة؟** (الإجابة الواضحة: نعم، لكن أحب أتأكد لأن هذا تعديل في Engine.)

3. **هل LLM (Anthropic Claude) إلزامي للقرار النهائي، أم اختياري (downgrade-only)؟**
   - الكود الحالي: اختياري، downgrade-only، لا يُسمح له بالترقية.
   - مواصفاتك الجديدة: لم تذكر LLM صراحةً ضمن قواعد GateMind. هل تريده؟ إذا نعم، بأي صلاحية؟

---

## ١٠) جاهزية للانطلاق

عندي:
- ✅ فهم كامل للنظام الفعلي (لا تخمين)
- ✅ فهم الفجوات بين الواقع والمواصفات
- ✅ تصميم باكتيستر يلتزم بـ "لا تكرار، لا تسريب، لا تجميل"
- ✅ خطة ٧ مراحل بمعايير قبول صارمة
- ✅ التزام مكتوب بما لن أفعله

**قراري النهائي قبل التنفيذ موقوف على إجابتك على الأسئلة الثلاثة في القسم ٩.**
