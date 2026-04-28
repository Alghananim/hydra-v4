"""ChartMind V4 — chart-pattern brain.

Public surface:
    from chartmind.v4.ChartMindV4 import ChartMindV4
    from chartmind.v4.models import ChartAssessment

Locked constants live in `chart_thresholds` (NEVER hardcode floats in
business logic). Indicators are imported from `marketmind.v4.indicators`
(SHARED — no duplication).

NOTE: We intentionally do NOT eagerly import ChartMindV4/ChartAssessment at
package init to avoid a circular import — ChartMindV4.py does
``from chartmind.v4 import breakout_detector, ...`` which would re-enter
this module before its top-level statements finished executing.
"""
def __getattr__(name):
    # Lazy attribute access: `chartmind.v4.ChartMindV4` and
    # `chartmind.v4.ChartAssessment` resolve on first use.
    if name == "ChartMindV4":
        from chartmind.v4.ChartMindV4 import ChartMindV4 as _C
        return _C
    if name == "ChartAssessment":
        from chartmind.v4.models import ChartAssessment as _C
        return _C
    raise AttributeError(f"module 'chartmind.v4' has no attribute {name!r}")
