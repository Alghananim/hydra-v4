"""HYDRA V5.2+ — variant registry.

Each variant is one isolated, single-concern modification of the V5.0
production system. Variants are applied via monkey-patch only inside the
variant runner (`replay/run_variant_backtest.py`); the production code
path is never altered at module-load time.

Each variant exports two callables:

  - apply()  -> Tuple[str, Callable[[], None]]
        Returns (label, revert). Applies the patch in-place, returns a
        function that undoes it. The runner calls revert() on exit.

  - describe() -> Dict[str, Any]
        Hypothesis, what changes, expected ENTER count direction
        (up / down / flat), risk if hypothesis wrong.

Naming:
  v5_2_drop_volatility_normal — drop one evidence flag
  v5_3_drop_no_liquidity_sweep — drop a different evidence flag
  v5_4_lower_a_min            — lower grade A threshold from 5 to 4
  v5_5_combined_4_and_5_2     — V5.4 + V5.2 stacked
  v6_per_pair_eur_lenient     — EUR/USD A=4, USD/JPY A=6 (per-pair)
  v7_require_mtf              — require mtf_aligned as hard gate
  v8_micro_risk_pct           — risk model tweak only
  v9_hardening                — defensive cleanup, no behaviour change
  v10_final                   — combined best variant after V5–V9

Each variant must, in addition to apply():
  - guarantee that gatemind/v4 unit tests pass (143/143)
  - guarantee that the orchestrator never reaches a different code path
    when its evidence flags are unchanged
  - never change the live execution path
"""
