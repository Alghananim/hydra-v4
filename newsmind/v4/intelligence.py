"""NewsMind V4 — intelligence layer.

REBUILT (per audit). Two responsibilities:

  1. surprise_score(actual, consensus, std_dev) — sigma units
     and pip_impact(event, surprise_score, pair) — using events.yaml pip_per_sigma.

  2. keyword_bias(headline, keywords_yaml) — maps a headline to a per-currency
     hawkish/dovish/risk_off/risk_on bias, then projects onto pair direction.

V3 mistake we don't repeat: V3 ignored the calibration in events.yaml and
hardcoded a flat "high impact = 50 pips" for every event. V4 uses per-event
pip_per_sigma.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from newsmind.v4.models import EventSchedule


# ---------------------------------------------------------------------------
# surprise score
# ---------------------------------------------------------------------------


def surprise_score(
    actual: Optional[float],
    consensus: Optional[float],
    std_dev: Optional[float],
) -> float:
    """Return surprise in sigma units. Positive = upside surprise.

    If any input is None or std_dev is non-positive, returns 0.0 — meaning
    "we cannot quantify surprise; treat as neutral".
    """
    if actual is None or consensus is None or std_dev is None:
        return 0.0
    if std_dev <= 0:
        return 0.0
    return float((actual - consensus) / std_dev)


def pip_impact(event: EventSchedule, sigma: float, pair: str) -> float:
    """Estimated pip move on `pair` for a `sigma`-σ surprise of `event`.

    Sign: positive sigma on a USD-currency event means USD strength, which
    is `+` for USDJPY and `-` for EURUSD. We let the caller resolve sign
    using the pair-vs-currency relationship; this function just gives the
    magnitude × signed sigma scalar.
    """
    pair_u = pair.upper()
    if pair_u not in event.pip_per_sigma:
        return 0.0
    return sigma * event.pip_per_sigma[pair_u]


def signed_pip_impact(event: EventSchedule, sigma: float, pair: str) -> float:
    """As `pip_impact` but with the sign aligned to pair direction.

    Convention used:
      - "positive sigma" → currency-of-event is STRONGER
      - For pair "EURUSD": EUR is base, USD is quote. USD-stronger surprise
        → EURUSD goes DOWN → negative pip move.
      - For pair "USDJPY": USD is base. USD-stronger surprise → USDJPY UP.
    """
    mag = pip_impact(event, abs(sigma), pair)
    direction = 1 if sigma >= 0 else -1
    pair_u = pair.upper()
    cur = event.currency.upper()
    if pair_u == "EURUSD":
        if cur == "USD":
            return -mag * direction
        if cur == "EUR":
            return +mag * direction
    if pair_u == "USDJPY":
        if cur == "USD":
            return +mag * direction
        if cur == "JPY":
            return -mag * direction
    return 0.0


# ---------------------------------------------------------------------------
# keyword bias
# ---------------------------------------------------------------------------


@dataclass
class KeywordBias:
    usd: str = "neutral"   # "hawkish" | "dovish" | "neutral"
    eur: str = "neutral"
    jpy: str = "neutral"
    risk: str = "neutral"  # "risk_off" | "risk_on" | "neutral"

    def is_neutral(self) -> bool:
        return (
            self.usd == "neutral"
            and self.eur == "neutral"
            and self.jpy == "neutral"
            and self.risk == "neutral"
        )


def _match(headline: str, phrases: List[str]) -> bool:
    h = (headline or "").lower()
    return any(p.lower() in h for p in (phrases or []))


def keyword_bias(headline: str, keywords: Dict[str, Any]) -> KeywordBias:
    """Run a headline against keywords.yaml maps."""
    out = KeywordBias()
    if "usd" in keywords:
        if _match(headline, keywords["usd"].get("hawkish", [])):
            out.usd = "hawkish"
        elif _match(headline, keywords["usd"].get("dovish", [])):
            out.usd = "dovish"
    if "eur" in keywords:
        if _match(headline, keywords["eur"].get("hawkish", [])):
            out.eur = "hawkish"
        elif _match(headline, keywords["eur"].get("dovish", [])):
            out.eur = "dovish"
    if "jpy" in keywords:
        if _match(headline, keywords["jpy"].get("hawkish", [])):
            out.jpy = "hawkish"
        elif _match(headline, keywords["jpy"].get("dovish", [])):
            out.jpy = "dovish"
    if "risk" in keywords:
        if _match(headline, keywords["risk"].get("risk_off", [])):
            out.risk = "risk_off"
        elif _match(headline, keywords["risk"].get("risk_on", [])):
            out.risk = "risk_on"
    return out


def bias_to_pair_direction(bias: KeywordBias) -> Tuple[str, str]:
    """Project KeywordBias onto (eur_usd_dir, usd_jpy_dir).

    Each direction ∈ {"long", "short", "neutral"}.

    Logic:
      - hawkish USD → EURUSD short, USDJPY long
      - dovish  USD → EURUSD long,  USDJPY short
      - hawkish EUR → EURUSD long
      - dovish  EUR → EURUSD short
      - hawkish JPY → USDJPY short
      - dovish  JPY → USDJPY long
      - risk_off    → USDJPY short (JPY bid), EURUSD short (EUR offered, USD bid)
      - risk_on     → USDJPY long, EURUSD long

    Conflicts collapse to neutral on that pair.
    """
    eur_usd_votes: List[int] = []  # +1 long, -1 short
    usd_jpy_votes: List[int] = []

    if bias.usd == "hawkish":
        eur_usd_votes.append(-1)
        usd_jpy_votes.append(+1)
    elif bias.usd == "dovish":
        eur_usd_votes.append(+1)
        usd_jpy_votes.append(-1)

    if bias.eur == "hawkish":
        eur_usd_votes.append(+1)
    elif bias.eur == "dovish":
        eur_usd_votes.append(-1)

    if bias.jpy == "hawkish":
        usd_jpy_votes.append(-1)
    elif bias.jpy == "dovish":
        usd_jpy_votes.append(+1)

    if bias.risk == "risk_off":
        eur_usd_votes.append(-1)
        usd_jpy_votes.append(-1)
    elif bias.risk == "risk_on":
        eur_usd_votes.append(+1)
        usd_jpy_votes.append(+1)

    return _resolve(eur_usd_votes), _resolve(usd_jpy_votes)


def _resolve(votes: List[int]) -> str:
    if not votes:
        return "neutral"
    s = sum(votes)
    if s > 0:
        return "long"
    if s < 0:
        return "short"
    return "neutral"
