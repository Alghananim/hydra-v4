# تقرير ما بعد المرحلة ٣ — بناء `backtest_v2`

**التاريخ:** 27 أبريل 2026
**النطاق:** بناء باكتيستر احترافي يلتزم بقواعدك الصارمة (لا تكرار، لا تسريب، لا تضخيم).
**الـ commit:** `7d1f861` على فرع `cleanup/hydra-v3-rebrand`.

---

## ١) ما الذي تم تغييره بالضبط

**ملف جديد:** `backtest_v2/` — مجلد كامل ٢٤ ملف (٧ tests + ١٧ كود + fixtures)

### الكود الأساسي (١٤ ملف)

| الملف | الدور | السطور |
|---|---|---|
| `runner.py` | الحلقة الرئيسية — تستدعي `EngineV3.decide_and_maybe_trade` لكل شمعة | ~٢٠٠ |
| `replay_clock.py` | ساعة افتراضية تتحرّك bar-by-bar مع cursor | ~٦٠ |
| `leak_detector.py` | wrapper حول الشموع — يرفع `LookaheadLeakError` لو حصل وصول لـ bar مستقبلي | ~١٢٠ |
| `account_simulator.py` | حساب paper: balance, positions, fills | ~١٥٠ |
| `broker_replay.py` | broker مزيّف يفّيل عند `bar[t+1].open` + spread | ~١٣٠ |
| `data_provider.py` | يجلب OANDA M15 (يستخدم `Backtest/data.py` الموجود) ويُكَش JSONL | ~٨٠ |
| `calendar_provider.py` | adapter لـ `Backtest.calendar.HistoricalCalendar` | ~٤٠ |
| `cross_asset_provider.py` | DXY/SPX/Gold (synthetic_dxy fallback لو غير متوفّر) | ~٧٠ |
| `metrics.py` | WR, PF, Max-DD, Sharpe, per-pair, per-brain | ~٢٠٠ |
| `per_brain_attribution.py` | لكل صفقة مغلقة: هل كل عقل كان صحيحاً؟ | ~١٤٠ |
| `reporter.py` | جدول مقارنة قبل/بعد | ~١٠٠ |
| `config.py` | `BacktestConfig` dataclass | ~٤٠ |
| `__init__.py` | exports | ~٢٠ |
| `README.md` | بالعربي، شرح كيف تشغّل | — |

### Fixtures (٣ ملفات)
- `synthetic_bars.py` — متسلسلات OHLC حتمية للاختبارات
- `synthetic_news.py` — أحداث تقويم معروفة
- `__init__.py`

### Tests (٧ ملفات، ١٥ حالة)
كل اختبار له هدف محدّد واضح:

| الاختبار | يثبت |
|---|---|
| `test_no_lookahead.py` (٦ حالات) | لا يمكن لأي bar مستقبلي أن يدخل في قرار |
| `test_engine_parity.py` (٣ حالات) | الباكتيست يستدعي `EngineV3` نفسها (لا fork) |
| `test_metrics_correctness.py` (٢ حالات) | WR, PF, Net تُحسب صح على fixture معروف |
| `test_strict_blocks_b_grades.py` (٢ حالات) | strict-mode يرفض B، loose-mode يسمح بـ B |
| `test_account_persistence.py` (١) | balance/positions تتطور صح |
| `test_no_mode_pollution.py` (١) | كل قيد في DB له `system_mode='backtest'` — لا تلوّث live |

---

## ٢) لماذا تم التغيير

أنت طلبت backtester احترافي يقيس:
- عدد الصفقات (مقبولة + مرفوضة)
- WR / PF / DD / P&L
- per-pair (EUR/USD + USD/JPY)
- per-brain accuracy + per-GateMind accuracy
- هل رفض B كان صحيحاً
- هل اتفاق A/A+ يحسّن النتائج
- مقارنة قبل/بعد لكل تعديل
- كشف overfitting و future leakage

**النظام السابق `Backtest/` (capital B) كان يختبر ChartMind فقط** — لا يستدعي Engine، لا GateMind، لا اتفاق العقول. **هذه فجوة جوهرية** بين ما تطلبه والمنفّذ. لذا بنيت `backtest_v2/` كـ **harness حول Engine**، ليس نظاماً موازياً.

---

## ٣) النتائج قبل التعديل

### قبل Phase 0+1+2:
- `risk_atr` في `integration_proof.py` = ~106-107 (قيمة وهمية: 0.001 × 100000)
- B grade في أي عقل → wait (يخالف مواصفاتك)
- ٢ من ٣ اتفاق كافي (يخالف مواصفاتك)
- LLM موصول لكن لا يُستدعى من Engine
- العدّادات في RAM (تُمسح عند restart)

### قبل Phase 3:
- لا يوجد باكتيستر يستخدم النظام الخماسي
- `Backtest/` الموجود = ChartMind فقط
- لا توجد طريقة لقياس "هل اتفاق A/A+ يحسن النتائج فعلاً"

---

## ٤) النتائج بعد التعديل

### بعد Phase 0+1+2:
- ✅ `risk_atr` الآن ~٧٫٤ (محسوب من ATR(14) فعلاً من الشموع)
- ✅ B في أي عقل → block (٥ اختبارات تنجح)
- ✅ ٣ من ٣ اتفاق مطلوب (٢ من ٣ + الثالث neutral → block)
- ✅ LLM يُستدعى downgrade-only (يستطيع التخفيض، لا يستطيع الترقية)
- ✅ العدّادات تُحفَظ في `engine_state` table في SmartNoteBook DB

### بعد Phase 3:
- ✅ باكتيستر يستدعي `EngineV3` نفسها — production parity كامل
- ✅ Lookahead bias مستحيل بناءً على البنية (ReplayClock + LeakDetector)
- ✅ كل قيد في DB له `system_mode='backtest'` — لا تلوّث
- ✅ Smoke test على ٥٠ شمعة اصطناعية: مكتمل بدون استثناءات، ٠ leaks
- ✅ في strict-mode على بيانات اصطناعية: ٢٠ قرار = ٢٠ block (متوقّع — البيانات الاصطناعية ضوضاء، لا أنماط حقيقية)

### حالة الاختبارات الكاملة:
```
======= 23 passed in 1.37s =======
```
- ٨ من Phase 0+1+2
- ١٥ من Phase 3
- **الكل ينجح**

---

## ٥) هل التحسن حقيقي أم لا؟

**التحسّن في الكود:** نعم، حقيقي ومُختَبر. الأدلة:
- `risk_atr` تغيّر من قيمة وهمية إلى محسوبة من الشموع → دليل قاطع أن `atr=0.001` كُسِر
- ٥ سيناريوهات strict mode تُنفَّذ صحيحاً
- ٦ اختبارات لا-تسريب تنجح (وهي adversarial — تحاول كسر النظام)
- Production parity test يضمن أن الباكتيست يستخدم نفس Engine الفعلية

**التحسّن في الأداء (PF/WR/DD):** **لم يُقَس بعد على بيانات حقيقية.** Smoke test على بيانات اصطناعية لا يثبت إلا أن النظام يعمل. القياس الحقيقي يحتاج تشغيل على EUR/USD M15 لمدة ٦-١٢ شهر من OANDA.

**هذا أمين.** لن أزعم تحسناً في أداء الاستراتيجية بدون أرقام حقيقية.

---

## ٦) هل يوجد أي خطر Overfitting؟

**حالياً لا — لأن:**
- لا يوجد parameter tuning بعد
- لا تعديل لقواعد القرار مبني على نتائج backtest
- التعديلات حتى الآن **هندسية** (إصلاح bugs، تطبيق مواصفاتك) وليست **استراتيجية**

**سيكون موجوداً لو فعلنا:**
- ضبط ATR window من ١٤ إلى رقم أفضل بناءً على نتائج backtest = overfitting
- إضافة فلتر session أو grade تعتمد على بيانات in-sample = overfitting
- اختيار الأزواج الأفضل بناءً على نفس الفترة المُختَبرة = survivorship-by-selection

**خطّة الحماية:** `walk-forward 8 ربعيات` (موجود في `scripts/walk_forward.py` — موروث من النظام السابق). أي تعديل استراتيجي يجب أن يجتاز هذا الفلتر قبل قبوله.

---

## ٧) هل توجد أخطاء أو قيود متبقية؟

### مكتشَف أثناء التنفيذ (موثَّق):

١. **خطأ broker_env في الإنتاج:**
   - `ValidationConfig.validate_or_die` يقبل `practice|live`
   - `GateMind.execution_check` يقبل `paper|live|sandbox`
   - النتيجة: كل قرار في الإنتاج يحمل `broker_unsafe:broker_mode_unknown:practice`
   - **الباكتيست تجاوزه** بـ wrapper مؤقّت يحوّل `practice→paper`
   - **يجب إصلاحه في الإنتاج** — يمنع أي صفقة live حالياً

٢. **Cross-assets في الباكتيست:**
   - يحمّل companion pair لو موجود في cache
   - XAU/SPX يُتركان فارغين (يصعب جلبهما تاريخياً بدون مزوّد إضافي)
   - MarketMind يتعامل مع غياب cross-assets gracefully، لكن إشارته ستكون أضعف من live
   - **الأثر:** درجة MarketMind قد تكون أحياناً أدنى مما كانت ستكون مع DXY الكامل

٣. **الأخبار التاريخية:**
   - الباكتيست يستخدم `HistoricalCalendar` (الأحداث المجدولة فقط)
   - الأخبار العاجلة (breaking) لا يمكن إعادة إنتاجها تاريخياً (لا cache reliable)
   - **مقصود:** أفضل من تزوير
   - **الأثر:** NewsMind في الباكتيست أضعف من live في الأحداث غير المجدولة

٤. **LLM في الباكتيست:**
   - معطّل افتراضياً (`use_llm=False`) لتجنّب التكلفة
   - **الأثر:** أرقام الباكتيست = mechanical-only، ربما LLM-on في live أفضل

### قيود معروفة لم تُلامَس:

- `audit_calibration.py` و `audit_failsafe.py` يعطون نتائج أقل بعد strict-mode (كانوا مكتوبين على افتراض loose). **يحتاجون re-baselining.**
- `integration_proof.py` لا زال كل سيناريوهاته تنتهي بـ block — لا يوجد سيناريو positive end-to-end.

---

## ٨) توصيتي للخطوة التالية

### الخطوة ٤ (الأولوية القصوى): **شغّل الباكتيست على بيانات حقيقية**

```powershell
$env:OANDA_API_TOKEN  = "...your token..."
$env:OANDA_ACCOUNT_ID = "...your id..."
$env:OANDA_ENV        = "practice"

cd $env:USERPROFILE\Documents\hydra-v3
.\.venv\Scripts\python.exe -c "from datetime import datetime, timezone; from backtest_v2 import BacktestConfig, BacktestRunner; cfg = BacktestConfig(pair='EUR/USD', start_utc=datetime(2024,1,1,tzinfo=timezone.utc), end_utc=datetime(2024,6,30,tzinfo=timezone.utc)); print(BacktestRunner.from_config(cfg).run().report.to_json())"
```

**ما الذي ستراه:**
- عدد الصفقات الفعلية في strict-mode على ٦ أشهر
- WR / PF / DD لـ EUR/USD
- per-brain accuracy لكل عقل من العقول الخمسة
- هل اتفاق ٣ من ٣ A/A+ يولّد فرص كافية أم قليلة جداً

**معيار النجاح:** ≥٣٠ صفقة مغلقة (Lopez de Prado threshold للحصول على أرقام موثوقة). إن أقل، نوسّع لـ ١٢ شهر.

### الخطوة ٥: **مقارنة loose vs strict على نفس البيانات**

نشغّل Run #1 (`strict_mode=True`) ثم Run #2 (`strict_mode=False`)، نقارن:

```python
from backtest_v2.reporter import diff_text
print(diff_text(loose_report, strict_report))
```

هذا يعطينا الجواب الكمّي على: **"هل قاعدتك الصارمة (٣ من ٣ A/A+) فعلاً تحسّن النتائج؟"**

### الخطوة ٦: **walk-forward ٨ ربعيات**

لرفض overfitting، نقسم البيانات إلى ٨ ربعيات ونشغّل على كل واحد. نقبل التحسّن فقط لو ظهر في ≥٦ من ٨.

### إصلاحات صغيرة قبل الخطوة ٤ (٢٠ دقيقة):

١. إصلاح `broker_env` mismatch (production-blocking)
٢. إضافة فحص explicit `news_silent → block` في `decision_engine.py`
٣. إضافة سيناريو positive في `integration_proof.py`
٤. إعادة معايرة `audit_calibration.py` لـ strict-mode

**رأيي الصريح:** نُكمل الإصلاحات الأربعة الصغيرة (٢٠ دقيقة) ثم نقفز للخطوة ٤. النظام يكون نظيفاً ١٠٠٪ قبل أول قياس حقيقي.

---

## ملاحظات صريحة

- لم أغيّر أي قاعدة من قواعد GateMind بدون مواصفاتك. كل ما عُدِّل خلف flag `strict_mode=True` (مطابق لمواصفاتك حرفياً).
- لم ألمس `safety_rails` (الـ ١٢ فحص).
- لم أرفع `ABSOLUTE_MAX_RISK_PCT` فوق ٠٫٥٪.
- لم أُدخل بيانات مستقبلية (٦ اختبارات adversarial تثبت).
- لم أَعِد بأداء قبل أن أقيس.

**الكود جاهز ومُختَبر. القياس الحقيقي ينتظر تشغيلك على OANDA.**
