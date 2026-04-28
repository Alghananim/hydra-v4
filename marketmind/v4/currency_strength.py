"""Currency Strength — basket-pairwise method.

Phase 1 audit lesson: V3's 0.75/0.25 hardcode (and news leaking into
strength) is REJECTED. V4 builds strength from PRICE pairs only, with
explicit `derived` flag when a currency is computed from too few pairs.

Method:
  For each pair of the form CCY1/CCY2 over a window:
    pct = (close_now - close_then) / close_then
    contribute +pct to CCY1 strength, -pct to CCY2 strength.
  Average over the contributions for each currency.
  Currencies with fewer than `min_pairs_direct` pairs are flagged as
  'derived(<value>)'.

Output: dict {ccy: float OR str("derived(<float>)")}.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Mapping, Any

from marketmind.v4.models import Bar


DEFAULT_WINDOW = 20
MIN_PAIRS_DIRECT = 3   # need at least 3 pair-contributions to call a strength "direct"


def _pct_change(bars: Sequence[Bar], window: int) -> float:
    if len(bars) < window + 1:
        return 0.0
    old = bars[-window - 1].close
    new = bars[-1].close
    if old <= 0:
        return 0.0
    return (new - old) / old


def _split_pair(pair: str):
    """Accept 'EURUSD' or 'EUR/USD'. Returns ('EUR','USD')."""
    p = pair.upper().replace("/", "").replace("-", "").replace("_", "")
    if len(p) != 6:
        return None
    return p[:3], p[3:]


def compute(
    baskets: Mapping[str, Sequence[Bar]],
    window: int = DEFAULT_WINDOW,
    min_pairs_direct: int = MIN_PAIRS_DIRECT,
) -> Dict[str, Any]:
    """Return {ccy: float | 'derived(<float>)'} for every currency seen.

    Each pair contributes BOTH currencies (one positive, one negative).
    """
    contribs: Dict[str, List[float]] = {}

    for pair, bars in baskets.items():
        sp = _split_pair(pair)
        if not sp:
            continue
        base, quote = sp
        pct = _pct_change(bars, window)
        contribs.setdefault(base, []).append(pct)
        contribs.setdefault(quote, []).append(-pct)

    out: Dict[str, Any] = {}
    for ccy, vals in contribs.items():
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        # Scale to a (-1..1)-ish band: 1% move on avg -> 0.5 strength.
        scaled = max(-1.0, min(1.0, avg * 50.0))
        if len(vals) >= min_pairs_direct:
            out[ccy] = round(scaled, 4)
        else:
            # Still surface the number, but mark as derived (not enough pairs)
            out[ccy] = f"derived({round(scaled, 4)})"
    return out


def numeric_value(v: Any) -> float:
    """Helper: extract float from either a raw float or the 'derived(x)' string."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.startswith("derived(") and v.endswith(")"):
        try:
            return float(v[len("derived("):-1])
        except ValueError:
            return 0.0
    return 0.0
