> **هذا الملف قديم. استخدم `INSTALL_GUIDE_HYDRA_V3.md` بدلاً منه.**

# دليل تثبيت NewsMind على اللابتوب (Windows) — DEPRECATED

## المتطلبات الأساسية

قبل ما تشغّل سكربت التثبيت، تأكد إن عندك:

| الأداة | الإصدار | الرابط |
|---|---|---|
| **Python** | 3.10 أو أحدث | https://www.python.org/downloads/ |
| **Git for Windows** | أي إصدار حديث | https://git-scm.com/download/win |
| اتصال إنترنت | — | للاستنساخ من GitHub وتنزيل المكتبات |

> **مهم جداً عند تثبيت Python:** حط علامة على خيار **"Add Python to PATH"** في أول شاشة، وإلا السكربت ما راح يلقاه.

للتأكد من التثبيت، افتح **PowerShell** أو **CMD** واكتب:

```
python --version
git --version
```

لازم يطلع لك إصدار لكل واحد. إذا طلع خطأ، أعد تثبيت الأداة المفقودة.

---

## خطوات التثبيت (مرة واحدة فقط)

### 1) شغّل سكربت التثبيت

دبل-كليك على الملف:

```
setup_newsmind.bat
```

السكربت راح يسألك عن مسار التثبيت. الافتراضي:

```
C:\Users\Mansur\Documents\newsmind
```

اضغط Enter لقبول المسار، أو اكتب مسار آخر تفضله ثم Enter.

السكربت راح يسوي:

1. يفحص Python و Git
2. يستنسخ المشروع من https://github.com/Alghananim/newsmind.git
3. ينشئ بيئة بايثون معزولة `.venv` داخل مجلد المشروع
4. يثبت المكتبات: `PyYAML, pandas, numpy, requests`
5. ينشئ ملف `.env` من القالب `.env.example`
6. يحفظ المسار في `newsmind_path.txt` عشان `run_newsmind.bat` يعرف وين المشروع

---

### 2) عبّي مفاتيح API في `.env`

افتح الملف:

```
<مسار التثبيت>\.env
```

(مثلاً: `C:\Users\Mansur\Documents\newsmind\.env`)

وعبّي القيم الحقيقية:

```ini
# OpenAI - من https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-...مفتاحك_الحقيقي...

# OANDA - من حسابك في https://oanda.com (Practice أولاً!)
OANDA_API_TOKEN=...توكن_OANDA_practice...
OANDA_ACCOUNT_ID=101-001-XXXXXXXX-001
OANDA_ENVIRONMENT=practice          # ← لازم practice في البداية
```

> **تحذير أمان (راجع `CREDENTIAL_SAFETY_NOTICE.md` داخل المشروع):**
> أي مفاتيح كانت مسربة في الـ commits السابقة لازم تُلغى من OANDA + OpenAI وتُستبدل بمفاتيح جديدة. لا تستخدم القديمة أبداً.

> **تحذير مالي:** خلّ `OANDA_ENVIRONMENT=practice` لحد ما يكمل النظام 5 أيام نظيفة على الـ practice. بعدها فقط حوّله `live` ببدء `risk_pct_per_trade=0.25%`.

---

### 3) شغّل النظام

دبل-كليك على:

```
run_newsmind.bat
```

السكربت راح يسألك أي entry point تريد:

| الخيار | الملف | متى تستخدمه |
|---|---|---|
| **1 (افتراضي)** | `main_v3.py` | Engine V3 — العقول الخمسة V3 + LLM layer (الموصى به) |
| 2 | `main.py` | الإصدار القديم (للتجارب فقط) |

اضغط **1** ثم Enter.

---

## كيف توقف النظام

داخل النافذة شغّالة، اضغط **Ctrl+C**. النظام يحفظ الـ state ويغلق بشكل آمن.

---

## استكشاف الأخطاء (Troubleshooting)

### `python --version` يطلع خطأ بعد ما ثبّت Python
- معناه Python ما انضاف للـ PATH. أعد تثبيته وعلّم على "Add Python to PATH".
- بدائل: استخدم `py --version` بدل `python --version`، وعدّل سكربت setup ليستخدم `py`.

### `git --version` يطلع خطأ
- ثبّت Git for Windows. بعد التثبيت أعد فتح CMD/PowerShell.

### `pip install` يفشل بسبب pandas أو numpy
- جرّب: من داخل `.venv` نفّذ `pip install --upgrade pip setuptools wheel` ثم `pip install -r requirements.txt` مرة ثانية.
- إذا استمرت المشكلة، شغّل CMD كـ Administrator ونفذ السكربت من جديد.

### `OANDA practice` يرفض الاتصال
- تأكد إن الـ token من حساب practice مو live.
- تأكد من `OANDA_ACCOUNT_ID` بالشكل الصحيح: `101-001-XXXXXXXX-001`.
- جرّب من المتصفح: https://api-fxpractice.oanda.com/v3/accounts (مع توكنك في Authorization header).

### الـ logs تطلع لكن ما تنفذ صفقات
- هذا متوقع! النظام `default-deny`. لازم العقول الخمسة كلها تتفق + GateMind يوافق.
- راجع `SmartNoteBook` journal لتعرف سبب كل block/wait.
- في البداية على practice، توقع 90%+ من القرارات تكون `block` لأن الفلتر الإنتاجي = `kill_asia` فقط على EUR/USD.

### تبي تتحدث (pull) آخر تعديلات من GitHub
- شغّل `setup_newsmind.bat` من جديد - راح يكتشف إن المشروع موجود ويعمل `git pull`.

---

## تحديث المشروع لاحقاً

**الطريقة 1 (يدوي):**
```
cd C:\Users\Mansur\Documents\newsmind
git pull
.venv\Scripts\activate
pip install -r requirements.txt
```

**الطريقة 2 (تلقائي):** أعد تشغيل `setup_newsmind.bat`.

---

## بنية المشروع المثبت

```
newsmind\
├── .venv\                  ← بيئة بايثون المعزولة
├── .env                    ← مفاتيحك الخاصة (لا تشاركها أبداً)
├── main_v3.py              ← نقطة دخول Engine V3 (الإنتاج)
├── main.py                 ← الإصدار القديم
├── engine\v3\              ← المنسّق + safety_rails + position_sizer
├── chartmind\v3\           ← العقل #1 (التحليل الفني)
├── marketmind\v3\          ← العقل #2 (الماكرو)
├── newsmind\v2\            ← العقل #3 (الأخبار)
├── gatemind\v3\            ← العقل #4 (البوابة)
├── smartnotebook\v3\       ← العقل #5 (الذاكرة)
├── llm\                    ← OpenAI integration للعقول الخمسة
├── NewsMind\config\        ← YAML: events, sources, narratives, keywords
└── ...
```

---

## ملخص الأوامر السريعة

```bat
:: تثبيت أول مرة
setup_newsmind.bat

:: تشغيل
run_newsmind.bat

:: تحديث
setup_newsmind.bat   (يعمل git pull إذا المشروع موجود)
```

---

تم بناء هذه الحزمة لتشغيل المشروع محلياً (laptop development mode). الإنتاج الفعلي على **Hostinger VPS عبر Docker** من نفس الـ repo (راجع `docker-compose.yml` و `hostinger-deploy.yml` داخل المشروع).
