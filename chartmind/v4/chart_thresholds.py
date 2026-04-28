"""ChartMind V4 — locked thresholds. NO magic floats anywhere else.

These names are the API: business logic must reference them by name. Tuning
must be done HERE so it shows up in code review and is traceable. Phase 1
audit lists these as 'do not tune' — see module docstring of ChartMindV4.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Indicator periods (mirror marketmind.v4.indicators — re-exported for clarity)
# ---------------------------------------------------------------------------
ATR_PERIOD = 14            # Wilder's ATR
ADX_PERIOD = 14            # Wilder's ADX
EMA_PERIOD = 20            # close-EMA used by trend slope test


# ---------------------------------------------------------------------------
# RULE 1 — Trend structure (M15)
# ---------------------------------------------------------------------------
TREND_LOOKBACK_BARS = 40         # 40 M15 bars ≈ 10 hours
TREND_HH_HL_MIN_STRONG = 3       # need >=3 HH AND >=3 HL to call _strong
TREND_SLOPE_BARS = 10            # EMA-20 slope must be > 0 over last 10 bars
TREND_RANGE_HHLL_MAX = 1         # range = HH+LL <= 1 each
TREND_RANGE_ADX_MAX = 18.0
TREND_CHOPPY_FLIPS_MIN = 4       # >=4 direction flips in last 10 bars


# ---------------------------------------------------------------------------
# RULE 2 — Key levels
# ---------------------------------------------------------------------------
SWING_K = 3                      # adaptive k=3 fractal on M15 closes
LEVEL_LOOKBACK_BARS = 80         # cluster pivots from last 80 bars
CLUSTER_TOL_ATR = 0.3            # cluster tolerance = 0.3 × ATR
LEVEL_STRENGTH_WEAK = 1
LEVEL_STRENGTH_MEDIUM = 2
LEVEL_STRENGTH_STRONG = 3        # 3+ touches


# ---------------------------------------------------------------------------
# RULE 3 — Real breakout (Wyckoff body-close)
# ---------------------------------------------------------------------------
BREAKOUT_CONFIRM_ATR = 0.3       # body close must exceed level by 0.3 × ATR
BREAKOUT_BODY_RATIO_MIN = 0.5    # body/range >= 0.5
BREAKOUT_CLOSE_LOC_MIN = 0.7     # close in upper 30% (i.e. position >= 0.7) for long


# ---------------------------------------------------------------------------
# RULE 4 — Fake breakout
# ---------------------------------------------------------------------------
FAKE_BREAKOUT_LOOKAHEAD = 3      # any of next 3 bars closing back inside


# ---------------------------------------------------------------------------
# RULE 5 — Successful retest
# ---------------------------------------------------------------------------
RETEST_WINDOW_MIN_BARS = 3
RETEST_WINDOW_MAX_BARS = 10
RETEST_TOL_ATR = 0.5             # touch within ± 0.5 × ATR of level
RETEST_REJECTION_WICK_MIN = 0.4  # rejection wick / range >= 0.4


# ---------------------------------------------------------------------------
# RULE 6 — Pullback in trend
# ---------------------------------------------------------------------------
PULLBACK_DEPTH_MIN_ATR = 0.5
PULLBACK_DEPTH_MAX_ATR = 1.5


# ---------------------------------------------------------------------------
# RULE 7 — Entry zone width (bands derived from ATR)
# ---------------------------------------------------------------------------
ENTRY_BAND_BREAKOUT_ATR = 0.2    # ± 0.2 × ATR around last close
ENTRY_BAND_RETEST_ATR = 0.3      # ± 0.3 × ATR around level
ENTRY_BAND_PULLBACK_ATR = 0.3    # ± 0.3 × ATR around recent swing


# ---------------------------------------------------------------------------
# Candle in-context filter
# ---------------------------------------------------------------------------
CANDLE_IN_CONTEXT_ATR = 1.0      # only count candles within 1.0 × ATR of a level

# Single-bar Nison candle anatomy thresholds (hammer / shooting star)
CANDLE_HAMMER_BODY_MAX = 0.4     # body / range <= 0.4 to qualify as hammer/star
CANDLE_WICK_MIN = 0.5            # rejection wick / range >= 0.5
CANDLE_BODY_TOP_MAX = 0.2        # opposite (non-rejection) wick / range <= 0.2


# ---------------------------------------------------------------------------
# Liquidity sweep — wick anatomy on the sweep bar
# ---------------------------------------------------------------------------
LIQUIDITY_SWEEP_WICK_MIN = 0.5   # sweeping wick / range >= 0.5


# ---------------------------------------------------------------------------
# References — invalidation fallback (no swing yet)
# ---------------------------------------------------------------------------
INVALIDATION_FALLBACK_ATR_MULT = 2.0   # invalidation = anchor ± 2.0 × ATR fallback


# ---------------------------------------------------------------------------
# RULE 8 — Additive evidence ladder for grade
# ---------------------------------------------------------------------------
GRADE_A_PLUS_MIN_EVIDENCE = 6    # of 8
GRADE_A_MIN_EVIDENCE = 5
GRADE_B_MIN_EVIDENCE = 3
# C = 1..2; BLOCK = 0 OR data bad OR upstream block

EVIDENCE_KEYS = (
    "strong_trend",
    "key_level_confluence",
    "real_breakout",
    "successful_retest",
    "in_context_candle",
    "mtf_aligned",
    "volatility_normal",
    "no_liquidity_sweep",
)


# ---------------------------------------------------------------------------
# Volatility envelope (mirrors MarketMind percentile thresholds for parity)
# ---------------------------------------------------------------------------
VOL_COMPRESSED_PCT_MAX = 25.0    # ATR percentile <=25 -> compressed
VOL_EXPANDED_PCT_MIN = 80.0      # ATR percentile >=80 -> expanded
VOL_DANGEROUS_PCT_MIN = 95.0     # ATR percentile >=95 -> dangerous


# ---------------------------------------------------------------------------
# Data quality minimums
# ---------------------------------------------------------------------------
MIN_BARS_FOR_EVALUATION = 30     # less than this = data missing
MAX_STALE_MINUTES = 60           # last bar age vs now > 60 min = stale
MIN_BARS_FOR_FRACTAL = 2 * SWING_K + 1
