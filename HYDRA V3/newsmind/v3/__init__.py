"""NewsMind v2 — structured news intelligence with safety-first defaults."""
from .models import NewsItem, EventSchedule, NewsVerdict, TradePermission, FreshnessStatus, ImpactLevel, SourceType
from .freshness import FreshnessAnalyzer
from .chase_detector import ChaseDetector, ChaseAssessment
from .event_scheduler import EventScheduler, CURRENCY_TO_PAIRS, EVENT_META
from .sources import (NewsSource, SourceAggregator, default_sources,
                      ReutersWireSource, BloombergWireSource,
                      ForexliveSource, InvestingCalendarSource,
                      TwitterOfficialSource)
from .permission import PermissionEngine
from .intelligence import IntelligenceLayer, ImpactAssessment
from .NewsMindV3 import NewsMindV3

__all__ = [
    "NewsItem", "EventSchedule", "NewsVerdict",
    "TradePermission", "FreshnessStatus", "ImpactLevel", "SourceType",
    "FreshnessAnalyzer", "ChaseDetector", "ChaseAssessment",
    "EventScheduler", "CURRENCY_TO_PAIRS", "EVENT_META",
    "NewsSource", "SourceAggregator", "default_sources",
    "ReutersWireSource", "BloombergWireSource", "ForexliveSource",
    "InvestingCalendarSource", "TwitterOfficialSource",
    "PermissionEngine", "NewsMindV3",
    "IntelligenceLayer", "ImpactAssessment",
]
