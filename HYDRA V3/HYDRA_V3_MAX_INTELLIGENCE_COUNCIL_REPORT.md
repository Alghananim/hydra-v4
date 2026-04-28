# HYDRA V3 — تقرير مجلس الذكاء الأقصى

**التاريخ:** 27 أبريل 2026
**المنهج:** ٥ Sub-Agents مستقلون، كل واحد بدور خبير عالمي، نتائج بأدلة file:line، ثم نقاش متبادل وقرار موحّد.
**الحالة:** التقرير لا يحتوي مجاملات. الكلام عام مرفوض. الأفكار التي لا تصمد أمام الاختبار تُرفض بالدليل.

---

## ١) تحليل كل Agent المستقل

### Agent #1 — Trading Systems Architect: **C+**

البنية صحيحة منطقياً (`EngineV3.decide_and_maybe_trade` هو المسار الوحيد، GateMind في موقعه الصحيح، default-deny مفروض)، لكن **المفاصل مكسورة**:
- `engine/v3/main_v3.py:88-102` حلقة heartbeat لا تتداول؛ التعليق صريح "Future: pull OANDA candles..."
- `gatemind/v3/execution_check.py:14-18` يحوي `PAIR_STATUS` مكرّر مستقل عن `ValidationConfig.pair_status` → مصدران متضاربان للحقيقة
- `gatemind/v3/contradictions.py:64-69` يقرأ `state.data_latency_ms` و `state.cooldown_until_utc` التي **EngineV3 لا يضبطها أبداً** → كاشف تضارب ميت
- `backtest_v2/runner.py:182-194` يعيد كتابة `safety_rails.check_all` على مستوى الموديول → تسريب process-wide

**الاكتشاف الأخطر:** ChartMind و MarketMind **يحسبان ADX/ATR-14 على نفس شموع M15 لنفس الزوج** (`chartmind/v3/trend.py:30-47` + `marketmind/v3/regime_detector.py:37-62`). الإشارة الفريدة لـ MarketMind هي cross-asset (DXY/XAU/SPX)، لكن في الباكتيست هذه الشموع `None` → **MarketMind يتحوّل إلى صدى ChartMind + خبر** → اتفاق "٣ من ٣" فعلياً = **٢ من ٣ مقنّع**.

### Agent #2 — Quant / Backtesting: **C-**

دفاع lookahead جيد بنيوياً (`LeakSafeBars` أفضل من ٩٠٪ من المحاولات)، لكن ٣ أخطاء "صدق" تدمر النتائج:

١. `calendar_provider.py:83-95` يُرجع `grade="B"` ثابت لكل bar غير حدث → **NewsMind صامت** + `per_brain_attribution.py:65-69` يحسب أن NewsMind صحيح في **كل** صفقة رابحة → **دقّة NewsMind = win rate رياضياً = كذبة قياس**.

٢. `metrics.py:197-199` Sharpe يُحسب بـ `mean(R)/stdev(R) × sqrt(252)` — يفترض ٢٥٢ صفقة/سنة. مع ٢ صفقة/يوم نحصل على ٥٠٠/سنة، لكن مع ٥٠/سنة → Sharpe مضخّم بـ ~٢٫٢×.

٣. `pnl_pct` مرجعه `initial_balance` (`broker_replay.py:173`) → لا compounding. نتيجة ١٥٠٪ قد تخفي drawdown ≥ -٥٠٪ في منتصف الفترة لأن الأرقام لا تتراكم بشكل صحيح.

**رياضيات صريحة:**
- ٢ صفقة/يوم تتطلب اتفاق ٣ عقول بنسبة ≥٨٪ من شموع نوافذ NY → غير واقعي. **التوقع المنطقي: ٠٫٥-١٫٠ صفقة/يوم، ١٣٠-٢٥٠ صفقة/سنة**.
- ١٥٠٪ تتطلب expectancy = ١٫٨٣ R/صفقة على ٢٠٠ صفقة/سنة → WR=٦٠٪ مع R:R=٣:١، لكن spread+slippage ≈ ٢ pips drag = ٠٫١٣R → الـ expectancy الحقيقي المطلوب = **١٫٩٦R**.

### Agent #3 — AI / Prompt Engineering: **C-**

Asymmetric authority بنيوياً مفروضة (`openai_brain.py:211`, `EngineV3.py:282`) — Claude لا يستطيع الترقية. **لكن** ٣ ثقوب هلوسة:

١. **الـ killer:** `openai_brain.py:162` — السطر `f"Pair: EUR/USD"` **مزروع صلباً**. لما النظام يقيّم USD/JPY، Claude يُسأل عن EUR/USD! → كل verdict على USD/JPY = هلوسة عن أداة مختلفة.

٢. `confidence` لا يُختبَر بحدّ أدنى (`openai_brain.py:213-219`) → block بثقة ٠٫٠٥ يحجب صفقة شرعية.

٣. `reasoning` نص حر يدخل `gate_decision.reason` نصياً (`EngineV3.py:290-303`) → سجل القرار قد يحوي تناقضاً ("blocked but Claude said safe").

**التكلفة:** ~$٠٫٠٠٠١/استدعاء. ٣٠ استدعاء/يوم × $٠٫٠٠٣/يوم. الباكتيست ٦ أشهر = $٠٫٦٥. **التكلفة ليست قيداً، التأخير ٥ ثواني هو القيد.**

### Agent #4 — Risk Management / Execution: **C+**

السقوف الصلبة جيدة (`validation_config.py:14-19`). ATR/SL حقيقيان (`stop_target.py:20-66`). لكن ٣ مسارات للخراب:

١. **monkey-patch يتسرّب عبر العمليات:** `runner.py:182-191` يعدّل `safety_rails.check_all` على الموديول. لا `try/finally` للاستعادة. لو ركض backtest ثم live engine في نفس Python process → السلامة معدّلة من backtest تظل سارية على live.

٢. **العدّادات بدون reset يومي:** `EngineV3.py` يحفظ `daily_loss_pct/consecutive_losses/trades_today` لكن لا يصفّرها يومياً. **اليوم ٢ يبدأ بقيم اليوم ١** → kill-switch يطلق false-trigger.

٣. **`consecutive_losses_limit` متضارب:** `validation_config.py:27` = ٢. `state_check.py:27` = ٣. → سلوك مختلف حسب أيّ طبقة تُستشار.

**رياضيات ١٥٠٪:**
عند r=٠٫٢٥٪، WR=٥٥٪، R:R=٢:٠:
- EV = +٠٫٦٥R/صفقة = +٠٫١٦٢٥٪
- ١٥٠٪ تتطلب ~٥٦٤ صفقة → ٢٫٢٥ صفقة/يوم أو WR=٥٨٪
- لكن: P(٢ خسارة متتالية) = ٠٫٤٥² = ٢٠٫٢٥٪ → kill-switch (consecutive_losses=٢) **يطلق ~٣٠+ مرة/سنة** → **يقتل الـ edge قبل تحقيق ١٥٠٪**.

### Agent #5 — Code Quality / Reliability: **C+**

١. **خمس نسخ مستقلة من ATR(14)**: `chartmind/v3/trend.py`, `marketmind/v3/regime_detector.py`, `engine/v3/_helpers.py`, `Backtest/runner.py`, `Backtest/regime.py` → أي تعديل في حاسبة ATR لا ينعكس على البقية.

٢. **`except: continue` صامت داخل `permission_engine`** (`marketmind:58, 71`، `chartmind:72, 84`) — لو لامبدا hard-block فشلت بسبب rename → الحجب يُتجاوَز بصمت.

٣. **`_persist_state` يبتلع الاستثناءات** (`EngineV3.py:174-182`) — فشل الكتابة = فقدان عدّادات الحماية بصمت.

٤. **١٢+ رقم سحري في GateMind وحدها** — `0.3, 3.0, 0.8, 1.2, 0.7, 5.0, 50, 1024, 128`...

٥. **لا logging structured في EngineV3 ولا GateMind** — كل القرارات تتخذ بدون رؤية المدخلات.

---

## ٢) أخطر المشاكل التي اكتشفها كل Agent

| Agent | المشكلة الأخطر | الدليل |
|---|---|---|
| **Architect** | اتفاق "٣ من ٣" مقنّع — ChartMind و MarketMind يستخدمان نفس البيانات | `chartmind/v3/trend.py:30` + `marketmind/v3/regime_detector.py:37` |
| **Quant** | NewsMind silent دائماً → دقّته = win rate (كذبة قياس) | `calendar_provider.py:83-95` + `per_brain_attribution.py:65-69` |
| **AI/Prompt** | Claude يُسأل عن EUR/USD لكل صفقة USD/JPY (hardcoded prompt) | `llm/openai_brain.py:162` |
| **Risk** | Kill-switch consecutive_losses=2 يطلق ٣٠+ مرة/سنة عند WR=55% → يقتل edge قبل ١٥٠٪ | `validation_config.py:27` + رياضيات WR |
| **CodeQuality** | `except: continue` داخل permission_engine — صفقات تتجاوز حجب صامتاً | `marketmind/v3/permission_engine.py:58, 71` |

**المفارقة الأخطر:** **كل Agent اكتشف مشكلة لم يلاحظها الآخرون.** الفحص الفردي قبل المجلس كان غير كافٍ.

---

## ٣) أقوى الأفكار والخوارزميات المقترحة

### من Architect:
- **A1**: MarketMind يجب أن يـ block عند غياب companion bars (XAU/SPX) — fail-closed على عجز البيانات
- **A2**: Cohen's kappa بين ChartMind و MarketMind directions — يكشف overlap بنسبة قابلة للقياس
- **A3**: Information-theoretic gate (mutual information weighting) — حل احترافي بعيد المدى

### من Quant:
- **Q1**: Anchored walk-forward + ١-week embargo — توزيع زمني صادق
- **Q2**: Concentration test — لو إزالة ≤٥ أيام تكسر PF<1.0 → استراتيجية lottery، رفض
- **Q3**: Deflated Sharpe Ratio (López de Prado 2014) — تعديل multi-trial selection
- **Q4**: Sharpe annualisation by trade frequency (sqrt(N_trades_per_year)) بدل sqrt(252)

### من AI:
- **AI1**: Anthropic adapter مع `tool_choice` schema enforcement — لا prose escape
- **AI2**: `audit_hash = sha256(prompt + verdict)` يُحفَظ في SmartNoteBook — قابلية تدقيق ١٠٠٪
- **AI3**: Confidence floor للـ blocks (≥ 0.5)
- **AI4**: System prompt صريح: "you have NO upgrade authority"
- **AI5**: تمرير الـ pair الفعلي للـ user prompt — إصلاح bug #1

### من Risk:
- **R1**: Daily-risk-budget kill-switch (cumulative session risk ≤ 1٪ قبل ربح أول)
- **R2**: DD-triggered position-size halving (DD>1.5% → r×0.5 حتى التعافي)
- **R3**: Per-pair max-trades-per-session cap (1 صفقة/زوج/نافذة → ٤/يوم max)
- **R4**: Notional-to-balance ratio cap (≤ 50:1) في safety_rails — يمنع عدد lots مفرط
- **R5**: Daily reset عند UTC midnight + NY 17:00
- **R6**: NY session re-verification في safety_rails (طبقة ثانية)

### من CodeQuality:
- **C1**: ATR centralisation — مكتبة واحدة في `engine/v3/_helpers.py` تستوردها جميع المودولات
- **C2**: `tests/test_no_magic_numbers.py` — AST property test يكشف أي رقم سحري في gatemind
- **C3**: Structured logging على كل دخول/خروج من brain
- **C4**: Property-based tests على invariants `BrainSummary` / `GateDecision`
- **C5**: `engine_state` schema versioning + migration tests

---

## ٤) الاعتراضات المتبادلة بين Agents

### اعتراض ١: تقسيم EngineV3
- **CodeQuality يرفض** تقسيم `decide_and_maybe_trade` إلى ملفات → الفائدة في رؤية ١٠ خطوات top-to-bottom
- **Architect يقبل التقسيم** نظرياً (Single Responsibility) لكن **يوافق CodeQuality** على ضرورة بقاء التدفق واضحاً
- **القرار:** عدم التقسيم. تعليقات `# ---------- N. step name ----------` تكفي.

### اعتراض ٢: LLM richer
- **Quant يرفض** "LLM يصنّف كل bar" → ١٨ ساعة API serial في الباكتيست = غير قابل للتشغيل
- **AI/Prompt يوافق Quant** صراحة: latency = القيد الحقيقي
- **القرار:** Claude downgrade-only فقط على enter بعد GateMind. لا scoring لكل bar.

### اعتراض ٣: رفع الـ risk
- **Risk يرفض** "رفع r إلى 0.4% على A+/A+/A+"
- **Quant يوافق Risk** — confidence-weighting risk = hidden leverage
- **القرار:** r ثابت = 0.25%. تعديل المخاطر يحتاج walk-forward كامل.

### اعتراض ٤: hardcoded EUR/USD في prompt
- **AI/Prompt** اكتشف هذا
- **CodeQuality** لم يلاحظه (بحثه في magic numbers لم يصل لـ string templates)
- **Architect** لم ينتبه (ركّز على البنية)
- **الإجماع:** **bug حرج، إصلاح فوري**.

### اعتراض ٥: حذف `Backtest/` القديم
- **CodeQuality يرفض** الحذف الكامل — `backtest_v2/data_provider.py:46`, `broker_replay.py:28`, `calendar_provider.py:19` تستوردها
- **Architect يفضّل** التوحيد لكن يقبل الترحيل التدريجي
- **القرار:** هجرة قبل الحذف.

### اعتراض ٦: brain redundancy
- **Architect** يقول ChartMind+MarketMind يتداخلان (kappa probably > 0.7)
- **Quant** يوافق (NewsMind silent، MarketMind بدون cross-assets = صدى ChartMind)
- **Risk و CodeQuality** لم يعلقوا
- **الإجماع:** المشكلة حقيقية. **اختبار Cohen's kappa أولوية**.

---

## ٥) الأفكار المرفوضة ولماذا

| الفكرة | المُقترِح | السبب |
|---|---|---|
| رفع risk_pct إلى 0.4% على A+/A+/A+ | احتمالاً Quant/Risk | hidden leverage. يخالف ABSOLUTE_MAX_RISK_PCT. الكسر = خسارة الحساب. |
| LLM يصنّف كل bar (continuous feature) | احتمالاً Quant | latency 18 ساعة في الباكتيست. يحوّل Claude من ناقد إلى input. عدم تكرارية backtest. |
| LLM يستطيع الترقية في حالات "context واضح" | احتمالاً AI/Prompt | يكسر invariant downgrade-only. يخالف مواصفات المستخدم صراحة. |
| تخفيض الـ stop / توسيع الـ target لرفع WR | احتمالاً Risk | post-hoc parameter tweak — overfitting كلاسيكي. |
| تقسيم EngineV3.decide_and_maybe_trade | احتمالاً Architect | يخفي ترتيب الخطوات الـ ١٠ والـ invariants المتقاطعة. |
| ضبط ATR window per pair بناءً على نتائج backtest | احتمالاً Quant | overfitting بحت. النوافذ مشتركة لأن منطق ATR لا يتغير بالزوج. |
| السماح بـ alignment 2-of-3 مع high confidence | احتمالاً Quant | يخالف مواصفات المستخدم الصريحة. غير قابل للتفاوض. |
| حذف `Backtest/` (legacy) فوراً | احتمالاً CodeQuality | ٣ ملفات في `backtest_v2/` تستوردها. هجرة قبل حذف. |
| LLM upgrade على enter حسب confidence | احتمالاً AI/Prompt | يكسر authority asymmetry. الإجماع: مرفوض. |
| إجبار صفقتين/يوم بتقليل grade threshold | احتمالاً Quant | يخالف مواصفات المستخدم: "لا إجبار على صفقتين يومياً". |

---

## ٦) الأفكار المقبولة ولماذا

| الفكرة | السبب | المُقترِح |
|---|---|---|
| **MarketMind يـ block عند غياب companion bars** | يحوّل overlap الصامت إلى block صريح. fail-closed. | Architect |
| **Cohen's kappa test بين ChartMind/MarketMind** | يقيس الاستقلال الحقيقي بدليل رقمي | Architect |
| **Anchored walk-forward + 1-week embargo** | المعيار الذهبي للـ FX strategies؛ يكشف regime drift | Quant |
| **Concentration test (top-5-day P&L)** | يكشف "lottery equity curves" قبل أن تخدع | Quant |
| **Sharpe annualisation by trade frequency** | إصلاح خطأ رياضي قائم | Quant |
| **Anthropic adapter مع tool_choice + audit_hash** | schema enforcement + قابلية تدقيق ١٠٠٪ | AI |
| **تمرير pair الفعلي للـ Claude prompt** | إصلاح bug حرج (EUR/USD hardcoded) | AI |
| **Confidence floor للـ blocks (≥ 0.5)** | يمنع griefing الصامت | AI |
| **Daily reset للعدّادات** | يمنع false-trigger للـ kill-switches | Risk |
| **Per-pair per-session max trades cap** | يمنع stack 5 صفقات على EUR/USD في نافذة واحدة | Risk |
| **Notional-to-balance ratio cap (≤ 50:1)** | يمنع leverage مفرط من tight SL | Risk |
| **NY session re-verification في safety_rails** | طبقة ثانية، لا تعتمد على GateMind وحدها | Risk |
| **ATR centralisation في `_helpers.py`** | إنهاء الـ ٥ نسخ المستقلة | CodeQuality |
| **`tests/test_no_magic_numbers.py`** | كاشف drift دائم في CI | CodeQuality |
| **Structured logging على دخول/خروج كل brain** | post-mortem يصير ممكناً | CodeQuality |
| **إصلاح `consecutive_losses_limit` التضارب** | مصدر واحد للحقيقة | Risk + CodeQuality |
| **حذف monkey-patch من `runner.py:182`** | يستبدل بـ injected callable في constructor | Architect + Risk |

---

## ٧) أولويات التنفيذ (مرتّبة)

### المرحلة A — إصلاحات حرجة قبل أي backtest حقيقي (٢-٣ ساعات)
١. **إصلاح hardcoded EUR/USD في `openai_brain.py:162`** — تمرير pair الفعلي
٢. **حذف monkey-patch** من `backtest_v2/runner.py:182-194` — استبدال بـ `safety_rails_callable` في constructor
٣. **إصلاح تضارب `consecutive_losses_limit`** — `state_check.py:27` يجب أن يقرأ من `validation_config`
٤. **إضافة Daily reset** للعدّادات (`UTC midnight` + `NY 17:00`)
٥. **توحيد ATR في `engine/v3/_helpers.py`** — استبدال ٥ نسخ
٦. **إصلاح `permission_engine.py except: continue`** — re-raise + log

### المرحلة B — إصلاحات بنيوية (٣-٥ ساعات)
٧. **MarketMind يـ block على missing companion bars** (Architect A1)
٨. **Anthropic adapter كامل** مع `tool_choice` + `audit_hash` (AI1+AI2)
٩. **NY session re-verification في safety_rails** (R6)
١٠. **Per-pair per-session max-trades cap** (R3)
١١. **Notional-to-balance cap** في safety_rails (R4)
١٢. **`tests/test_no_magic_numbers.py`** + استخراج magic numbers (C2)

### المرحلة C — قبل الباكتيست النهائي (٢-٣ ساعات)
١٣. **إصلاح Sharpe formula** في `metrics.py:197` (Q4)
١٤. **إصلاح `pnl_pct` compounding** في `broker_replay.py:173` (Q3)
١٥. **Concentration test** كملف جديد `backtest_v2/concentration_test.py` (Q2)
١٦. **Cohen's kappa test** بين ChartMind و MarketMind (A2)
١٧. **Confidence floor للـ blocks** في LLM verdict (AI3)

### المرحلة D — الباكتيست الحقيقي (٤-٦ ساعات)
١٨. **Anchored walk-forward + embargo** على ٢٤ شهر EUR/USD + USD/JPY
١٩. **مقارنة strict vs loose** على نفس البيانات
٢٠. **Concentration test execution** (پاس فقط لو k≥10٪ من الأيام)
٢١. **Walk-forward 8 quarters** — قبول فقط لو ≥6/8 إيجابي

### المرحلة E — مراجعة ذاتية + تحسينات (مفتوحة)
٢٢. تقرير نتائج صريح
٢٣. كشف overfitting (DSR + concentration + WF)
٢٤. توصية: live أو reject

**المجموع:** ~١٥-٢٠ ساعة عمل هندسي قبل أي قرار live.

---

## ٨) خطة اختبار كل فكرة

| الفكرة | كيف نختبرها | معيار النجاح |
|---|---|---|
| MarketMind block on missing bars | Backtest مع/بدون XAU/SPX، قياس الفرق في accept rate | فرق واضح + accept rate أكثر صدقاً |
| Cohen's kappa | Backtest عام كامل، حساب kappa(chart_dir, market_dir) | k>0.7 = problem confirmed; k<0.4 = independence ok |
| Anchored walk-forward | 8 ربعيات، embargo ١ أسبوع | ≥6/8 ربعيات إيجابية للقبول |
| Concentration test | Sort days by abs(P&L)، إزالة top-1 → top-N، حساب PF | k≥10٪ من الأيام يجب أن تكسر edge → استراتيجية صحيحة |
| Sharpe fix | حساب باستخدام `sqrt(N_trades_year)` بدل `sqrt(252)` | الأرقام الصحيحة تُذكر في التقرير |
| pnl_pct compounding | إعادة حساب equity curve مع compounding | net% و per-trade% يتطابقان |
| Anthropic adapter | اختبار اتصال + اختبار schema enforcement (محاولة upgrade → rejected) | استدعاء واحد ناجح + 0 upgrade attempts pass |
| Daily reset | اختبار يحفظ daily_loss = 0.012، يتقدم اليوم، يتحقق من reset | عند 17:00 NY، الكل صفر |
| Notional cap | حالة باختبار 4-pip stop على $100k، 0.25% risk | تُرفض كـ "notional_cap_exceeded" |
| Magic numbers | AST walker على gatemind/v3/*.py | 0 violations بعد extraction |
| LLM hardcoded pair fix | Backtest على USD/JPY مرتين (قبل/بعد) | ≥10٪ من LLM verdicts تختلف |

---

## ٩) أخطر مخاطر Overfitting / Data Leakage

### Overfitting risks (مرتّبة بالخطورة)
١. **Iteration on aggregate WF score** — كل تعديل يحسّن WF Sharpe = meta-overfit. **علاج:** pre-register one canonical run؛ التعديلات اللاحقة تتطلب out-of-sample جديد.

٢. **Multi-trial selection bias** (DSR من López de Prado) — اختبار ١٠٠+ variant ثم اختيار الأفضل = ~30٪ احتمال قبول استراتيجية بـ edge=0. **علاج:** Deflated Sharpe Ratio.

٣. **Per-pair tuning** — ضبط ATR window أو session لكل زوج = overfitting لـ regime محدد. **علاج:** حظر per-pair tuning بسياسة.

٤. **Chart pattern parameters** — `permission_engine` thresholds مضبوطة على بيانات in-sample. **علاج:** استخدام نفس thresholds عبر الـ ٨ ربعيات.

### Data leakage risks
١. **Spread sourcing الحالي** يستخدم `bar_t.spread_pips` لقرار `bar_t+1.open` fill — **bias optimistic بـ ٠٫٣-٠٫٨ pip في NY 03:00/08:00**. (Quant)
٢. **Per-brain attribution** يحوي خطأ: NewsMind صامت دائماً → دقّته = WR. (Quant)
٣. **Companion bars filter `<= now`** — تمت مراجعته، **آمن**. (Quant)
٤. **State persistence** يحفظ بعد القرار، لكن يُقرأ قبل القرار التالي — **آمن** بنيوياً. (Risk)

---

## ١٠) خطة الباكتيست الحقيقية

### الإعدادات
- **الفترة:** 2024-01-01 إلى 2026-04-26 (28 شهر)
- **الأزواج:** EUR/USD + USD/JPY
- **Granularity:** M15
- **Mode:** strict (3-of-3 A/A+، B → block)
- **Risk:** 0.25% ثابت
- **Sessions:** NY فقط (3-5 + 8-12)
- **LLM:** mock (Anthropic disabled في الباكتيست لتقليل التكلفة، لكن بـ option للتفعيل في تشغيلة منفصلة)

### الـ runs (٤ تشغيلات منفصلة)
١. **Run 1 — Baseline strict mechanical:** kappa-based brain independence check
٢. **Run 2 — Strict + LLM-on:** ١٠٪ sample للتأكد من أن LLM يخفّض ٢-٥٪ من الـ enters
٣. **Run 3 — Loose comparison:** strict_mode=False (للتأكد أن strict أفضل)
٤. **Run 4 — Walk-forward 8 quarters:** anchored، embargo 1 week

### المقاييس
- Trade count (acc/rej) per pair
- WR / PF / Sharpe (corrected) / Max-DD / Calmar
- Net return (compounded)
- Per-brain accuracy (after fixing NewsMind constant-B bug)
- Per-window analysis (3-5 vs 8-12)
- Cohen's kappa (chart_dir, market_dir)
- Concentration index (top-5-day P&L share)
- DSR (Deflated Sharpe Ratio)

### القبول
- WF: ≥6/8 ربعيات إيجابية
- Concentration: top-5 days < 50٪ من P&L
- DSR: > 0
- Max-DD: < 15٪
- Min trades: 30 صفقة في كل ربع (Lopez de Prado)

أي معيار يفشل = الاستراتيجية مرفوضة.

---

## ١١) كيف سنثبت هدف صفقتين يومياً

**الإجابة الصريحة من المجلس:** **مستبعد إحصائياً مع القواعد الصارمة الحالية**.

### رياضيات Quant
- نوافذ NY: ٦ ساعات/يوم = ٢٤ شمعة M15/يوم
- معدّلات A/A+ المستقلة:
  - ChartMind A/A+: ١٥-٢٥٪
  - MarketMind A/A+: ٢٠-٣٠٪
  - NewsMind allow في النافذة: ~٨٥٪
- Joint independent: 0.20 × 0.25 × 0.85 = **٤٫٢٥٪**
- مع correlation عند trends: ٢-٦٪

→ **التوقّع: ٠٫٥-١٫٠ صفقة/يوم على الوسطي، ٣-٤ في الأيام الجيدة، ١٣٠-٢٥٠ صفقة/سنة.**

### "صفقتين يومياً" تتطلب:
- joint consensus rate ≥ ٨٪
- correlation between brains > 0.6 → **يقترح أن العقول ليست مستقلة فعلياً** (وهو ما اكتشفه Architect)

### قرار المجلس
- لا نُجبر النظام على ٢ صفقة/يوم. ذلك يخالف مواصفاتك صراحةً ("لا إجبار").
- نقيس فعلاً ونرى. إذا الباكتيست يعطي ١٫٥ صفقة/يوم في النوافذ النشطة، هذا ممتاز.
- إذا جاء ٠٫٢ صفقة/يوم → النظام بحاجة عقل رابع/خامس مستقل أو تخفيف منطقي للقواعد.

---

## ١٢) كيف سنثبت أو ننفي ١٥٠٪ بأرقام حقيقية

### الرياضيات الصريحة (Risk Agent)
عند r = ٠٫٢٥٪، WR = ٥٥٪، R:R = ٢:١:
- EV = +٠٫٦٥R/صفقة = +٠٫١٦٢٥٪/صفقة
- مطلوب: ln(2.5) / ln(1.001625) ≈ ٥٦٤ صفقة
- على ٢٥٠ يوم تداول = ٢٫٢٥ صفقة/يوم → ⚠️ غير واقعي إحصائياً

### التحدي الأساسي
- WR=٥٥٪ → P(٢ خسارة متتالية) = ٢٠٫٢٥٪
- consecutive_losses_limit = ٢ → kill-switch يطلق ~٣٠ مرة/سنة
- **الـ kill-switch يقتل الـ edge قبل الوصول لـ ١٥٠٪**

### الحلول الممكنة (مرتّبة بالأمان)
١. **رفع consecutive_losses_limit إلى ٣** (محسوب: P(3 losses)=9.1٪، أكثر منطقية لـ WR=٥٥٪) — يحتاج إثبات WF
٢. **رفع target R:R إلى ٢٫٥-٣** (يحتاج بنية سوق تسمح، اختبار في WF)
٣. **رفع r إلى ٠٫٣٧٥٪ بعد ٣ أسابيع نظيفة** — لا يكسر cap الـ ٠٫٥٪، يضيف ٥٠٪ tempo

### اختبار الإثبات/النفي
١. شغّل الباكتيست الكامل مع الإصلاحات
٢. احسب expectancy الفعلية بعد spread+slippage
٣. احسب عدد الصفقات الفعلية في ٢٤ شهر
٤. حدّ المركّب: `(1 + r×E)^N - 1`
٥. إذا الناتج ≥ ١٥٠٪ + DSR > 0 + Concentration > 10٪ + WF ≥ 6/8 = **مُثبَت**
٦. إذا أقل = **منفي بالأدلة**، نقدّم خطة بديلة

**القرار الصريح:** ١٥٠٪ ليست هدفاً مقدّساً. الهدف هو **edge موجب وثابت بأمان**. لو الأرقام الواقعية ٧٠٪/سنتين بـ DD<١٠٪ → نظام ممتاز ومُثبَت. ١٥٠٪ بـ DD>٣٠٪ = مرفوض.

---

## ١٣) أول ٣ تعديلات يجب تنفيذها (الإجماع)

### #١ — إصلاح hardcoded EUR/USD في Claude prompt
**الملف:** `llm/openai_brain.py:162` و `engine/v3/EngineV3.py:131-142`
**التغيير:** تمرير `pair=brain_outputs["pair"]` فعلياً في `_mind_outputs_to_dict`
**السبب:** كل verdict على USD/JPY حالياً مبني على prompt EUR/USD = هلوسة عن أداة مختلفة
**الاختبار:** Backtest USD/JPY مرتين، ≥١٠٪ من LLM verdicts تختلف
**الوقت:** ١٥ دقيقة

### #٢ — إصلاح Daily reset + consecutive_losses تضارب
**الملف:** `engine/v3/EngineV3.py` (إضافة `_daily_reset()`) و `gatemind/v3/state_check.py:27` (قراءة من validation_config)
**التغيير:**
- Daily reset عند UTC midnight + NY 17:00
- `state_check.py` يقرأ `cfg.consecutive_losses_limit` بدل `>= 3` صلب
**السبب:** Kill-switch يطلق false-trigger يومياً + تضارب ٢/٣ بين طبقتين
**الاختبار:** ٣ tests جديدة في `test_engine_state_persistence.py`
**الوقت:** ٤٥ دقيقة

### #٣ — حذف monkey-patch + إصلاح broker_env mismatch بشكل صحيح
**الملف:** `backtest_v2/runner.py:182-194` و `gatemind/v3/execution_check.py:14-18`
**التغيير:**
- Constructor `BacktestRunner` يستلم `safety_rails_callable=None` ويمرّره للـ Engine
- `execution_check.py` يقرأ `PAIR_STATUS` من `validation_config` (مصدر واحد)
- `validation_config.py` يضيف `practice` كـ alias لـ `paper`
**السبب:** أكبر تسريب process-wide في النظام + مصدران للحقيقة
**الاختبار:** test ينشئ backtest ثم live engine في نفس الـ process، يتحقّق أن live broker يرفض fake order
**الوقت:** ١ ساعة

---

## ١٤) معايير النجاح والفشل

### النجاح
✅ **الكود (هندسي):**
- ٠ hardcoded values في GateMind (test_no_magic_numbers يمر)
- ٠ silent except: continue (audit pass)
- ١ مصدر للـ ATR(14)
- structured logging على كل brain
- Daily reset يعمل (test يمر)
- Single source of truth لـ PAIR_STATUS
- LLM يستخدم pair الفعلي

✅ **الباكتيست (إحصائي):**
- ≥٦/٨ ربعيات إيجابية في walk-forward
- DSR > 0
- Concentration test: top-5 days < 50٪ P&L
- Max-DD < 15٪
- Cohen's kappa(chart, market) < 0.7 (إثبات استقلال نسبي)
- ≥٣٠ صفقة في كل ربع (Lopez de Prado threshold)

✅ **الأمان (Risk):**
- ٠ مسارات تسمح بـ live order أثناء backtest
- safety_rails ١٢ check يمر، بالإضافة لـ session re-verification
- Notional cap يعمل
- Per-pair per-session limit يطبّق

### الفشل
❌ أيّ من الآتي = الاستراتيجية مرفوضة:
- WF < ٦/٨ ربعيات إيجابية
- Concentration: top-5 days ≥ ٥٠٪ P&L (lottery curve)
- Max-DD ≥ ١٥٪
- DSR ≤ 0
- ≤ ٣٠ صفقة/ربع (insufficient sample)
- Cohen's kappa > 0.85 (overlap بنيوي ≠ ٣ من ٣)
- Walk-forward غير قابل للتكرار (data leakage)
- Live order أُرسِل أثناء backtest في أي اختبار (catastrophic)

---

## ١٥) القرار النهائي للفريق

### الإجماع
**HYDRA V3 نظام بنية صحيحة، تنفيذ نصف ناضج، توقعات أداء غير واقعية.**

### قرارات حازمة
١. **مواصفات GateMind صحيحة، يجب الالتزام بها بصرامة** (٣ من ٣ A/A+، أي B/missing/conflict = block).
٢. **لا تعديل في القواعد لتلبية ١٥٠٪/سنة** — إذا الواقع الإحصائي يقول ٧٠-١٠٠٪ بسلامة، فهذا الأفضل.
٣. **١٧ إصلاح حرج قبل أي backtest حقيقي** (في القسم ٧).
٤. **الباكتيست يجب أن يمر بـ ٤ معايير** (WF + concentration + DSR + sample size).
٥. **١٥٠٪ هدف نقيسه، لا نُجبر النظام لتحقيقه**.
٦. **رفض مطلق:** أي اقتراح يخفّف الصرامة لزيادة الصفقات.

### ترتيب التنفيذ
- **اليوم/جلسة قادمة:** ٣ إصلاحات حرجة (القسم ١٣)
- **ثم:** المرحلة A (٦ إصلاحات إضافية، ٢-٣ ساعات)
- **ثم:** المرحلة B (٦ إصلاحات بنيوية، ٣-٥ ساعات)
- **ثم:** المرحلة C (٥ تحسينات قبل الباكتيست، ٢-٣ ساعات)
- **ثم:** المرحلة D (الباكتيست الحقيقي، ٤-٦ ساعات)
- **ثم:** المرحلة E (المراجعة الذاتية النقدية)

**المجموع:** ١٥-٢٠ ساعة عمل قبل أي قرار live.

### كلمة أخيرة من المجلس
أنت لا تبني نظام تداول لتحقيق رقم. أنت تبني محرّك صادق يقول لك بالأرقام: هذا ما يستطيع. الفرق بين ٧٠٪ مثبتة و ١٥٠٪ متخيّلة هو الفرق بين رأس مال محفوظ وحساب مدمَّر.

**القرار:** نمضي. بترتيب. بأدلة. بدون مجاملة.

---

**آخر تحديث:** هذا التقرير كامل. أي تعديل لاحق يكون commit جديد بـ diff واضح.
