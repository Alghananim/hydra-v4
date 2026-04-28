"""HYDRA V4 — Orchestrator error hierarchy.

Errors here are raised at the *orchestrator boundary* — i.e., for
problems that are NOT a brain's responsibility (missing inputs, bad
arguments, etc.). A brain's own fail-CLOSED BLOCK BrainOutput is NEVER
turned into an exception by the orchestrator; it's propagated as data
and recorded in SmartNoteBook.
"""

from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for orchestrator-only failures."""


class MissingBrainOutputError(OrchestratorError):
    """A brain returned None or a non-BrainOutput object.

    NEVER raised because a brain returned a BLOCK BrainOutput — that's a
    valid output and is propagated as data, not as an exception.
    """


class BarFeedError(OrchestratorError):
    """The bar feed inputs are missing / malformed at the orchestrator
    boundary (before any brain has been called). e.g. naive datetime,
    empty symbol, bars_by_pair is None.
    """
