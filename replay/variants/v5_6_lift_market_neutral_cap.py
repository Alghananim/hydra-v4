"""V5.6 — lift the hidden cap-to-B when MarketMind is "neutral".

DISCOVERED IN AUDIT: F-017. `news_market_integration.integrate()` caps
ChartMind grade to B when MarketMind reports range/choppy and ChartMind
has a directional setup. This is INVISIBLE in the 8-flag evidence list
and is the prime suspect for ~60 % of the directional rejection mass.

Hypothesis: ChartMind already considers volatility and trend in its 8
evidence flags. Double-counting MarketMind's "neutral" verdict via this
hidden cap is over-conservative. Removing the cap should:
- Promote ~21 directional cycles from WAIT to ENTER (V5.0 had 33
  directional cycles → 12 ENTER; difference 21).
- Increase ENTER count substantially.
- Win-rate may decrease because some of those promoted cycles ARE
  questionable (market really WAS choppy). The shadow simulator says.

Risk: trades during choppy market regimes whip-saw and lose. The Red
Team must verify: (a) per-pair, (b) per-window, (c) drawdown floor.

Implementation: monkey-patch news_market_integration.integrate to skip
the neutral-vs-directional cap. Other caps (B/C grade, blocking,
opposing direction) stay intact.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_6_lift_market_neutral_cap"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import news_market_integration as nmi
    from contracts.brain_output import BrainGrade

    original_integrate = nmi.integrate

    def patched_integrate(news, market, chart_direction):
        result = original_integrate(news, market, chart_direction)
        # If the cap was added because of "market_neutral_vs_chart_*",
        # remove ONLY that cap. Other caps (B/C grade, opposing
        # direction, etc.) stay.
        cap_was_neutral_only = any(
            r.startswith("market_neutral_vs_chart_")
            for r in result.reason_bits
        )
        # Were there OTHER reasons that justify the cap?
        cap_other_reasons = any(
            (not r.startswith("market_neutral_vs_chart_"))
            and ("conflict" in r or "B" in r or "C" in r)
            for r in result.reason_bits
        )
        if cap_was_neutral_only and not cap_other_reasons:
            # Lift the cap. Reasons stay logged for transparency.
            return nmi.IntegrationContext(
                upstream_block=result.upstream_block,
                upstream_cap=None,  # lifted
                reason_bits=list(result.reason_bits) + ["v5_6_neutral_cap_lifted"],
                news_snapshot=result.news_snapshot,
                market_snapshot=result.market_snapshot,
                market_direction=result.market_direction,
            )
        return result

    nmi.integrate = patched_integrate

    def revert() -> None:
        nmi.integrate = original_integrate

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Removing the hidden upstream cap-to-B when MarketMind is "
            "neutral should promote ~21 directional cycles from WAIT to "
            "ENTER without adding new SETUP-level rejections."
        ),
        "expected_enter_direction": "strongly up (50%+ gain over V5.0)",
        "expected_winrate_direction": "down (we admit choppy-market trades)",
        "risk_if_wrong": (
            "Choppy-market trades whip-saw and lose. USD/JPY win rate "
            "could deteriorate further from 0/8."
        ),
        "promotion_criteria": [
            "ENTER count > 80 AND",
            "win rate (excl timeout) >= 25% AND",
            "Net pips > V5.0 baseline AND",
            "Per-pair USD/JPY net pips not below V5.0 by > 50 pips AND",
            "Red Team 8/8.",
        ],
        "rejection_triggers": [
            "Net pips worse than V5.0 by > 50 pips OR",
            "Win rate (excl timeout) < 20%.",
        ],
        "audit_finding": "F-017",
    }
