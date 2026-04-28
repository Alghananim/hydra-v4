# دليل تثبيت HYDRA V3 على اللابتوب (Windows)

> **HYDRA V3** = نظام تداول بخمسة عقول (5 رؤوس مثل أسطورة الهيدرا).
> العقول: ChartMind | MarketMind | NewsMind | GateMind | SmartNoteBook.
> المنسّق: EngineV3 + safety_rails (12 فحص نهائي قبل أي أمر).

---

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

## ملاحظة حول الاسم

اسم المشروع المعتمد لدينا الآن: **HYDRA V3**.

لكن مستودع الـ GitHub لسّه باسمه القديم: `https://github.com/Alghananim/newsmind.git`.
السكربت يستنسخ من هذا الـ URL ويثبّته في مجلد محلي اسمه `hydra-v3`. **التعليمة لاحقة لمن نريد إعادة تسمية الـ repo نفسه على GitHub** (إجراء منفصل).

---

## خطوات التثبيت (مرة واحدة فقط)

### 1) شغّل سكربت التثبيت

دبل-كليك على الملف:

```
setup_hydra_v3.bat
```

السكربت راح يسألك عن مسار التثبيت. الافتراضي:

```
C:\Users\Mansur\Documents\hydra-v3
```

اضغط Enter لقبول المسار، أو اكتب مسار آخر تفضله ثم Enter.

السكربت راح يسوي:

1. يفحص Python و Git
2. يستنسخ مصدر HYDRA V3 من GitHub
3. ينشئ بيئة بايثون معزولة `.venv` داخل المجلد
4. يثبت المكتبات: `PyYAML, pandas, numpy, requests`
5. ينشئ ملف `.env` من القالب `.env.example`
6. يحفظ المسار في `hydra_v3_path.txt` عشان `run_hydra_v3.bat` يعرف وين المشروع

---

### 2) عبّي مفاتيح API في `.env`

افتح الملف:

```
<مسار التثبيت>\.env
```

(مثلاً: `C:\Users\Mansur\Documents\hydra-v3\.env`)

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

### 3) شغّل HYDRA V3

دبل-كليك على:

```
run_hydra_v3.bat
```

السكربت راح يسألك أي entry point تريد:

| الخيار | الملف | متى تستخدمه |
|---|---|---|
| **1 (افتراضي)** | `main_v3.py` | HYDRA V3 — العقول الخمسة V3 + LLM layer (الموصى به) |
| 2 | `main.py` | الإصدار القديم (للتجارب فقط) |

اضغط **1** ثم Enter.

---

## كيف توقف النظام

داخل النافذة شغّالة، اضغط **Ctrl+C**. النظام يحفظ الـ state ويغلق بشكل آمن.

---

## استكشاف الأخطاء (Troubleshooting)

### `python --version` يطلع خطأ بعد ما ثبّت Python
- معناه Python ما انضاف للـ PATH. أعد تثبيته وعلّم على "Add Python to PATH".
- بدائل: استخدم `py --version` بدل `python --version`.

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
- شغّل `setup_hydra_v3.bat` من جديد - راح يكتشف إن المشروع موجود ويعمل `git pull`.

---

## تحديث المشروع لاحقاً

**الطريقة 1 (يدوي):**
```
cd C:\Users\Mansur\Documents\hydra-v3
git pull
.venv\Scripts\activate
pip install -r requirements.txt
```

**الطريقة 2 (تلقائي):** أعد تشغيل `setup_hydra_v3.bat`.

---

## بنية المشروع المثبت (HYDRA V3)

```
hydra-v3\
├── .venv\                  ← بيئة بايثون المعزولة
├── .env                    ← مفاتيحك الخاصة (لا تشاركها أبداً)
├── main_v3.py              ← نقطة دخول HYDRA V3 (الإنتاج)
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
setup_hydra_v3.bat

:: تشغيل
run_hydra_v3.bat

:: تحديث
setup_hydra_v3.bat   (يعمل git pull إذا المشروع موجود)
```

---

## إعادة تسمية الـ GitHub repo (خطوة اختيارية لاحقة)

إذا تبي تحوّل اسم الـ repo نفسه على GitHub من `newsmind` إلى `hydra-v3`:

1. روح على: https://github.com/Alghananim/newsmind
2. Settings → General → Repository name → غيّره إلى `hydra-v3`
3. اضغط **Rename**
4. GitHub راح يحوّل تلقائياً أي طلبات للرابط القديم للجديد، لكن أفضل تحدث:
   - في `setup_hydra_v3.bat` عدّل الـ URL لـ `https://github.com/Alghananim/hydra-v3.git`
   - في الـ origin المحلي: `git remote set-url origin https://github.com/Alghananim/hydra-v3.git`

> ملاحظة: Hostinger Docker compose يستخدم نفس الـ repo، فأي تغيير في URL لازم يتزامن مع `docker-compose.yml`.

---

تم بناء هذه الحزمة لتشغيل HYDRA V3 محلياً (laptop development mode). الإنتاج الفعلي على **Hostinger VPS عبر Docker** من نفس الـ repo (راجع `docker-compose.yml` و `hostinger-deploy.yml` داخل المشروع).
