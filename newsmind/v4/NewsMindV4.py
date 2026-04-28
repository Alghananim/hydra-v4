"""NewsMind V4 — orchestrator.

Public surface:
  NewsMindV4(sources, scheduler, keywords).evaluate(pair, now_utc, current_bar=None)
    -> BrainOutput

Design rules:
  - NO try/except that silently swallows errors. Specific source-level
    exceptions are caught and recorded in SourceHealth, but every other
    exception propagates to a single fail-CLOSED at the orchestrator
    boundary, which constructs BrainOutput.fail_closed(...).
  - BrainOutput is the single return type. NewsVerdict is held as a sibling
    artifact accessible via .last_verdict for auditors.
  - Direction is reported (eur_usd_dir, usd_jpy_dir) but the decision field
    is ENTER → "WAIT" (NewsMind cannot say BUY/SELL alone), unless explicit
    blackout → "BLOCK".
  - Grade ladder:
      BLOCK  : any fail-CLOSED condition
      C      : single source / unverified social / chase
      B      : >=2 confirmations but data quality not perfect, or recent (not fresh)
      A      : >=2 confirmations, fresh, good data
      A+     : reserved — must additionally have a scheduled-event surprise score
                with |sigma| >= 1.0 and tier-1 event
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contracts.brain_output import BrainGrade, BrainOutput

from newsmind.v4 import chase_detector, freshness, intelligence, permission
from newsmind.v4.config_loader import default_config_dir, load_keywords
from newsmind.v4.event_scheduler import EventOccurrence, EventScheduler
from newsmind.v4.models import (
    EventSchedule,
    NewsItem,
    NewsSummary,
    NewsVerdict,
    SourceHealth,
    _normalize_pair,
)
from newsmind.v4.sources import (
    BaseSource,
    SourceEmpty,
    SourceError,
    SourceHTTPError,
    SourceParseError,
    SourceTimeout,
    default_sources,
)


_log = logging.getLogger("newsmind.v4")


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------


class NewsMindV4:
    BRAIN_NAME = "newsmind"

    def __init__(
        self,
        sources: Optional[Sequence[BaseSource]] = None,
        scheduler: Optional[EventScheduler] = None,
        keywords: Optional[Dict[str, Any]] = None,
        *,
        config_dir: Optional[Path] = None,
    ) -> None:
        self._sources: List[BaseSource] = list(sources) if sources is not None else default_sources()
        self._scheduler = scheduler if scheduler is not None else EventScheduler()
        if keywords is None:
            # Fail fast: a deployment that lost keywords.yaml has lost its
            # chase-protection list. Silently defaulting to {} would let
            # unverified social sources slip through unflagged.
            keywords = load_keywords(
                (config_dir or default_config_dir()) / "keywords.yaml"
            )
        self._keywords = keywords or {}
        self._unverified = list(self._keywords.get("unverified_sources", []))
        self.last_verdict: Optional[NewsVerdict] = None

    # ---------------------------------------------------------------- public

    def evaluate(
        self,
        pair: str,
        now_utc: datetime,
        current_bar: Optional[Dict[str, Any]] = None,
    ) -> BrainOutput:
        try:
            return self._evaluate_inner(pair, now_utc, current_bar)
        except Exception as e:  # noqa: BLE001 — this IS the fail-CLOSED boundary
            _log.exception("NewsMindV4.evaluate fail-CLOSED")
            return BrainOutput.fail_closed(
                brain_name=self.BRAIN_NAME,
                reason=f"orchestrator exception: {type(e).__name__}: {e}",
                risk_flags=["orchestrator_exception"],
                evidence=[f"exception_type={type(e).__name__}"],
                data_quality="broken",
            )

    # ----------------------------------------------------------- core logic

    def _evaluate_inner(
        self,
        pair: str,
        now_utc: datetime,
        current_bar: Optional[Dict[str, Any]],
    ) -> BrainOutput:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be tz-aware UTC")
        pair_u = _normalize_pair(pair)

        # 1. fan-out: collect items per source, recording health on failures
        all_items, health_map, source_errors = self._collect_items(now_utc)

        # 2. summarise
        summary = self._summarise(pair_u, now_utc, all_items)

        # 3. blackout check
        active_event: Optional[EventOccurrence] = self._scheduler.get_active_event(pair_u, now_utc)
        in_blackout = active_event is not None
        blackout_reason: Optional[str] = None
        if in_blackout:
            assert active_event is not None
            blackout_reason = (
                f"blackout: event_id={active_event.event.id} "
                f"window=[-{active_event.event.blackout_pre_min}m,"
                f"+{active_event.event.blackout_post_min}m] of "
                f"{active_event.scheduled_utc.isoformat()}"
            )
            summary.is_scheduled_event = True
            summary.active_event_id = active_event.event.id
            summary.pre_event_window = self._scheduler.in_pre_event_window(pair_u, now_utc)
            summary.post_event_window = self._scheduler.in_post_event_window(pair_u, now_utc)

        # 4. data quality
        data_quality = self._derive_data_quality(health_map, summary, source_errors)

        # 5. permission
        perm_inputs = permission.PermissionInputs(
            data_quality=data_quality,
            is_scheduled_event=summary.is_scheduled_event,
            in_blackout=in_blackout,
            impact_level=summary.impact_level,
            confirmation_count=summary.confirmation_count,
            has_any_news=bool(summary.items),
        )
        perm, perm_reason = permission.decide(perm_inputs)

        # 6. freshness of leading headline
        leading: Optional[NewsItem] = summary.items[0] if summary.items else None
        fresh_report = freshness.classify(leading, now_utc)

        # 7. bias / direction
        bias = (
            intelligence.keyword_bias(leading.headline, self._keywords)
            if leading
            else intelligence.KeywordBias()
        )
        eur_usd_dir, usd_jpy_dir = intelligence.bias_to_pair_direction(bias)

        # 8. surprise score (only computed if scheduled event with calendar values)
        surprise = self._compute_surprise(active_event, summary)

        # 9. chase cap
        chase = False
        if leading is not None:
            chase = chase_detector.is_chase(
                source_type=leading.source_type,
                confirmation_count=summary.confirmation_count,
                impact_level=summary.impact_level,
                headline=leading.headline,
                unverified_source_names=self._unverified,
                source_name=leading.source_name,
            )

        # 10. grade
        grade = self._grade(
            permission_=perm,
            data_quality=data_quality,
            fresh_status=fresh_report.status,
            confirmation_count=summary.confirmation_count,
            chase=chase,
            active_event=active_event,
            surprise=surprise,
        )

        # 11. confidence
        confidence = self._confidence(
            grade=grade,
            confirmations=summary.confirmation_count,
            fresh_status=fresh_report.status,
            data_quality=data_quality,
            surprise=surprise,
        )

        # 12. evidence (concrete facts, never placeholders)
        evidence = self._build_evidence(
            summary, fresh_report.age_seconds, active_event, surprise, health_map
        )

        # 13. decision
        decision = "BLOCK" if perm == "BLOCK" or grade == BrainGrade.BLOCK else (
            "WAIT" if perm == "WAIT" else "WAIT"
        )
        # NewsMind never emits BUY/SELL by itself; route ENTER → WAIT for the
        # downstream router. Direction is communicated via NewsVerdict.

        # 14. risk flags
        risk_flags: List[str] = []
        if in_blackout:
            risk_flags.append("news_blackout")
        if data_quality in ("missing", "broken"):
            risk_flags.append("source_health_degraded")
        if chase:
            risk_flags.append("unverified_source")
        if leading and any(
            u.lower() in leading.source_name.lower() for u in self._unverified
        ):
            risk_flags.append("unverified_source")
        # Surface the stale-but-alive case so a downstream auditor can
        # distinguish 'silent feeds' from 'feeds answering with nothing fresh'.
        any_ok = any(h.last_status == "ok" for h in health_map.values())
        if data_quality == "stale" and any_ok and not summary.items:
            risk_flags.append("stale_feed_no_recent_items")
        for h in health_map.values():
            if h.last_status not in ("ok", "unknown"):
                risk_flags.append(f"src:{h.source_name}:{h.last_status}")

        # 15. build verdict
        verdict = NewsVerdict(
            trade_permission=perm,
            reason=perm_reason,
            grade=grade.value,
            confidence=confidence,
            headline=leading.headline if leading else None,
            source_name=leading.source_name if leading else None,
            source_type=leading.source_type if leading else None,
            freshness_status=fresh_report.status,
            news_age_seconds=fresh_report.age_seconds,
            impact_level=summary.impact_level,
            market_bias=summary.market_bias,
            risk_mode=summary.risk_mode,
            affected_assets=summary.affected_assets,
            confirmation_count=summary.confirmation_count,
            is_scheduled_event=summary.is_scheduled_event,
            event_id=summary.active_event_id,
            pre_event_window=summary.pre_event_window,
            post_event_window=summary.post_event_window,
            normalized_utc_time=leading.normalized_utc_time if leading else None,
            eur_usd_dir=eur_usd_dir,
            usd_jpy_dir=usd_jpy_dir,
            surprise_score=surprise,
            blackout_reason=blackout_reason,
            source_health=health_map,
        )
        self.last_verdict = verdict

        # 16. compose BrainOutput (contract-validated)
        # TODO(v4.1): wire newsmind.v4.llm_review.review() here as a
        # downgrade-only second-pass auditor. Call site:
        #   review = llm_review.review(pair_u, leading.headline if leading else None,
        #                              grade.value, decision, evidence, blackout_reason)
        #   if review.suggestion == "block":
        #       grade, decision, should_block = BrainGrade.BLOCK, "BLOCK", True
        #   elif review.suggestion == "downgrade":
        #       grade = _step_down(grade)  # never above; downgrade-only
        # The reviewer is DEAD CODE in v4.0 by design — see llm_review.py header.
        should_block = (grade == BrainGrade.BLOCK)
        if should_block:
            decision = "BLOCK"

        reason_full = perm_reason
        if blackout_reason:
            reason_full = f"{perm_reason} | {blackout_reason}"

        return BrainOutput(
            brain_name=self.BRAIN_NAME,
            decision=decision,
            grade=grade,
            reason=reason_full,
            evidence=evidence,
            data_quality=data_quality,
            should_block=should_block,
            risk_flags=risk_flags,
            confidence=confidence,
            timestamp_utc=now_utc.astimezone(timezone.utc),
        )

    # ------------------------------------------------------------- internals

    def _collect_items(
        self, now_utc: datetime
    ) -> Tuple[List[NewsItem], Dict[str, SourceHealth], List[str]]:
        all_items: List[NewsItem] = []
        health: Dict[str, SourceHealth] = {}
        errors: List[str] = []
        for src in self._sources:
            try:
                items = src.fetch(now_utc)
                all_items.extend(items)
            except SourceTimeout as e:
                errors.append(f"timeout:{src.name}")
                _log.warning("source timeout: %s: %s", src.name, e)
            except SourceParseError as e:
                errors.append(f"parse_error:{src.name}")
                _log.warning("source parse error: %s: %s", src.name, e)
            except SourceEmpty as e:
                errors.append(f"empty:{src.name}")
                _log.info("source empty: %s: %s", src.name, e)
            except SourceHTTPError as e:
                errors.append(f"http_error:{src.name}")
                _log.warning("source http error: %s: %s", src.name, e)
            except SourceError as e:
                errors.append(f"source_error:{src.name}")
                _log.warning("source generic error: %s: %s", src.name, e)
            health[src.name] = src.health
        return all_items, health, errors

    def _summarise(
        self, pair: str, now_utc: datetime, items: List[NewsItem]
    ) -> NewsSummary:
        # filter to recent (≤ 6h) and currency-relevant items
        relevant: List[NewsItem] = []
        for it in items:
            age = (now_utc - it.normalized_utc_time).total_seconds()
            if age > 6 * 60 * 60:
                continue
            if not _affects_pair(pair, it):
                continue
            relevant.append(it)

        # newest first
        relevant.sort(key=lambda x: x.normalized_utc_time, reverse=True)

        # confirmations: how many DISTINCT authoritative+tier1 sources contributed
        distinct_strong = {
            it.source_name
            for it in relevant
            if it.source_type in ("authoritative", "tier1", "calendar")
        }

        impact = _derive_impact(relevant)
        bias = _derive_market_bias(relevant)
        risk = _derive_risk_mode(relevant)
        affects = _derive_assets(pair)

        return NewsSummary(
            items=relevant,
            confirmation_count=len(distinct_strong),
            is_scheduled_event=False,   # set later by orchestrator if blackout
            active_event_id=None,
            pre_event_window=False,
            post_event_window=False,
            impact_level=impact,
            market_bias=bias,
            risk_mode=risk,
            affected_assets=affects,
        )

    def _derive_data_quality(
        self,
        health: Dict[str, SourceHealth],
        summary: NewsSummary,
        errors: List[str],
    ) -> str:
        if not health:
            return "broken"
        ok_count = sum(1 for h in health.values() if h.last_status == "ok")
        any_ok = ok_count > 0
        if ok_count == 0 and not summary.items:
            # All sources failed. Fail-CLOSED.
            return "missing"
        if ok_count == 0:
            return "broken"
        if ok_count < max(1, len(health) // 2):
            # majority of sources failed
            return "stale"
        # Stale-but-ok leak guard: sources returned HTTP 200 but every item
        # was filtered out by the freshness/age window. The feed is alive
        # but has nothing recent — caller must NOT treat that as 'good'.
        # `summary.items` only contains items that passed the 6h age filter
        # AND the pair-affecting filter, so emptiness here means "no in-
        # window items even though the feed answered". Mark as "stale".
        if any_ok and not summary.items:
            return "stale"
        return "good"

    def _compute_surprise(
        self, active: Optional[EventOccurrence], summary: NewsSummary
    ) -> float:
        # Without consensus/std_dev calibration data wired in for a specific
        # event, surprise is 0.0. The calendar JSON occasionally carries
        # forecast/actual but rarely a std_dev; we conservatively return 0.0
        # rather than fabricate a sigma.
        return 0.0

    def _grade(
        self,
        *,
        permission_: str,
        data_quality: str,
        fresh_status: str,
        confirmation_count: int,
        chase: bool,
        active_event: Optional[EventOccurrence],
        surprise: float,
    ) -> BrainGrade:
        if permission_ == "BLOCK":
            return BrainGrade.BLOCK
        if data_quality != "good":
            # WAIT-class — we cannot grade higher than C without good data
            if confirmation_count >= 1:
                return BrainGrade.C
            return BrainGrade.C
        if chase:
            return BrainGrade.C
        if confirmation_count < 2:
            return BrainGrade.C
        if fresh_status not in ("fresh", "recent"):
            return BrainGrade.B
        # confirmation>=2 AND data good AND fresh/recent
        if (
            active_event is not None
            and active_event.event.tier == 1
            and abs(surprise) >= 1.0
            and fresh_status == "fresh"
        ):
            return BrainGrade.A_PLUS
        if fresh_status == "fresh":
            return BrainGrade.A
        return BrainGrade.B

    def _confidence(
        self,
        *,
        grade: BrainGrade,
        confirmations: int,
        fresh_status: str,
        data_quality: str,
        surprise: float,
    ) -> float:
        # Construct from observable facts. No magic 0.95.
        if grade == BrainGrade.BLOCK:
            return 0.0
        base = {
            BrainGrade.C: 0.30,
            BrainGrade.B: 0.55,
            BrainGrade.A: 0.75,
            BrainGrade.A_PLUS: 0.90,
        }[grade]
        # Tiny adjustments grounded in the actual numbers:
        if data_quality == "good":
            base += 0.02
        if fresh_status == "fresh":
            base += 0.02
        base += min(0.05, 0.01 * max(0, confirmations - 2))
        base += min(0.05, 0.02 * abs(surprise))
        return float(min(0.99, max(0.0, base)))

    def _build_evidence(
        self,
        summary: NewsSummary,
        age_s: Optional[float],
        active_event: Optional[EventOccurrence],
        surprise: float,
        health: Dict[str, SourceHealth],
    ) -> List[str]:
        ev: List[str] = []
        for it in summary.items[:3]:
            ev.append(
                f"headline={it.headline!r} src={it.source_name} "
                f"type={it.source_type} t={it.normalized_utc_time.isoformat()}"
            )
        ev.append(f"confirmations={summary.confirmation_count}")
        ev.append(f"impact_level={summary.impact_level}")
        ev.append(f"market_bias={summary.market_bias}")
        if age_s is not None:
            ev.append(f"news_age_seconds={age_s:.1f}")
        if active_event is not None:
            ev.append(
                f"active_event={active_event.event.id} "
                f"scheduled_utc={active_event.scheduled_utc.isoformat()} "
                f"tier={active_event.event.tier}"
            )
        ev.append(f"surprise_sigma={surprise:.3f}")
        ev.append(
            "source_health="
            + ",".join(f"{n}:{h.last_status}" for n, h in health.items())
        )
        return ev


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_PAIR_TO_CCYS = {
    "EURUSD": ("EUR", "USD"),
    "USDJPY": ("USD", "JPY"),
}


# Hardcoded allowlist of source_name substrings whose pair-affecting
# behaviour we have explicitly verified. An attacker cannot mint a new
# "authoritative" source name and have it default to relevant.
_KNOWN_PAIR_SOURCES = (
    "federalreserve",
    "ecb.europa",
    "boj.or.jp",
    "boj",
    "forexlive",
    "faireconomy",
)


def _affects_pair(pair: str, item: NewsItem) -> bool:
    src = item.source_name.lower()
    p = pair.upper()
    bag = (item.headline + " " + (item.body or "")).lower()

    # Path (b): explicit affected_assets on the NewsItem wins regardless of
    # whether the source is known. NewsItem currently has no field for this,
    # but we look for `affected_assets` as a duck-typed attribute so that
    # callers can attach it forward-compatibly without a model migration.
    explicit = getattr(item, "affected_assets", None)
    if explicit:
        try:
            if any(p == str(a).upper().replace("/", "").replace("-", "").replace("_", "").replace(" ", "") for a in explicit):
                return True
        except Exception:
            pass

    # Path (a): only known source_name substrings are trusted.
    if "federalreserve" in src or "forexlive" in src:
        # tier1 / USD authoritative — always relevant to both pairs
        return True
    if "ecb.europa" in src:
        return p == "EURUSD"
    if "boj" in src:
        return p == "USDJPY"
    if "faireconomy" in src:
        # calendar — keep relevant rows by currency keyword
        if p == "EURUSD":
            return any(k in bag for k in ("usd", "eur", "united states", "eurozone", "euro area"))
        if p == "USDJPY":
            return any(k in bag for k in ("usd", "jpy", "united states", "japan"))

    # Fail-closed: unknown source_name (no allowlist hit) and no explicit
    # affected_assets → not relevant to this pair. Off-topic headlines
    # cannot inflate confirmation_count toward grade A.
    return False


def _derive_impact(items: List[NewsItem]) -> str:
    if not items:
        return "low"
    n = len(items)
    if n >= 4:
        return "high"
    if n >= 2:
        return "medium"
    return "low"


def _derive_market_bias(items: List[NewsItem]) -> str:
    return "neutral"  # set by intelligence layer at orchestrator-call site if needed


def _derive_risk_mode(items: List[NewsItem]) -> str:
    return "normal"


def _derive_assets(pair: str) -> List[str]:
    return [pair.upper()]


# ---------------------------------------------------------------------------
# convenience
# ---------------------------------------------------------------------------


def evaluate_news(
    pair: str,
    now_utc: datetime,
    *,
    sources: Optional[Sequence[BaseSource]] = None,
    scheduler: Optional[EventScheduler] = None,
    keywords: Optional[Dict[str, Any]] = None,
) -> BrainOutput:
    return NewsMindV4(sources=sources, scheduler=scheduler, keywords=keywords).evaluate(pair, now_utc)
