# backtest_v2 — هرنس احترافي حول EngineV3

`backtest_v2/` هو **هرنس** (harness) فقط، وليس محرّكًا موازيًا.
كل قرار تداول يُتَّخَذ عبر `EngineV3.decide_and_maybe_trade()` نفسها
التي تُستخدم في الإنتاج. لا يوجد منطق قرارات مكرّر.

## الميزات الأساسية

* قياس: عدد الصفقات (الكلّي/المقبول/المرفوض)، نسبة الربح،
  P&L، أقصى Drawdown، Profit Factor، أداء كل زوج، دقّة كل عقل،
  دقّة GateMind، مقارنة قبل/بعد بين strict و loose.
* **منع تسرّب البيانات المستقبلية** هيكليًا عبر `LeakSafeBars`.
* **تكاليف واقعية** عبر `Backtest/costs.py` (Spread + Slippage).
* **عزل تام**: كل سجلّات Backtest تُوسَم بـ `system_mode='backtest'`،
  فلا تختلط أبدًا مع بيانات `paper` أو `live`.
* `strict_mode=True` افتراضيًا، مع علم `strict_mode=False` للمقارنات.

## كيفية التشغيل

### 1) اختبار سريع (Fixtures فقط)

```bash
cd /path/to/hydra-v3
python -m pytest backtest_v2/tests/ -v
```

### 2) Backtest على بيانات OANDA الحقيقية

تتطلّب وجود متغيّرَي البيئة:

```bash
export OANDA_API_TOKEN=...
export OANDA_ACCOUNT_ID=...
export OANDA_ENV=practice
```

ثم شَغّل:

```python
from datetime import datetime, timezone
from backtest_v2 import BacktestConfig, BacktestRunner

cfg = BacktestConfig(
    pair="EUR/USD",
    start_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_utc=datetime(2024, 6, 30, tzinfo=timezone.utc),
    initial_balance=10_000.0,
    risk_pct_per_trade=0.0025,    # 0.25%
    strict_mode=True,
)
runner = BacktestRunner.from_config(cfg)
outcome = runner.run()
print(outcome.report.to_json())
```

### 3) مقارنة strict vs loose

```python
from backtest_v2 import BacktestConfig, BacktestRunner
from backtest_v2.reporter import diff_text

base = BacktestConfig(pair="EUR/USD", strict_mode=False, label="loose")
strict = BacktestConfig(pair="EUR/USD", strict_mode=True,  label="strict")

r1 = BacktestRunner.from_config(base).run()
r2 = BacktestRunner.from_config(strict).run()

print(diff_text(r1.report, r2.report))
```

## مخطّط المجلّد

```
backtest_v2/
├── config.py                 # BacktestConfig dataclass
├── data_provider.py          # OANDA bar loader (يعيد استخدام Backtest/data.py)
├── calendar_provider.py      # محوّل HistoricalCalendar -> NewsVerdict
├── cross_asset_provider.py   # DXY/SPX/Gold (synthetic_dxy fallback)
├── replay_clock.py           # ساعة استعادة بار-بار
├── account_simulator.py      # حساب Paper: رصيد، صفقات مفتوحة، MTM
├── broker_replay.py          # Broker وهمي: تنفيذ على Open للبار التالي
├── leak_detector.py          # حماية هيكلية ضدّ Lookahead bias
├── metrics.py                # WR, PF, DD, Sharpe, per-pair, per-brain
├── per_brain_attribution.py  # دقّة كل عقل لكلّ صفقة مغلقة
├── reporter.py               # جدول مقارنة strict vs loose
├── runner.py                 # الحلقة الرئيسية
├── fixtures/                 # OHLC وأخبار اصطناعية للاختبارات
└── tests/                    # 6 ملفّات اختبار، كلّها يجب أن تنجح
```

## ضمانات الجودة

كل اختبار في `tests/` يُغلق ثغرة:

| الاختبار                          | يضمن أنّ                                              |
|------------------------------------|--------------------------------------------------------|
| test_no_lookahead.py               | Engine لا يرى أيّ بار > cursor                         |
| test_engine_parity.py              | Backtest يستخدم نفس صنف EngineV3 الإنتاجي              |
| test_metrics_correctness.py        | WR/PF/Net تُحسَب بدقّة على fixture يدويّ                |
| test_strict_blocks_b_grades.py     | strict_mode يَرفُض كلّ ChartMind بدرجة B                |
| test_account_persistence.py        | الرصيد والصفقات تستمرّ صحيحة بين البارات                |
| test_no_mode_pollution.py          | كلّ سجلّ في الـSmartNoteBook موسوم backtest             |

أيّ تسرّب بيانات مستقبلية = فشل اختبار تلقائي. هذه القاعدة لا تُكسَر.
