"""HYDRA V4 — Orchestrator package.

Wires the 5 frozen brains (NewsMind, MarketMind, ChartMind, GateMind,
SmartNoteBook) into a single decision cycle. The orchestrator owns:

  * cycle_id minting
  * per-brain timing measurements
  * SmartNoteBook recording (DECISION_CYCLE + GATE_AUDIT)
  * final DecisionCycleResult assembly

The orchestrator NEVER:
  * overrides a brain's decision
  * sends live orders or imports a broker SDK
  * swallows brain fail-CLOSED outputs
"""

from orchestrator.v4.cycle_id import mint_cycle_id
from orchestrator.v4.decision_cycle_record import DecisionCycleResult
from orchestrator.v4.HydraOrchestratorV4 import HydraOrchestratorV4
from orchestrator.v4.orchestrator_errors import (
    BarFeedError,
    MissingBrainOutputError,
    OrchestratorError,
)

__all__ = [
    "HydraOrchestratorV4",
    "DecisionCycleResult",
    "mint_cycle_id",
    "OrchestratorError",
    "MissingBrainOutputError",
    "BarFeedError",
]
