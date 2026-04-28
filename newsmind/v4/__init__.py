"""NewsMind V4 — clean rebuild.

Public surface:
  NewsMindV4   — the orchestrator class
  NewsItem     — single news headline (raw)
  NewsVerdict  — full verdict (extra fields beyond BrainOutput)
  evaluate_news — convenience function
"""

from newsmind.v4.models import (
    EventSchedule,
    NewsItem,
    NewsSummary,
    NewsVerdict,
)
from newsmind.v4.NewsMindV4 import NewsMindV4, evaluate_news

__all__ = [
    "NewsMindV4",
    "NewsItem",
    "NewsVerdict",
    "EventSchedule",
    "NewsSummary",
    "evaluate_news",
]
