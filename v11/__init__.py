"""HYDRA V11 — multi-pair, multi-timeframe redesign.

V11 keeps every V5 invariant (V4.7 consensus, 16-condition guard,
SmartNoteBook chain, no-lookahead) and adds:

  - M5 timeframe (3x more bars than M15).
  - 6 instruments (3x more pairs).
  - 4 trading windows (~10h/day vs V5's 6h).
  - Per-pair SL/TP scaling.
  - Real M5 entry + M15 trend + H1 bias multi-timeframe pipeline.
  - 3 new setup detectors (inside-bar, range-break, mean-reversion).

Modules:
  pairs           : per-pair calibration table (ATR, spread, SL/TP).
  windows         : 4-window NY/London/Asian schedule.
  m5_data_fetch   : OANDA M5 cache builder.
  setups          : new ChartMind setup detectors.
  v11_orchestrator: V11 wrapper that wires the above into V5's brains.
"""
