# HYDRA V4 — Complete Trading System

**نظام تداول آلي لـ EUR/USD و USD/JPY على نوافذ نيويورك**

## البنية

```
Desktop\HYDRA V4\
│
├── HYDRA V4 CODE (محتوى المجلد الرئيسي — code lives here)
│   ├── contracts\
│   │   └── brain_output.py       # العقد الموحَّد لكل العقول
│   │
│   ├── newsmind\v4\               # العقل #1 — الأخبار
│   ├── marketmind\v4\             # العقل #2 — الماكرو
│   ├── chartmind\v4\              # العقل #3 — الشارت
│   ├── gatemind\v4\               # العقل #4 — البوابة الصارمة
│   ├── smartnotebook\v4\          # العقل #5 — الذاكرة
│   ├── orchestrator\v4\           # النخاع الشوكي — يربط العقول
│   │
│   ├── config\                    # YAML configs
│   └── *.git\                     # git history
│
└── All files\                     # الوثائق والتقارير
    ├── HYDRA_V4_README.md         # هذا الملف
    ├── HYDRA_V4_FIVE_MINDS_INTEGRATION_REPORT.md
    ├── NEWSMIND_V4_FREEZE_REPORT.md
    ├── MARKETMIND_V4_FREEZE_REPORT.md
    ├── CHARTMIND_V4_FREEZE_REPORT.md
    ├── GATEMIND_V4_FREEZE_REPORT.md
    └── SMARTNOTEBOOK_V4_FREEZE_REPORT.md
```

> **ملاحظة بنية**: الكود يبقى في الجذر للحفاظ على Python imports + git history. مجلد `All files\` للوثائق فقط.

## التشغيل بنقرة واحدة

دبل-كليك على:
```
Desktop\Run_HYDRA_V4.bat
```

السكربت يسوي:
1. يفحص بيئة Python
2. يشغّل ٦٣٢ اختبار (٥٣٨ brain + ٩٤ orchestrator)
3. يطبع تقرير حالة النظام
4. **لا يفتح صفقات. لا يستخدم OANDA live. لا يطبع secrets.**

## الإحصائيات النهائية

| Component | حالة | Tests |
|---|---|---|
| NewsMind V4 | 🔒 Frozen | 49 |
| MarketMind V4 | 🔒 Frozen | 116+ |
| ChartMind V4 | 🔒 Frozen | 120 |
| GateMind V4 | 🔒 Frozen | 138 |
| SmartNoteBook V4 | 🔒 Frozen | 115 |
| Orchestrator V4 | 🔒 Integrated | 94 |
| **TOTAL** | | **632** |

## القواعد غير القابلة للكسر

- **التداول فقط على EUR/USD + USD/JPY**
- **التداول فقط في نوافذ نيويورك:** 03:00-05:00 + 08:00-12:00 NY
- **GateMind صارم:** 3/3 + A/A+ + أي B = BLOCK
- **Claude downgrade-only** — لا يقدر يرفع BLOCK إلى ENTER
- **No live orders** أثناء أي اختبار
- **No data leakage** — `verify_chain` على SmartNoteBook
- **No silent failures** — كل برنامج له fail-CLOSED + loud propagation

## الخطوات المسموحة بعد التجميد

١. **Backtester V4** — يستهلك Orchestrator في loop على بيانات OANDA حقيقية
٢. **Risk/Execution Layer** — يستهلك `gate_decision.trade_candidate`
٣. **Dashboard** — يقرأ من SmartNoteBook reports
٤. **إضافة أزواج** (GBPUSD, AUDUSD) — symbol parameter بدون كود إضافي

## الخطوات الممنوعة

- ❌ تعديل أي عقل مُجمَّد إلا إذا integration كشف bug حقيقي موثَّق
- ❌ تجاوز GateMind بأي طريقة
- ❌ live orders بدون practice ٤ أسابيع
- ❌ تخفيف القواعد لتحقيق صفقتين يومياً أو ١٥٠٪
