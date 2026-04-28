# HYDRA V3 — نظام تداول بخمسة عقول

نظام تداول EUR/USD مبنيّ على ٥ عقول مستقلة + منسّق + طبقة LLM اختيارية. **يشتغل محلياً على لابتوب بـ Python 3.10+ — لا VPS، لا Docker.**

## البنية المعمارية

النظام يتكوّن من خمسة عقول قابلة للاختبار باستقلال + منسّق. كل عقل يتولّى مسؤولية معرفية واحدة؛ لا يستورد أي عقل من الآخر — يلتقون فقط داخل `Engine`.

```
┌────────────┐   ┌────────────┐   ┌────────────┐
│ ChartMind  │   │ MarketMind │   │  NewsMind  │
│  V3 (TA)   │   │ V3 (Macro) │   │  V3 (News) │
└─────┬──────┘   └─────┬──────┘   └─────┬──────┘
      │                │                │
      │   BrainGrade   │  BrainGrade    │  BrainGrade
      └────────────────┼────────────────┘
                       ▼
                 ┌──────────┐         ┌────────────────┐
                 │ GateMind │ ◀─────▶ │ SmartNoteBook  │
                 │ V3 (Gate)│         │  V3 (Memory)   │
                 └────┬─────┘         └────────────────┘
                      ▼
              ┌──────────────┐
              │  EngineV3    │  ينسّق العقول الخمسة
              │  main_v3.py  │  بقاعدة halt-first + memory-first
              └──────────────┘
```

| العقل | الدور الميكانيكي |
|---|---|
| **ChartMind V3** | تحليل فني (Price Action / SMC / ICT / Wyckoff). ينتج `TradePlan`. |
| **MarketMind V3** | ماكرو (DXY synthetic / RORO / strength index). ينتج `MarketContext`. |
| **NewsMind V3** | أحداث مجدولة + headlines + narratives. ينتج `NewsContext`. |
| **GateMind V3** | البوابة الوحيدة: kill-switches + sizing + routing. لا bypass. |
| **SmartNoteBook V3** | الذاكرة المؤسسية: journal + post/pre-mortem + lessons. |

`EngineV3` يفرض ٣ قواعد أولوية:
1. **Halt-first** — أي blackout/halt/kill يلغي التداول حتى مع plan ممتاز.
2. **Memory-first** — SmartNoteBook يحقن lessons في كل عقل قبل تكوين grade.
3. **LLM downgrades only** — طبقة LLM تخفّض فقط ولا ترفع. Asymmetric authority.

## التشغيل المحلي على Windows

### المتطلبات
- Python 3.10+ (مع `Add to PATH` مفعّلاً)
- Git for Windows
- حساب OANDA (practice مفضّل في البداية)
- مفتاح API (OpenAI أو Anthropic — اختياري للـ LLM)

### خطوات التثبيت

```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/Alghananim/newsmind.git hydra-v3
cd hydra-v3
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env   # عبّي مفاتيح API
```

### التشغيل

```powershell
cd $env:USERPROFILE\Documents\hydra-v3
.\.venv\Scripts\python.exe main_v3.py
```

أو دبل-كليك على `HYDRA V3.bat` على سطح المكتب (إذا ركّبت اختصار سطح المكتب).

## بنية المجلدات

```
hydra-v3/
├── chartmind/v3/         ← العقل #1
├── marketmind/v3/        ← العقل #2
├── newsmind/v3/          ← العقل #3
├── gatemind/v3/          ← العقل #4
├── smartnotebook/v3/     ← العقل #5
├── engine/v3/            ← المنسّق + safety_rails
├── llm/                  ← LLM layer (OpenAI/Anthropic)
├── config/news/          ← YAML: events, sources, narratives, keywords
├── Backtest/             ← أدوات الباك-تست (utility)
├── scripts/              ← walk-forward + variants tests
├── archive/              ← V1/V2 محفوظ كمرجع تاريخي (راجع archive/README.md)
└── main_v3.py            ← نقطة الدخول
```

## ضوابط الأمان (Safety)

- `ABSOLUTE_MAX_RISK_PCT = 0.5%` — الكود يرفض أي قيمة أعلى بـ `SystemExit`.
- `risk_pct_per_trade = 0.25%` افتراضياً.
- `default-deny` متعدد الطبقات: عند الشك → block.
- **GateMind بوابة وحيدة**: لا تنفيذ بدون موافقتها (لا bypass).
- **SmartNoteBook يسجّل كل قرار** بـ `audit_id` متطابق.
- **safety_rails (12 فحص)** قبل أي أمر — راجع `engine/v3/safety_rails.py`.

> ⚠️ راجع `CREDENTIAL_SAFETY_NOTICE.md` — أي مفاتيح كانت في commits قديمة لازم تُلغى وتُستبدل.

## التطوير القادم

- إصلاحات ما بعد التدقيق (راجع `HYDRA_V3_AUDIT.md`):
  - توصيل أنابيب البيانات الحقيقية (NewsMind RSS، OANDA candles)
  - تثبيت counters على القرص بدل RAM
  - إضافة سيناريو positive في integration_proof
- استراتيجيات بحثية جديدة (mean-reversion / statistical edge)
- توسيع backtest على أزواج إضافية

## الترخيص و المسؤولية

هذا نظام بحث وتطوير. **التداول الحقيقي على مسؤوليتك** — راجع نتائج الـ backtest في `AUDIT_VERDICT.md` و `DIAGNOSTIC.md` قبل أي قرار live.
