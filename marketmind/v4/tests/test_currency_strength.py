"""Currency-strength tests: basket method + derived flag."""
from __future__ import annotations

from marketmind.v4 import currency_strength
from marketmind.v4.tests.conftest import make_trending_bars


def test_two_pairs_marks_jpy_derived():
    eur = make_trending_bars("up", n=40, start=1.10, step_pct=0.0010)        # EUR up vs USD
    jpy = make_trending_bars("down", n=40, start=150.0, step_pct=0.0010)     # USD down vs JPY
    out = currency_strength.compute({"EURUSD": eur, "USDJPY": jpy}, window=20)
    # USD has 2 pair-contributions, EUR has 1, JPY has 1 -> all under min_pairs_direct
    assert "EUR" in out
    assert "USD" in out
    assert "JPY" in out
    # All should be marked derived (default min_pairs_direct=3)
    for ccy in ("EUR", "USD", "JPY"):
        v = out[ccy]
        assert isinstance(v, str) and v.startswith("derived(")


def test_three_pairs_usd_direct():
    eur = make_trending_bars("up", n=40, start=1.10, step_pct=0.001)
    jpy = make_trending_bars("down", n=40, start=150.0, step_pct=0.001)
    gbp = make_trending_bars("up", n=40, start=1.25, step_pct=0.001)
    cad = make_trending_bars("down", n=40, start=1.35, step_pct=0.001)
    out = currency_strength.compute(
        {"EURUSD": eur, "USDJPY": jpy, "GBPUSD": gbp, "USDCAD": cad}, window=20
    )
    # USD appears in 4 pairs -> direct
    assert isinstance(out["USD"], (int, float)), out
    # EUR appears in only 1 pair -> derived
    assert isinstance(out["EUR"], str) and out["EUR"].startswith("derived(")


def test_strength_sign_for_clearly_strong_usd():
    # USD strong: EUR/USD down, USD/JPY up, GBP/USD down, USD/CAD up
    eur = make_trending_bars("down", n=40, start=1.10, step_pct=0.001)
    jpy = make_trending_bars("up", n=40, start=150.0, step_pct=0.001)
    gbp = make_trending_bars("down", n=40, start=1.25, step_pct=0.001)
    cad = make_trending_bars("up", n=40, start=1.35, step_pct=0.001)
    out = currency_strength.compute(
        {"EURUSD": eur, "USDJPY": jpy, "GBPUSD": gbp, "USDCAD": cad}, window=20
    )
    assert isinstance(out["USD"], (int, float))
    assert out["USD"] > 0, out


def test_strength_zero_when_no_movement():
    flat = make_trending_bars("up", n=40, start=1.10, step_pct=0.0)
    out = currency_strength.compute({"EURUSD": flat}, window=20)
    eur_v = currency_strength.numeric_value(out.get("EUR", 0.0))
    usd_v = currency_strength.numeric_value(out.get("USD", 0.0))
    assert abs(eur_v) < 1e-6
    assert abs(usd_v) < 1e-6


def test_numeric_value_helper():
    assert currency_strength.numeric_value(0.42) == 0.42
    assert currency_strength.numeric_value("derived(0.5)") == 0.5
    assert currency_strength.numeric_value("garbage") == 0.0


def test_invalid_pair_skipped():
    out = currency_strength.compute({"NOTAPAIR": [], "EURUSD": []}, window=20)
    # Empty bars -> contributions skipped; returns {}
    assert out == {}
