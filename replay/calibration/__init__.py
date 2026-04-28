"""HYDRA V4.8 calibration toolkit.

Activated only after V4.7 War Room results show that the strict A/A+ rule
under-trades. This package isolates the parameter-sweep machinery from
the production gate so that:

  1. The frozen orchestrator stays untouched (live trading code path
     never mutates during a sweep).
  2. Each variant is a deterministic recipe applied at orchestrator
     instantiation only — never live.
  3. Every variant runs the SAME unit tests + Red Team probes that V4.7
     passed.

Modules:
  parameters    : registry of tunable knobs and their safe ranges
  sweep         : one-parameter-at-a-time backtest harness
  compare       : per-variant trade count, win rate, drawdown, Red Team
"""
