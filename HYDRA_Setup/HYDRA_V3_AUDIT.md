# تدقيق فني شامل لنظام HYDRA V3

> **الهدف:** فحص صحة الكود لكل عقل من الأدمغة الخمسة ولمنسّق Engine V3 ومسار التنفيذ، بالاعتماد على قراءة الكود مباشرةً (لا على ملفات `AUDIT_VERDICT.md` أو `DIAGNOSTIC.md`، فهي تتحدث عن نتائج الـ backtest وليس عن صحة الكود).
>
> **المرجع الزمني:** قراءة الكود في `/tmp/newsmind` بتاريخ 2026-04-26.
>
> **تنبيه أولي ومهم جداً:** اكتشف التدقيق وجود نسختين متوازيتين في نفس المستودع — نسخة قديمة مكتوبة بأحرف كبيرة (`ChartMind/`, `MarketMind/`, `NewsMind/`, `GateMind/`, `SmartNoteBook/`, `Engine.py`, `main.py`) وهي ما يشغّله فعلياً `Dockerfile` و `docker-compose.yml`، ونسخة V3 الجديدة بأحرف صغيرة (`chartmind/v3/`, `marketmind/v3/`, ...) وهي **غير موصولة بالإنتاج**. كل ما يلي يخصّ نسخة V3 المطلوب تدقيقها.

---

## 1) ChartMind V3 — التحليل الفني

### 1.1 ملفات الحزمة

| الملف | عدد الأسطر | الدور بسطر واحد |
|---|---:|---|
| `ChartMindV3.py` | 267 | منسّق المراحل الـ 12 وحساب grade/permission |
| `models.py` | 116 | `Bar`, `Level`, `ChartAssessment` (dataclasses) |
| `market_structure.py` | 101 | تصنيف HH/HL/LH/LL + BoS + CHoCH عبر swing points |
| `support_resistance.py` | 62 | بناء مستويات الدعم/المقاومة من القمم/القيعان |
| `trend.py` | 104 | اتجاه + قوة (ADX مبسّط) + جودة (smooth/jagged/exhausting) |
| `candles.py` | 144 | كشف الشموع وسياقها على المستوى |
| `breakout.py` | 95 | حالة الاختراق: real/fake/pending/weak |
| `pullback.py` | 69 | جودة الارتداد (clean/deep/shallow) |
| `multi_timeframe.py` | 51 | محاذاة M15/M5/M1 |
| `entry_quality.py` | 79 | excellent/good/marginal/late/chase/no_setup |
| `stop_target.py` | 98 | حساب SL/TP و R:R |
| `traps.py` | 89 | liquidity sweep / bull-trap / bear-trap / chop / stop-hunt |
| `permission_engine.py` | 146 | hard-blocks + hard-waits + grade ladder |
| `scoring.py` | 58 | تحويل تسميات إلى أرقام 0..1 |
| `cache.py` | 51 | تخزين مؤقت لـ ATR/ADX/swings (memoize) |
| `latency.py` | 46 | Stopwatch لقياس زمن كل مرحلة |
| `audit_calibration.py` | 165 | اختبار محلي (سكربت) |
| `audit_failsafe.py` | 113 | اختبار محلي (سكربت) |
| `cert_v3.py` | 369 | شهادة قبول داخلية بالسيناريوهات |
| `cert_speed.py` | 300 | اختبار زمن الاستجابة |
| `__init__.py` | 15 | تصدير `ChartMindV3` و `Bar` |

**المجموع:** 21 ملفاً، حوالي 2,476 سطراً.

### 1.2 كيف يفكّر

- **المدخلات:** قائمة Bars على M15 (إلزامية، ≥6 شموع) + M5/M1 اختياريين، الزوج، وقت UTC (`ChartMindV3.assess` في `ChartMindV3.py:51-66`).
- **المعالجة:** يعمل على 12 مرحلة موقوتة: data_load → structure → ATR → support/resistance → trend → candle → breakout (يجرّب اتجاهين ويختار الأكثر إشارةً) → pullback → multi-timeframe → entry_quality → risk_reward → traps → permission. كل مرحلة معزولة في دالة، والنتائج تُحقن في `ChartAssessment`.
- **حقول الإشارات الناتجة:** `market_structure`, `trend_direction/strength/quality`, `support_levels`, `resistance_levels`, `breakout_status`, `retest_status`, `entry_quality`, `stop_loss`, `take_profit`, `risk_reward`, `volatility_status`, traps متعدّدة، تحذيرات قائمة (`warnings`).
- **القرار النهائي:** `permission_engine.finalize` (`permission_engine.py:55-149`) يطبّق hard-blocks ثم hard-waits ثم سُلّم درجات A+/A/B/C، ويملأ `grade` و `trade_permission` و `confidence`.
- **المُستهلِك:** GateMind يستلم النتيجة عبر `BrainSummary` المبني في `EngineV3._brain_summary_from_chart`.

### 1.3 ما هو قوي

1. **هندسة default-deny واضحة:** أي بيانات ناقصة (<6 شموع) ترجع `block` فوراً (`ChartMindV3.py:54-66`)، وأي استثناء داخل قواعد الـ permission يُتجاوز بأمان (`permission_engine.py:62-65, 73-76`).
2. **memoization حقيقي:** `cache.py:_fingerprint` يعتمد على (id(bars), len, last close, last timestamp) ويوفر `ATR/ADX/swings` بشكل ثابت بدون إعادة حساب (`trend.py:14-15`, `market_structure.py:18-19`).
3. **صدق منطقي في السُّلم:** A+ يستلزم 11 شرطاً متزامناً (`permission_engine.py:84-95`)، وحجب Set-up المستحيل (`unclear/range + late/chase/no_setup`) إلى `wait+C` (`permission_engine.py:77-83`).
4. **قياس زمن صريح لكل مرحلة:** `bottleneck_stage` و `stages_breakdown` معبّأة في كل تقييم، وميزانية 50ms محدّدة في الكود.

### 1.4 ما هو ضعيف أو ناقص

1. **عتبات سحرية كثيرة بدون مرجع:** قيم مثل `0.3 ATR` للاختراق، `0.5 ATR` للارتداد، `1.5 ATR` للـ chase، `2 ATR` للانفجار، `flips ≥ 4` لـ jagged، كلها مكتوبة كأرقام صلبة في `breakout.py:24-30`, `pullback.py:30-40`, `entry_quality.py:34-38`, `trend.py:80-87` بلا توثيق إحصائي ولا اختبار walk-forward داخل V3 (الـ DIAGNOSTIC.md الموجود في الجذر يخصّ النسخة القديمة).
2. **منطق `bull_trap`/`bear_trap` فيه عيب منطقي صامت:** الحلقة الداخلية في `traps.py:33-37, 47-51` تحوي `if j < 0` وهي `True` دائماً داخل `range(i+1, 0)` — أي أنّ الشرط لا يُضيف فلتراً فعلياً، وهذا يجعل الكاشف يُفعَّل بسهولة على شريط متعرّج عادي.
3. **`entry_price_zone` ثابت بنسبة ±2 pips:** `(close*0.9998, close*1.0002)` (`ChartMindV3.py:202-203`) بصرف النظر عن التذبذب الحقيقي للزوج/الجلسة، ما يجعل المنطقة غير ذات معنى لـ JPY.
4. **`speed_score` و `intelligence_score` لا يُستهلَكان من GateMind:** يُحسبا ويُحفظا في `ChartAssessment` لكن لا يُؤثّران في قرار التداول النهائي (`EngineV3.py:79-100`).

### 1.5 حالة الاكتمال

🟡 **Beta** — البنية مكتملة ومنسجمة، لكن العتبات لم تُعايَر إحصائياً داخل V3 ومنطق فخّيْ الـ trap فيه خلل.

---

## 2) MarketMind V3 — السياق الكلّي

### 2.1 ملفات الحزمة

| الملف | الأسطر | الدور |
|---|---:|---|
| `MarketMindV3.py` | 301 | منسّق 10 مراحل + احتساب الـ DXY الاصطناعي + التناقضات |
| `models.py` | 78 | `Bar`, `MarketAssessment` |
| `regime_detector.py` | 195 | trend/range/choppy/breakout/fake_breakout/reversal/news_driven/low_liq/high_vol/dangerous |
| `synthetic_dxy.py` | 94 | DXY مركّب من EUR/USD, USD/JPY, GBP/USD, USD/CAD, USD/CHF, SEK/USD |
| `strength_index.py` | 87 | قوة الدولار/العملة المقابلة |
| `risk_sentiment.py` | 98 | risk_on / risk_off / unclear |
| `correlation.py` | 99 | كشف انكسار العلاقات (EURUSD↔DXY, USDJPY↔Gold, ...) |
| `data_quality.py` | 64 | gaps/spread/staleness anomalies |
| `news_alignment.py` | 62 | aligned / divergent / no_news / blocked / caution |
| `pair_assessor.py` | 62 | منطق خاص لكل زوج |
| `contradictions.py` | 129 | كاشف التناقضات بين الإشارات |
| `permission_engine.py` | 160 | hard-blocks + grade ladder + news cap |
| `scoring.py` | 80 | تحويل التسميات إلى أرقام 0..1 |
| `cache.py` | 61 | memoize ATR/ADX/percentiles |
| `latency.py` | 58 | Stopwatch + per-source latency |
| `audit_failsafe.py` | 307 | اختبار سكربتي |
| `final_certification.py` | 387 | شهادة قبول داخلية |
| `cert_v3.py` | 372, `cert_speed.py` 321 | شهادات الأداء |
| `__init__.py` | 16 | تصدير |

**المجموع:** 20 ملفاً، حوالي 2,991 سطراً.

### 2.2 كيف يفكّر

- **المدخلات:** قاموس `baskets` يحوي شموع EUR/USD و USD/JPY و GBP/USD، شموع XAU/USD و SPX500 (اختيارية)، وقرار NewsMind `news_verdict`، و`source_latencies_ms` اختيارية للحكم على نضارة المصادر.
- **المعالجة:** 10 مراحل: data_quality → regime → risk_sentiment → strength+DXY → correlation → pair_logic → news_alignment → contradictions → labels → permission. يحسب `synthetic_dxy` من سلّة العملات الموجودة بعد إعادة تطبيع الأوزان.
- **مصافي السلامة:** إذا غطّى الـ DXY أقل من 70% أو فيه أقل من زوجين دولاريين → تحذير `dxy_low_coverage` (`MarketMindV3.py:135-141`). إذا 50% من المصادر متأخرة → تحذير `many_stale_sources` (`MarketMindV3.py:88-99`).
- **القرار النهائي:** `permission_engine.finalize` يجمع hard-blocks (spread خطر / regime خطر / news_block) وhard-waits (data missing / volatility extreme / تناقضات USD-JPY-DXY)، ثم سُلّم درجات A+/A/B/C، ثم `news_grade_cap` و `contradiction_grade_cap` يأخذ الأشد.
- **المُستهلِك:** GateMind عبر `_brain_summary_from_market`.

### 2.3 ما هو قوي

1. **DXY اصطناعي ذكي:** الأوزان ICE الحقيقية مع إعادة تطبيع لتغطية جزئية (`synthetic_dxy.py:31-39`)، وقياس `coverage` صريح يُستخدم لاحقاً كتحذير.
2. **شبكة contradictions غنية:** `contradictions.py` يكشف dxy↔eurusd كسر، usdjpy spike، coincident usd pairs، وكلّها معنية بحوادث التدخّل (intervention).
3. **سُلّم اشتراطات A+ صارم جداً:** 8 شروط متزامنة (`permission_engine.py:97-105`) — قوي ضد إعطاء A+ بسهولة.
4. **تكاملٌ صحيح مع NewsMind:** يعرف الفرق بين كائن `NewsVerdict` و `dict` ويتعامل معهما (`MarketMindV3.py:118-126`، `permission_engine.py:138-148`).

### 2.4 ما هو ضعيف أو ناقص

1. **`yield_signal = "unavailable"` ثابت:** لا توجد أيّ بنية لجلب عوائد السندات الأمريكية (`MarketMindV3.py:215`)، مع أنّ المنطق يتحدّث عنها كأحد أعمدة risk-sentiment.
2. **Gold/SPX قد لا يُمرَّران:** الـ EngineV3 لا يحقن `bars_xau` ولا `bars_spx` في `decide_and_maybe_trade` (يمرّر `news_verdict, market_assessment` معدّاً مسبقاً)، فالـ risk_sentiment يصير في الإنتاج `unclear` غالباً.
3. **عتبات إحصائية سحرية:** `ATR > 2.5×ATR_p95 ⇒ extreme`، `ratio < 0.4 ⇒ poor` (`MarketMindV3.py:55-67`)، عتبات spread محدّدة لـ EUR/USD و USD/JPY فقط، أي زوج ثالث يقع في الفرع العام.
4. **اعتماد على `now_utc.hour` لتقسيم الجلسات:** (`MarketMindV3.py:32-37`) يتجاهل DST، خلافاً لـ `gatemind/v3/session.py` الذي يعتمد على `zoneinfo` بشكل صحيح.

### 2.5 حالة الاكتمال

🟡 **Beta** — كاشفات regime/correlation/contradiction قوية ومتشعّبة، لكن مدخلات Gold/SPX/Yields غير موصولة فعلياً بالإنتاج.

---

## 3) NewsMind V2 — الأخبار والأحداث

> ملاحظة: المسار `newsmind/v2/` (ليس v3) متعمد، فالنسخة V2 تخدم Engine V3 مباشرة.

### 3.1 ملفات الحزمة

| الملف | الأسطر | الدور |
|---|---:|---|
| `NewsMindV2.py` | 200 | المنسّق: scheduler → fetch → freshness → chase → permission → intelligence |
| `models.py` | 171 | `NewsItem`, `EventSchedule`, `NewsVerdict` |
| `sources.py` | 147 | محوّلات المصادر (Reuters/Bloomberg/Forexlive/Investing/Twitter) + Aggregator |
| `freshness.py` | 83 | fresh / recent / stale / recycled / unknown |
| `chase_detector.py` | 121 | كشف "الجري خلف السوق" بعد الخبر |
| `event_scheduler.py` | 160 | نوافذ pre/during/post للأحداث الكبرى (NFP/CPI/FOMC/ECB/BoJ/BoE) |
| `permission.py` | 173 | محرّك القرار: 10 قواعد متراصّة + grade ladder |
| `intelligence.py` | 232 | تصنيف الحدث + parser للمفاجآت + اتّجاه USD/EUR/JPY + risk_mode |
| `cert_v3.py` | 296 | شهادة قبول داخلية |
| `test_intelligence.py` | 677 | اختبارات وحدة |
| `test_newsmind_v2.py` | 386 | اختبارات وحدة |
| `__init__.py` | 24 | تصدير |

**المجموع:** 12 ملفاً، حوالي 2,670 سطراً (منها 1,063 سطراً اختبارات).

### 3.2 كيف يفكّر

- **المدخلات:** الزوج، تقويم اقتصادي اختياري (`calendar`)، قائمة `sources` (محوّلات مصادر)، عدد التأكيدات المطلوبة، وفي كل دورة: `now_utc`, `recent_bars`, `current_bar`.
- **المعالجة:** أولاً يفحص `event_scheduler.windows_for` لو في نافذة حدث عالي → `block` فوراً (`NewsMindV2.py:99-118`). ثم يُحضر العناوين عبر `aggregator.fetch_all`. لو لم تُرجَع أخبار، يميّز بين "shut tape" (allow) و"source outage" (wait) عبر `fetch_status_summary` (`NewsMindV2.py:128-156`). لكل خبر صالح: freshness → chase → `permission.decide` → `_enrich_with_intelligence` (يحقن `market_bias`, `risk_mode`, `impact_level` ويضيف override "wait" لـ political-unverified ولـ risk_off+high_impact غير الواضح).
- **القرار النهائي:** worst-case يفوز (block > wait > allow) عبر ترتيب القائمة (`NewsMindV2.py:177-181`).
- **المُستهلِك:** MarketMind وGateMind وEngineV3.

### 3.3 ما هو قوي

1. **Fail-safe ضد انقطاع المصادر:** `fetch_status_summary` يعدّ `ok/empty/error/never` ويمنع التداول لو كل المصادر ميّتة (`NewsMindV2.py:131-141`، `sources.py:128-136`)، وهذا تصحيح صريح لخطأ سابق `bug #25/26`.
2. **كشف "recycled":** `freshness.py:62-69` يقارن `published_at` مقابل `received_at` ويلتقط إعادة نشر الأخبار القديمة.
3. **تغطية أحداث صريحة:** `event_scheduler.EVENT_META` يحدد NFP/CPI/PPI/FOMC/ECB/BoJ/BoE/UK CPI بوزن "high"/"medium"، مع مساحة pre/during/post (`event_scheduler.py:30-44`).
4. **تغطية اختبار جيدة لـ V2 فقط:** 1,063 سطر اختبار وحدة (`test_intelligence.py`، `test_newsmind_v2.py`) — هذا أقوى تغطية اختبار في كل V3.

### 3.4 ما هو ضعيف أو ناقص — **خطير جداً**

1. **🔴 كل محوّلات المصادر مُجوَّفة (stubs):**
   ```py
   # sources.py:62-90
   class ReutersWireSource(NewsSource):
       def _do_fetch(self, *, since_utc, now): return []
   class BloombergWireSource(NewsSource):
       def _do_fetch(self, *, since_utc, now): return []
   class ForexliveSource(NewsSource):
       def _do_fetch(self, *, since_utc, now): return []
   class InvestingCalendarSource(NewsSource):
       def _do_fetch(self, *, since_utc, now): return []
   class TwitterOfficialSource(NewsSource):
       def _do_fetch(self, *, since_utc, now): return []
   ```
   **هذا يعني أنّ NewsMind في الإنتاج لا يستلم خبراً واحداً.** المنطق كلّه صحيح، ولكن لا توجد بنية `requests`/RSS/API تستدعي الموقع. كل الإنتاج يقع في فرع "no relevant news → no_blocking_news → allow + grade C" ما لم يُحقَن `calendar` خارجي عبر `EventScheduler`.
2. **التقويم `calendar=None` افتراضياً:** `engine/v3/EngineV3.py` لا يمرّر تقويماً، فالـ `scheduler.windows_for` يعمل على قائمة فارغة، وبالتالي لا توجد حماية من نافذة NFP/CPI تلقائياً ما لم يحقن المستخدم `HistoricalCalendar` يدوياً.
3. **`since = now - 2h` ثابتة:** نافذة الجلب 2 ساعة لا تُغيَّر من البيئة (`NewsMindV2.py:120`)، وقد تكون قصيرة لو الدورة 60 ثانية وحدث متأخّر في النشر.
4. **`require_confirmations=2` ثابت:** بدون التأكيدين يُعطي `wait`. لمّا تكون كل المصادر stubs ولا تأكيد، فحتى لو حقن المستخدم RSS يدوياً، ستحدث "wait" دائمة حتى يتأكّد مصدران مستقلان.

### 3.5 حالة الاكتمال

🔴 **Stub في الإنتاج / Beta منطقياً.** الذكاء والقواعد ممتازة، لكن طبقة الإدخال غير موجودة. NewsMind حالياً عبارة عن منسّق متعطّل لأنّ كل أنابيب البيانات مفرّغة.

---

## 4) GateMind V3 — البوّابة والتوجيه

### 4.1 ملفات الحزمة

| الملف | الأسطر | الدور |
|---|---:|---|
| `GateMindV3.py` | 209 | المنسّق: 10 مراحل + التناقضات + القرار النهائي |
| `models.py` | 116 | `BrainSummary`, `SystemState`, `GateDecision` |
| `decision_engine.py` | 154 | تركيب القرار: hard-blocks → hard-waits → enter |
| `alignment.py` | 45 | تطابق الاتجاه بين الأدمغة الثلاثة |
| `risk_check.py` | 29 | فحص SL/TP/RR + ATR |
| `session.py` | 33 | نافذة NY (03–05 و 08–12) عبر `zoneinfo` |
| `news_gate.py` | 16 | inheriting block/wait من NewsMind |
| `execution_check.py` | 60 | pair_status + broker_mode + spread + slippage |
| `state_check.py` | 55 | daily limits / cooldown / open positions |
| `contradictions.py` | 118 | كاشف فخاخ خفية (8 أنواع) |
| `scoring.py` | 51 | scores 0..1 |
| `cache.py` | 5 | placeholder dummy (موضّحة كذلك في الكود) |
| `audit_bypass.py` | 243 | اختبار محاولة التحايل |
| `audit_calibration.py` | 146 | اختبار معايرة |
| `audit_failsafe.py` | 246 | اختبار فشل آمن |
| `cert_v3.py` | 329, `cert_speed.py` 211 | شهادات قبول |
| `latency.py` | 36 | Stopwatch |
| `__init__.py` | 13 | تصدير |

**المجموع:** 19 ملفاً، حوالي 2,115 سطراً.

### 4.2 كيف يفكّر

- **المدخلات:** `BrainSummary` لكل من News/Market/Chart + `SystemState` (وضع البروكر، spread، slippage، حدود يومية، خسائر متتالية، حالة الزوج)، entry/SL/TP/size/atr، حد ثقة أدنى.
- **المعالجة:** 10 مراحل: input_parse → alignment_check → risk_check → session_check → news_gate → execution_check → daily_limits_check → contradictions → final_decision (synthesize). كلّها داخل `try/except` لكي لا يُسقِط الاستثناء البوّابة.
- **القرار النهائي:** `decision_engine.synthesize` (`decision_engine.py:18-153`):
  - أيّ block من أيّ دماغ → block.
  - أيّ grade=C → block.
  - أيّ B → wait.
  - allow + A/A+ + alignment=aligned + risk=ok + session=in_window + news_gate=ok + execution=ok + flat + لا حدود + ثقة ≥ 0.6 → enter.
  - بعد ذلك تطبَّق التناقضات: critical → block، high → wait، medium → wait أيضاً لو القرار enter (`GateMindV3.py:148-167`).
- **المُستهلِك:** Engine V3 لتنفيذ الأمر بعد safety_rails.

### 4.3 ما هو قوي

1. **Default-deny صريح ومتعدّد الطبقات:** أيّ خطأ في أيّ مرحلة يقع في كتلة `except` تضع الحالة على "blocking" ثم القرار على block.
2. **`pair_status` مصدر حقيقي وحيد:** `execution_check.PAIR_STATUS = {EUR/USD: production, USD/JPY: monitoring, GBP/USD: disabled}` متطابقة مع `validation_config.pair_status` ومع `main.py` القديم — منع التداول الحقيقي على JPY/GBP حتى لو طلب الكود ذلك.
3. **DST صحيح:** `session.py` يعتمد `zoneinfo("America/New_York")` ويرفض القرار `dst_unknown` كـ block لو المكتبة غير متاحة (مهم على نظم Linux قديمة).
4. **8 كاشفات تناقضات:** "high grade مع warning keyword"، "high confidence مع stale data"، spread قريب من الحد، نهاية النافذة، RR ضعيفة بين 1.0–1.2، monitoring+live، chart allow مع reason يحوي fake_breakout، خسائر متتالية بدون cooldown.

### 4.4 ما هو ضعيف أو ناقص

1. **`atr=0.001` ثابت في `EngineV3`:** (`EngineV3.py:158`) — يقتل قاعدة `risk_check`'s "stop too tight/wide" لأنّ `risk_atr = stop_distance/0.001` غير واقعي. يُحوِّل أي وقف 5 pips على EUR/USD إلى `risk_atr=0.5` فيرفع البلاغ "stop_too_tight".
2. **`entry_price = nearest_key_level OR 1.0`:** (`EngineV3.py:155`) — لو ChartMind لم يجد مستوى مفتاح، السعر يُملأ بالقيمة `1.0`، وهي قيمة بعيدة جداً عن السعر الحقيقي وستجعل `risk_check` يبلّغ stop_too_wide دائماً.
3. **`min_confidence=0.6` افتراضي:** ولكن ChartMind غالباً يعطي `confidence=0.20` لـ C و 0.50 لـ B و 0.70 لـ A، فالعبور يلزم A+ على Chart لرفع المتوسّط فوق 0.6 — قاعدة منطقية لكنّها لم توثَّق.
4. **`cache.py` placeholder:** (`gatemind/v3/cache.py:1-5`) موجود فقط لتطابق API — لا تأثير، لكنّه دلالة على نسخ-لصق الهيكل.

### 4.5 حالة الاكتمال

🟡 **Beta قوي** — المنطق متين والـ default-deny آمن، لكن وصلات `entry_price` و `atr` من EngineV3 هشّة جداً ولا تنتج قراراً enter منطقياً في الواقع.

---

## 5) SmartNoteBook V3 — الذاكرة والمذكّرات

### 5.1 ملفات الحزمة

| الملف | الأسطر | الدور |
|---|---:|---|
| `SmartNoteBookV3.py` | 168 | المنسّق: record_trade/decision/bug + reports + queries |
| `models.py` | 229 | `MindOutputs`, `TradeAuditEntry`, `DecisionEvent`, `LessonLearned`, `BugDetected`, `DailySummary`, `WeeklySummary`, `AttributionResult` |
| `storage.py` | 255 | SQLite + JSONL append-only، WAL، connection persistent |
| `classifier.py` | 79 | logical_win/lucky_win/spread_loss/structural_loss/breakeven... |
| `attribution.py` | 113 | تحديد الدماغ المسؤول عن النتيجة |
| `recommender.py` | 52 | اقتراحات تتطلب ≥3 شواهد، تأكيد عند 5 |
| `pattern_detector.py` | 68 | grade calibration، brain overconfidence |
| `report.py` | 149 | تقارير يومية وأسبوعية |
| `search.py` | 59 | why_did_we_lose/win, most_wrong_brain |
| `bug_log.py` | 43 | تسجيل الـ bugs ومعالم الإصلاح |
| `audit_integrity.py` | 242 | اختبار سلامة المذكّرة |
| `async_writer.py` | 79 | كاتب غير متزامن للأحداث |
| `scoring.py` | 45 | speed/intelligence scores |
| `cert_v3.py` | 226, `cert_speed.py` 245 | شهادات قبول |
| `latency.py` | 73 | Stopwatch + Metrics |
| `__init__.py` | 13 | تصدير |

**المجموع:** 17 ملفاً، حوالي 2,148 سطراً.

### 5.2 كيف يفكّر

- **المدخلات:** كل قرار/صفقة من Engine V3 يصل كـ `DecisionEvent` أو `TradeAuditEntry`. الـ `record_trade` يُصنِّف ويسند المسؤولية ثم يكتب.
- **المعالجة:** كتابة على SQLite (autocommit + WAL) مع نسخة JSONL يومية أيضاً (`storage.py:108-128`). الكتابة "Critical" (trades, bugs) متزامنة، والـ "wait/observable" تمر بكاتب async دفعات (`async_writer.py`). الـ `recommender` يفرض ≥3 شواهد قبل أيّ توصية و≥5 قبل تأكيد، ضد الـ overfitting.
- **المُخرَجات:** يوميات JSONL + قاعدة SQLite + تقارير + lessons + bugs.

### 5.3 ما هو قوي

1. **مكافحة overfitting صريحة:** `MIN_EVIDENCE_FOR_SUGGESTION=3` و `MIN_EVIDENCE_FOR_CONFIDENT=5` (`recommender.py:21-22`)، كل lesson دون 5 شواهد يحمل علم `requires_more_evidence=True`.
2. **Append-only + dedupe:** `audit_id` و `trade_id` PRIMARY KEY مع تحقّق `SELECT 1` قبل الكتابة (`storage.py:127-130`). أيضاً JSONL يومية كنسخة احتياطية في حال تلف SQLite.
3. **WAL + persistent connection:** (`storage.py:42-45`) للأداء العالي — `sqlite_thread_safety` مفعّل عبر `check_same_thread=False` مع قفل خارجي `_LOCK`.
4. **Async مع backpressure:** `AsyncWriter` يستخدم `queue` بحجم 10000 ويعدّ `dropped/written/submitted` ويكشفها في `health_report` (`async_writer.py:25-34`).

### 5.4 ما هو ضعيف أو ناقص

1. **`intelligence_score` يستخدم قِيَم مفترضة ثابتة:**
   ```py
   # SmartNoteBookV3.py:127-131
   def intelligence_score(self) -> float:
       return scoring.notebook_intelligence_score(
           classification_acc=0.95, attribution_acc=0.90,
           recommendation_q=1.0, pattern_detection=1.0)
   ```
   تعليق صريح "Placeholder using current metrics + assumed accuracies" — لا يقيس دقّة فعلية.
2. **`update_after_close` لا يكتب الإغلاق في الجدول:** (`EngineV3.py:251-262`) يحدّث `consecutive_losses` و `daily_loss_pct` بالذاكرة فقط، لكنّ `TradeAuditEntry` المخزّنة سابقاً لا تُحدَّث بسعر الخروج/PnL/exit_time. التعليق نفسه يقول "(extension)".
3. **لا توجد آلية ترقّي/تنظيف للـ JSONL:** ملفات JSONL يومية تُكتب بلا اقتطاع، وقد تنمو بلا حدّ.
4. **`storage_health` يصنّف `degraded` فقط عند 5% drop_rate:** (`scoring.py:42-46`) قد يخفي مشاكل تسجيل تحت العتبة.

### 5.5 حالة الاكتمال

🟡 **Beta** — البنية الكتابية والاستعلام نظيفة، لكن دورة "trade open → trade closed" غير مكتملة، و `intelligence_score` رمزي.

---

## 6) Engine V3 — المنسّق العام و حواجز السلامة

### 6.1 ملفات الحزمة

| الملف | الأسطر | الدور |
|---|---:|---|
| `EngineV3.py` | 290 | الواجهة `decide_and_maybe_trade` + `update_after_close` |
| `validation_config.py` | 86 | `ValidationConfig` + `ABSOLUTE_*` ceilings + validate_or_die |
| `position_sizer.py` | 89 | حساب units من 0.25% risk + pip value |
| `safety_rails.py` | 81 | الفحوصات الـ 12 النهائية قبل الأمر |
| `integration_proof.py` | 312 | اختبار شامل من 5 سيناريوهات |
| `cert_pre_live.py` | 187 | شهادة "قبل live" بـ 15 سيناريو إلزامي |
| `main_v3.py` | 98 | نقطة الدخول، حالياً heartbeat فقط |
| `__init__.py` | 8 | تصدير |

### 6.2 كيف يفكّر دورة `decide_and_maybe_trade`

1. بناء `SystemState` من cfg والإحصاءات الجارية (`EngineV3.py:124-138`).
2. تحويل قراءة كل دماغ إلى `BrainSummary`.
3. استدعاء `GateMindV3.decide` مع entry/SL/TP من ChartMind و `atr=0.001` ثابت (هشّ).
4. تسجيل `DecisionEvent` غير المتزامن في SmartNoteBook على كل حال.
5. لو القرار ≠ enter → خروج مع السبب.
6. حساب الحجم عبر `position_sizer.calculate_position_size`.
7. **`safety_rails.check_all`** — فحص 12 طبقة نهائية (التفصيل بعد قليل).
8. لو وجود broker → `submit_market_order`؛ غير ذلك dry-run.
9. تسجيل `TradeAuditEntry` متزامن.

### 6.3 `safety_rails.py` — الفحوصات الـ 12 النهائية

| # | الفحص | السطر | الحكم |
|---|---|---|---|
| 1 | قرار البوابة لازم enter | `safety_rails.py:24-26` | ✅ صلب |
| 2 | حجم المركز صالح + units≥1 | 28-31 | ✅ صلب |
| 3 | risk الفعلي لا يتجاوز `max_risk_pct_per_trade` (+0.01 tolerance) | 33-37 | ✅ صلب |
| 4 | الخسارة اليومية لم تصل الحد | 39-41 | ✅ صلب لكن `daily_loss_pct` لا يحمل حسابات سابقة عند إعادة التشغيل (في الذاكرة فقط) |
| 5 | الخسائر المتتالية أقل من الحد | 43-45 | ⚠ ذاكرة فقط |
| 6 | عدد صفقات اليوم تحت الحد | 47-49 | ⚠ ذاكرة فقط |
| 7 | SmartNoteBook قابلة للكتابة | 51-53 | ✅ صلب |
| 8 | spread أقل من الحد لكل زوج | 55-58 | ✅ صلب |
| 9 | slippage تقديرياً تحت الحد | 60-62 | ✅ صلب |
| 10 | حالة الزوج: ليست disabled / monitoring في live / unknown | 64-71 | ✅ صلب |
| 11 | broker_env ضمن (practice, live) | 73-75 | ✅ صلب لكن `validation_config.py` يقبل أيضاً (paper) في `execution_check.py`، فالقيم ليست متطابقة 100% |
| 12 | رصيد الحساب موجب | 77-79 | ✅ صلب |

**النتيجة:** الـ 12 فحصاً كلّها صحيحة منطقياً، لكن 3 منها (#4،#5،#6) تعتمد على متغيّرات داخل `EngineV3` بالذاكرة، تُفقَد عند إعادة تشغيل الحاوية، وهذا فجوة سلامة حقيقية في الإنتاج طويل العمر.

### 6.4 `validation_config.py` — السقوف الصلبة

```py
ABSOLUTE_MAX_RISK_PCT = 0.5             # 0.5% per trade
ABSOLUTE_MAX_DAILY_LOSS_PCT = 3.0       # 3% daily
ABSOLUTE_MAX_TRADES_PER_DAY = 10
ABSOLUTE_MAX_CONSECUTIVE_LOSSES = 3
MIN_RR_FOR_LIVE = 1.2
```

`validate_or_die()` يرفع `SystemExit` لو أيّ سقف تجاوز الحد المطلق. الافتراضات: `risk_pct_per_trade=0.25`، `daily_loss_limit_pct=2.0`، `consecutive_losses_limit=2`، `daily_trade_limit=5`. `pair_status` ثابت في الـ dataclass، يتطابق مع `execution_check.PAIR_STATUS`. هذه أكثر طبقة موثوقة في كلّ V3 — حماية صريحة ضد متغيّرات بيئة عدوانية.

**ملاحظة دقيقة:** `from_env()` يقرأ `OANDA_ENV` كـ `broker_env`، لكنّ `safety_rails.py:73` يفحص `("practice", "live")`، بينما `gatemind.execution_check.check` يقبل `("paper", "live", "sandbox")`. عدم اتّساق طفيف لكنه لا يفتح ثغرة (`safety_rails` أكثر صرامة).

### 6.5 `position_sizer.py` — حساب الحجم

- صيغة: `units = (balance * risk_pct/100) / (stop_pips * pip_value_per_unit)`
- قيود: `risk_pct ∈ (0, 0.5]`، balance>0، stop_distance>0، units≥1.
- pip_value: 0.0001 لـ EUR/USD (USD account)، 0.01/price لـ USD/JPY (≈0.000067).
- منطق صحيح لـ "USD as quote" و"USD as base"، **لكن** الفرع الأخير `# Cross pair — needs conversion rate (rare in our setup)` يرجع `pip_size` بلا تحويل (`position_sizer.py:46`)، أي أنه سيُحجّم خاطئاً لأي زوج cross غير مدعوم.

### 6.6 `integration_proof.py` — تغطية الاختبار من طرف لطرف

- 5 سيناريوهات: aligned A+، B grade، C grade، news block، outside session.
- **مفاجأة كبيرة:** `expected_decision="block"` في **كل السيناريوهات الخمسة**. لا يوجد سيناريو إيجابي يثبت أنّ النظام يستطيع فعلاً قول "enter".
- يستخدم `make_bars` ببيانات اصطناعية لينة (slope ثابت + noise صغير). تعليق داخلي صريح: `synthetic data triggers chart_grade_C + stop_too_wide at gate`.
- يثبت أنّ خط أنابيب التسجيل يعمل (audit_id يتطابق بين GateDecision و SmartNoteBook event)، وأنّ الـ Gate لا يُتجاوَز.

**الخلاصة:** الاختبار يثبت السلامة (لا يوجد bypass)، **لكنّه لا يثبت أنّ النظام قادر على إنتاج أمر صحيح حقيقي.**

### 6.7 `main_v3.py` — نقطة الدخول

- يستورد Engine V3 + LLM + يفحص الاتصال بـ OpenAI.
- الحلقة: heartbeat كل `POLL_INTERVAL_SEC` ثانية، **لا تجلب شموع، لا تحلّل، لا تتداول**:
  ```py
  # Future: pull OANDA candles → brain analysis → LLM review → GateMind → execute
  # For now: idle. LLM layer is wired and ready.
  ```
- **أيّ تنفيذ live يحتاج إلى ربط feed→ChartMind→MarketMind→NewsMind→Engine يدوياً، وهو غير موجود.**

### 6.8 LLM layer — `llm/openai_brain.py`

- 256 سطراً. عميل HTTP بسيط مبنيّ على `urllib` بدون حزم خارجية.
- `LLM_AVAILABLE = bool(OPENAI_API_KEY)` — fail-safe لو لم يوجد المفتاح.
- نموذج افتراضي `gpt-4o-mini` (لكن `docker-compose.yml` يضع `gpt-5` كافتراضي).
- توقيت 5 ثوانٍ، 300 token، JSON-only response_format.
- `review_brain_outputs` يرجع `LLMReview` مع severity/suggestion. **لا يستطيع الترقية، فقط التخفيض** (allow→wait→block).
- **لكن `EngineV3.py` لا يستدعي `review_brain_outputs` في `decide_and_maybe_trade`!** فالطبقة موصولة لكن غير مُستهلَكة. التعليق في `main_v3.py` يؤكّد ذلك: "LLM layer is wired and ready" أي "جاهزة" لا "تعمل".

---

## 7) الخلاصة الإستراتيجية

### 7.1 درجة الصحة الإجمالية للنظام: **C-**

**التبرير في فقرة واحدة:** البنية الهندسية لـ Engine V3 ممتازة على الورق — default-deny متعدّد الطبقات، sliders صلبة لا تتجاوزها متغيّرات البيئة، تسجيل ذو مسارَين (SQLite + JSONL)، وتقسيم وظائف نظيف بين الأدمغة الخمسة. لكن بمجرّد فحص الكود، النتائج صادمة: **NewsMind لا يجلب أيّ خبر** (كل المحوّلات `_do_fetch` ترجع `[]`)، **MarketMind لا يستلم Gold/SPX/Yields في الإنتاج**، **`engine/v3/main_v3.py` حلقة heartbeat فارغة** لا تُداول، **طبقة LLM موصولة لكن غير مستدعاة من Engine**، **integration_proof يتوقّع `block` في كل السيناريوهات الخمسة**، و**`Dockerfile` يشغّل `main.py` (النسخة القديمة) لا `main_v3.py`**. النسخة V3 إذن نظام معماري متكامل عقلياً ولكنه غير موصول كهربائياً بالسوق ولا بالبروكر. أيّ "live" حالياً يجري عبر الكود القديم في `Engine.py` و `ChartMind/`.

### 7.2 أكبر 3 مخاطر لو شُغِّل النظام على حساب حقيقي اليوم

1. **NewsMind أعمى تماماً عن الأخبار:** فقط نوافذ التقويم (لو حُقن `HistoricalCalendar`) ستحمي من NFP/FOMC. أيّ خبر طارئ — تدخّل بنك ياباني، تصريح سياسي، حدث جيوسياسي — سيمرّ كأنّه "no_blocking_news" وسيُسمح بالتداول أثناء انفجار السوق.
2. **`atr=0.001` و `entry_price=1.0` ثوابت في EngineV3:** `decide_and_maybe_trade` يحقن قيمتي السعر و ATR كأرقام صلبة (`EngineV3.py:155, 158`). أيّ زوج JPY قيمته ~150 سيرفض كل صفقاته كـ stop_too_wide تلقائياً، وأيّ EUR/USD قد يحصل على enter زائف لو السعر الفعلي يصدف قريباً من 1.0. التطبيق المباشر يكسر منطق `risk_check` تماماً.
3. **حدود الخسارة اليومية والـ consecutive_losses في الذاكرة فقط:** `EngineV3.daily_loss_pct/consecutive_losses/trades_today` لا تُحفَظ على القرص (التعليق نفسه: "would be loaded from notebook in production"). إعادة تشغيل الحاوية بعد خسارة 1.5% تجعل العدّاد صفراً ويستأنف التداول. هذا عيب fail-open في طبقة سلامة كان يفترض أنها fail-closed.

### 7.3 أعلى 3 تحسينات ذات رافعة عالية بعد ذلك

1. **توصيل أنابيب البيانات الحقيقية** قبل أيّ شيء آخر:
   - تنفيذ `_do_fetch` لـ Reuters/Bloomberg/Forexlive RSS (10 سطور بـ `feedparser` لكل مصدر).
   - حقن `HistoricalCalendar` (موجود في `Backtest/calendar.py` بحسب التفقّد) في `EventScheduler` افتراضياً.
   - في `EngineV3` تمرير شموع XAU/SPX (إن جُلبت) إلى `MarketMindV3.assess`.
   - في `EngineV3.decide_and_maybe_trade` استبدال `atr=0.001` و `entry_price=1.0` بقيم حقيقية محسوبة من الشموع.
2. **تثبيت العدّادات على القرص:**
   - حفظ `daily_loss_pct/consecutive_losses/trades_today` في SQLite ضمن جدول `engine_state`، تُحمَّل عند الإقلاع.
   - تكملة `update_after_close` ليكتب `exit_time/exit_price/pnl/exit_reason` على `TradeAuditEntry` المخزّنة (UPDATE).
3. **اختبار قبول إيجابي واحد على الأقل:**
   - السيناريو السادس في `integration_proof.py` يجب أن يتوقّع `decision="enter_dry_run"` بشموع حقيقية (مثلاً سحب يوم تاريخي من OANDA بسيط) ليثبت أنّ الـ Gate قادر فعلاً على قول enter.
   - هذا الاختبار اليوم غير موجود، وعدم وجوده يعني أنّ خطّ السلامة لا يُختبَر إلا من جهة "block".

### 7.4 هل القلق مبرَّر؟

**نعم، القلق مبرَّر — لكنه ليس قلق "كارثة وشيكة"، بل قلق "نظام نصف مكتمل يُسوَّق كأنّه كامل".** الكود كقطعة هندسية مكتوب بعناية واضحة: تعليقات نظيفة، تكرار قليل، defaults آمنة. لكن قراءة دقيقة تكشف أنّ:

- **النسخة V3 لم تُربَط بعد بالإنتاج**؛ هي عمل تحت الإنشاء، وكل ما يجري في حاوية Docker هو النسخة القديمة من `main.py` التي يقول أصحابها أنفسهم في `AUDIT_VERDICT.md` و `DIAGNOSTIC.md` إنها "غير صالحة للتشغيل الحقيقي" بسبب غياب edge في ChartMind v1 (backtest على سنتين OANDA حقيقية كشف عن سالب expectancy على 96 اختباراً).
- **وجود نسختين متوازيتين في نفس المستودع** أزمة تنظيمية حقيقية: المالك قد يظنّ أنّ التحسينات على V3 تنعكس فوراً على الإنتاج، لكنّها لا تنعكس. هذا الالتباس بحدّ ذاته خطر.
- **طبقة LLM موصولة بـ openai لكن لا يستدعيها أحد** في المسار النهائي — أيّ مفتاح OpenAI مُفعَّل اليوم في docker-compose يُهدَر بلا فائدة.
- **safety_rails ممتازة منطقياً** ولن تسمح بصفقة كارثية لو شُغِّلت كاملة، لكنّها لن تشتغل أصلاً قبل أن تجلب الأنابيب بياناتها.

**التوصية الصريحة:** لا تشغّل V3 على حساب حقيقي قبل تنفيذ التحسينات الـ 3 أعلاه على الأقل، وتشغيل دورة paper-trading لمدّة 30 يوماً تنتج صفقات فعلية (لا مجرّد heartbeat) تُسجَّل في SmartNoteBook، ثم مراجعة تلك الصفقات قبل التحويل إلى live. الحالة الراهنة: **V3 لا تتداول، النسخة القديمة تتداول بنتائج سالبة موثَّقة، إذن النظام كلّه يجب أن يبقى في وضع البحث.**

---

## 8) تنظيم الملفات المقترح

### الوضع الحالي
الجذر يحتوي على ست مجلدات قديمة بأحرف كبيرة (`ChartMind/`, `ChartMindV2/`, `MarketMind/`, `NewsMind/`, `GateMind/`, `SmartNoteBook/`) بالإضافة إلى `LLMCore/`، `OandaAdapter/`، `Engine.py`، `main.py`، و `position_monitor.py`، وكلّها تُكوِّن النسخة القديمة. وفي الوقت ذاته توجد المجلدات الجديدة بأحرف صغيرة: `chartmind/v3/`, `marketmind/v3/`, `newsmind/v2/`, `gatemind/v3/`, `smartnotebook/v3/`, `engine/v3/`, `llm/`. هذا التداخل خطر تنظيمي يجب حلّه.

### البنية المقترحة

```
hydra/
├── README.md
├── pyproject.toml                      # تعريف الحزمة الموحّد
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── src/
│   └── hydra/
│       ├── __init__.py
│       ├── chartmind/                  # محتوى chartmind/v3 الحالي
│       ├── marketmind/                 # محتوى marketmind/v3
│       ├── newsmind/                   # محتوى newsmind/v2
│       ├── gatemind/                   # محتوى gatemind/v3
│       ├── smartnotebook/              # محتوى smartnotebook/v3
│       ├── engine/                     # engine/v3 + main_v3.py كنقطة دخول
│       ├── llm/                        # llm/openai_brain.py
│       ├── adapters/
│       │   ├── oanda/                  # OandaAdapter الحالي
│       │   └── feeds/                  # محوّلات RSS/News الحقيقية
│       └── backtest/                   # Backtest/ الحالي
├── tests/
│   ├── unit/
│   │   ├── chartmind/
│   │   ├── marketmind/
│   │   ├── newsmind/                   # نقل test_intelligence + test_newsmind_v2
│   │   ├── gatemind/
│   │   └── smartnotebook/
│   ├── integration/
│   │   └── test_engine_e2e.py          # integration_proof.py محسّناً + سيناريوهات إيجابية
│   └── certification/                  # كل ملفات cert_*.py و audit_*.py مجمّعة
├── scripts/                            # محتوى scripts/ الحالي
├── docs/
│   ├── architecture.md
│   ├── safety-model.md
│   └── runbook.md                      # LIVE_VALIDATION_RUNBOOK + INTEGRATION_ACCEPTANCE
├── deploy/
│   └── hostinger-deploy.yml
└── archive/                            # أرشفة فقط — لا استخدام
    ├── ChartMind/
    ├── ChartMindV2/
    ├── MarketMind/
    ├── NewsMind/
    ├── GateMind/
    ├── SmartNoteBook/
    ├── LLMCore/
    ├── Engine.py
    ├── main.py
    └── position_monitor.py
```

### ملاحظات تنظيمية

1. **حذف النسخ القديمة من الإنتاج فوراً (نقلها إلى `archive/`):** هي مرجع تاريخي مفيد لأنّ بعض الأفكار فيها (`SmartNoteBook/journal.py`, `SmartNoteBook/post_mortem.py`, `ChartMind/wyckoff.py`) لم تنتقل إلى V3 وقد يحتاجها مالك المشروع لاحقاً. لكن يجب إخراجها من PYTHONPATH حتى لا يستوردها أحد بالخطأ.
2. **توحيد نقطة الدخول:** الـ Dockerfile الحالي يقول `CMD ["python", "/app/main.py"]` — يجب أن يصير `CMD ["python", "-m", "hydra.engine.main"]` بعد النقل، ليُحسم نهائياً أيّ نسخة يشغّلها الإنتاج.
3. **الحفاظ على جذر `Backtest/` كما هو:** لأنّ `Engine.py` القديم يستورد منه وإذا أرشف فجأة سيكسر الباك-تست. إذن يجب أرشفته فقط بعد التأكّد من فصل تبعيات Backtest عن Engine القديم.
4. **هذه التوصية وصف فقط، لا تنفيذ — كما طلب المستخدم.**

