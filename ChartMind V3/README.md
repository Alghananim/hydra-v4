# ChartMind V3 — العقل الفني (Technical Analysis)

> العقل #1 من ٥ في نظام HYDRA V3.
> دوره: تحليل سعر/أنماط/ICT-SMC على الشموع وإنتاج `TradePlan` مع درجة A+/A/B/C.

## كيف يفكّر

يستقبل **شموع M15** (إلزامي ≥ ٦ شموع) + M5/M1 (اختياري) → يشغّل ١٢ مرحلة موقوتة:

1. data_load — التحقق من سلامة البيانات
2. structure — HH/HL/LH/LL + BoS + CHoCH (market_structure.py)
3. ATR — قياس التقلّب
4. support/resistance — مستويات الدعم والمقاومة
5. trend — اتجاه + قوة (ADX) + جودة (smooth/jagged/exhausting)
6. candle — الشموع وسياقها على المستوى
7. breakout — real/fake/pending/weak
8. pullback — clean/deep/shallow
9. multi_timeframe — محاذاة M15/M5/M1
10. entry_quality — excellent/good/marginal/late/chase/no_setup
11. risk_reward — حساب SL/TP و R:R
12. traps — liquidity sweep / bull-trap / bear-trap / chop / stop-hunt

ثم `permission_engine` يطبّق:
- **Hard-blocks**: أي trap → block
- **Hard-waits**: late entry / weak structure → wait
- **Grade ladder**: A+ / A / B / C / no_setup

## الملفات الرئيسية

| الملف | الدور |
|---|---|
| `ChartMindV3.py` | المنسّق — ١٢ مرحلة |
| `models.py` | `Bar`, `Level`, `ChartAssessment` |
| `market_structure.py` | HH/HL/LH/LL + BoS + CHoCH |
| `support_resistance.py` | مستويات الدعم والمقاومة |
| `trend.py` | الاتجاه و ADX |
| `candles.py` | كشف الشموع |
| `breakout.py` | حالة الاختراق |
| `pullback.py` | جودة الارتداد |
| `multi_timeframe.py` | محاذاة M15/M5/M1 |
| `entry_quality.py` | جودة الدخول |
| `stop_target.py` | SL/TP و R:R |
| `traps.py` | كشف الفخاخ |
| `permission_engine.py` | hard-blocks/waits + grade |
| `scoring.py` | تحويل تسميات إلى أرقام |
| `cache.py` | memoize (ATR/ADX) |
| `latency.py` | قياس زمن المراحل |
| `cert_v3.py` / `audit_*.py` | اختبارات داخلية |

## ملاحظات من تقرير التدقيق (HYDRA_V3_AUDIT.md)

**نقاط القوة:**
- منطق ١٢ مرحلة معزول وقابل للاختبار
- `permission_engine` صارم (default-deny)
- cache ذكي يقلل إعادة الحساب

**نقاط الضعف:**
- بعض التحقق من الإدخال غير صارم (شموع بأسعار سالبة قد تتسبب بأخطاء)
- `traps.py` يعتمد على ثوابت hardcoded تحتاج معايرة أكثر بأزواج JPY
- لا يوجد اختبار positive في `cert_v3.py` (كلها سيناريوهات block)

## كيف تعدل هذا العقل

> هذا المجلد **نسخة قراءة فقط** من المصدر.
> المصدر الفعلي في: `HYDRA V3\chartmind\v3\`
> أي تعديل يُفترض أن يتم هناك، ثم تُحدَّث هذه النسخة بإعادة النسخ.
