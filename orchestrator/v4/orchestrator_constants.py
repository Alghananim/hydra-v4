"""HYDRA V4 — Orchestrator constants (no magic numbers anywhere else).

Every named string / number used by the orchestrator lives here. Tests
import these constants instead of hardcoding so a rename here is caught
at lint-time rather than runtime.
"""

from __future__ import annotations

from typing import FrozenSet

# ---------------------------------------------------------------------------
# Final status — what the orchestrator publishes downstream
# ---------------------------------------------------------------------------
FINAL_ENTER_CANDIDATE: str = "ENTER_CANDIDATE"
FINAL_WAIT: str = "WAIT"
FINAL_BLOCK: str = "BLOCK"
FINAL_ORCHESTRATOR_ERROR: str = "ORCHESTRATOR_ERROR"

VALID_FINAL_STATUSES: FrozenSet[str] = frozenset({
    FINAL_ENTER_CANDIDATE,
    FINAL_WAIT,
    FINAL_BLOCK,
    FINAL_ORCHESTRATOR_ERROR,
})

# ---------------------------------------------------------------------------
# Brain identities (per Phase 1 verified APIs)
# ---------------------------------------------------------------------------
BRAIN_KEY_NEWS = "newsmind"
BRAIN_KEY_MARKET = "marketmind"
BRAIN_KEY_CHART = "chartmind"
BRAIN_KEY_GATE = "gatemind"
BRAIN_KEY_NOTEBOOK = "smartnotebook"

# ---------------------------------------------------------------------------
# Default symbol — V4 trades EUR_USD only (USD_JPY is on the roadmap, see
# scalability test). Always pass an explicit symbol; this is the safety net.
# ---------------------------------------------------------------------------
DEFAULT_SYMBOL: str = "EUR_USD"

# ---------------------------------------------------------------------------
# Timing labels (timings_ms keys)
# ---------------------------------------------------------------------------
T_NEWS = "news_ms"
T_MARKET = "market_ms"
T_CHART = "chart_ms"
T_GATE = "gate_ms"
T_NOTEBOOK = "notebook_ms"
T_TOTAL = "total_ms"

# ---------------------------------------------------------------------------
# Cycle ID
# ---------------------------------------------------------------------------
CYCLE_ID_PREFIX: str = "hyd"      # "hydra"
CYCLE_TS_FORMAT: str = "%Y%m%dT%H%M%S%fZ"

# ---------------------------------------------------------------------------
# Forbidden imports — used by adversarial test (test_no_live_order)
# ---------------------------------------------------------------------------
FORBIDDEN_IMPORTS: FrozenSet[str] = frozenset({
    "oanda",
    "oandapyV20",
    "requests",
    "urllib",
    "urllib3",
    "httpx",
    "socket",
    "http.client",
    "anthropic",
    "openai",
})

# ---------------------------------------------------------------------------
# Default GateMind session_status fallback when GateMind couldn't compute
# ---------------------------------------------------------------------------
SESSION_STATUS_UNKNOWN: str = "session_unknown"

# ---------------------------------------------------------------------------
# Numeric constants — replaces magic literals scattered through the orchestrator
# ---------------------------------------------------------------------------
MS_PER_SECOND: float = 1000.0
"""Multiplier turning seconds (perf_counter delta) into milliseconds."""

EVIDENCE_PER_BRAIN_LIMIT: int = 3
"""Max evidence strings collected from each BrainOutput when assembling
the DECISION_CYCLE evidence_summary. Caps log size."""

CLOCK_DRIFT_TOLERANCE_MINUTES: int = 5
"""Allowed wall-clock drift between caller's now_utc and the orchestrator
host's clock. Bigger gaps reject the cycle as a Bar-Feed error (Red Team A5).
"""

# ---------------------------------------------------------------------------
# Markers used by SmartNoteBook ledger to surface ORCHESTRATOR_ERROR
# despite the ledger only accepting {ENTER_CANDIDATE, WAIT, BLOCK}.
# Auditors querying for ORCHESTRATOR_ERROR can grep blocking_reason for
# this prefix. (Fix O3 — ledger/DCR divergence.)
# ---------------------------------------------------------------------------
ORCHESTRATOR_ERROR_PREFIX: str = "orchestrator_error:"
SMARTNOTEBOOK_RECORD_FAILURE_PREFIX: str = "smartnotebook_record_failure:"
