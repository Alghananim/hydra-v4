"""MarketMind V4 — rule-based market regime brain.

Public surface:
    MarketMindV4(...).evaluate(pair, bars_by_pair, now_utc, news_output=None) -> MarketState

Design rules (Phase 1 protocol):
  - NO indicator without test
  - NO regime without proof
  - NO score without explanation
  - NO V3 code without verification
  - NO A/A+ without evidence
  - Rule-based ONLY (no Claude in MarketMind itself)
  - Every state field comes from a NAMED, DOCUMENTED rule
  - Fail-CLOSED on missing data
  - NewsMind risk MUST be respected (downgrade or BLOCK)
"""

from marketmind.v4.models import Bar, MarketState
from marketmind.v4.MarketMindV4 import MarketMindV4

__all__ = ["MarketMindV4", "MarketState", "Bar"]
