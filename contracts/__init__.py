"""HYDRA V4 shared contracts.

Every brain (NewsMind, MarketMind, ChartMind, GateMind) MUST emit a
`BrainOutput` defined here. Invariants are enforced in __post_init__.
"""

from contracts.brain_output import BrainGrade, BrainOutput

__all__ = ["BrainGrade", "BrainOutput"]
