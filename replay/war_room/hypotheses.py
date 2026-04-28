"""HYDRA 4.7 War Room — Step 4: hypothesis register.

Each hypothesis is one possible explanation for why only 9 trades came
out of ~21k cycles in the partial run. Every hypothesis is a *structured
record* with:

  - id            : H1, H2, ...
  - claim         : one-sentence statement
  - evidence_for  : counters from diagnostics that suggest it
  - evidence_against : counters that contradict it
  - test          : how we will test it (deterministic, reproducible)
  - risk          : what could go wrong if we act on it without checking

The list is intentionally **larger** than what we expect to hold up under
Red Team. Most hypotheses will be rejected. The point is that we
discover the few that survive evidence + adversarial review.

Usage: read hypotheses_register() to seed the report and the evaluation
harness. Feed test outcomes back via attach_test_result().
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Hypothesis:
    id: str
    claim: str
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    test: str = ""
    risk: str = ""
    test_result: Optional[Dict[str, Any]] = None
    verdict: Optional[str] = None  # "supported" | "rejected" | "inconclusive"


def hypotheses_register() -> List[Hypothesis]:
    return [
        Hypothesis(
            id="H1",
            claim="ChartMind very rarely emits BUY/SELL with grade A/A+, so the strict gate has nothing to pass.",
            evidence_for=["decision_distribution_by_mind for ChartMind",
                          "grade_distribution_by_mind for ChartMind"],
            evidence_against=["if ChartMind emits BUY/SELL often then this is wrong"],
            test=("From cycles.jsonl count cycles where chart.decision in "
                  "{BUY, SELL} AND chart.grade in {A, A+}. If << ENTER count "
                  "implies a sub-1%/cycle rate, ChartMind detection is the choke."),
            risk="Loosening grade is overfit if the B-grade signals are noisy.",
        ),
        Hypothesis(
            id="H2",
            claim="MarketMind hands out grade B (or worse) most of the time, so unanimous A is rare even when ChartMind is directional.",
            evidence_for=["MarketMind grade distribution skewed to B/C"],
            evidence_against=["MarketMind grade distribution skewed to A/A+"],
            test=("Compute % of in-window cycles where MarketMind grade in "
                  "{A, A+}. Compare to ChartMind and NewsMind. If MarketMind A-rate "
                  "is the worst, it is the principal grade gate failure."),
            risk="MarketMind B may reflect genuine regime uncertainty; loosening masks risk.",
        ),
        Hypothesis(
            id="H3",
            claim="NewsMind WAIT/A is functionally a non-vote, so the gate now lives entirely in MarketMind+ChartMind grade.",
            evidence_for=["NewsMind decision distribution (WAIT-only)",
                          "NewsMind grade distribution (mostly A under V4.7)"],
            evidence_against=["NewsMind frequently issues BLOCK"],
            test=("Confirm NewsMind decision distribution; confirm NewsMind never "
                  "appears as the lowest-grade attribution in bottleneck table."),
            risk="None — this is a structural observation, not a fix.",
        ),
        Hypothesis(
            id="H4",
            claim="ChartMind setup detector requires breakout confirmation that almost never occurs on M15.",
            evidence_for=["High proportion of (chart.decision == WAIT) even mid-window"],
            evidence_against=["ChartMind sometimes emits BUY/SELL"],
            test=("Plot histogram of ChartMind decision label per hour-of-day. "
                  "If WAIT dominates >95% even in 03-05 NY, threshold is too high."),
            risk="Lowering threshold raises false positives -> drawdown.",
        ),
        Hypothesis(
            id="H5",
            claim="The session window (only 6h/day across pre-open + morning) excludes the bulk of valid setups.",
            evidence_for=["session_outside_window dominates final_status"],
            evidence_against=["No expectation that off-hours improve win rate on EUR/USD"],
            test=("Run shadow_chart over the full timeline ignoring session "
                  "filter. Compare in-window vs out-of-window net pips."),
            risk="Out-of-hours liquidity may be poor — actual fills worse than backtest.",
        ),
        Hypothesis(
            id="H6",
            claim="V4.7 'incomplete_agreement' (chart=WAIT, news/market directional) blocks trades where News/Market actually had it right.",
            evidence_for=["incomplete_agreement count in final_reason"],
            evidence_against=["NewsMind never emits BUY/SELL, so this branch can only fire on rare MarketMind directional"],
            test=("Count cycles where final_reason==incomplete_agreement AND "
                  "(news.decision in {BUY,SELL} OR market.decision in {BUY,SELL}). "
                  "Run shadow P&L on those."),
            risk="Reversing this lets MarketMind override Chart's caution -> bigger losses.",
        ),
        Hypothesis(
            id="H7",
            claim="data_quality flag 'stale' is over-triggering on weekend-spanning windows even after the Phase 9 fix.",
            evidence_for=["MarketMind data_quality distribution shows non-trivial 'stale' or 'missing'"],
            evidence_against=["data_quality is mostly 'good'"],
            test=("Count in-window cycles where MarketMind data_quality != 'good'. "
                  "If >5% it is still misfiring."),
            risk="None — this is a bug fix if confirmed.",
        ),
        Hypothesis(
            id="H8",
            claim="The 500-bar lookback warm-up consumes the first ~5 trading days, so the first chunk is structurally trade-less.",
            evidence_for=["BLOCK rate in first 1000 in-window cycles vs later"],
            evidence_against=["If trade rate is uniform across timeline this is wrong"],
            test=("Bin cycles by week-of-backtest. Compute ENTER rate per bin. "
                  "If week 1-2 is 0 but later weeks are >0, warm-up is real but bounded."),
            risk="None — informational.",
        ),
        Hypothesis(
            id="H9",
            claim="The 2-trades/day target is structurally impossible under the current grade-A unanimous rule given real M15 noise.",
            evidence_for=["Diagnostics show A-unanimous-and-directional << 2/day"],
            evidence_against=["If grade thresholds tuned correctly, ChartMind may produce >> 2/day setups"],
            test=("Compute upper-bound daily rate of (chart.decision in {BUY,SELL} "
                  "AND chart.grade in {A,A+}). If avg < 2/day, grade rule alone "
                  "cannot deliver target."),
            risk="Stating impossibility without exhausting calibration is premature.",
        ),
        Hypothesis(
            id="H10",
            claim="Per-cycle SmartNoteBook writes are slowing the runner enough to artificially shorten the chunk's covered timeline.",
            evidence_for=["sandbox /tmp filled at ~21k cycles"],
            evidence_against=["Same code runs fine on local disk with more space"],
            test=("Time the runner with notebook stubbed vs full notebook. "
                  "Compare cycles/sec."),
            risk="Stubbing notebook in production breaks audit trail.",
        ),
        Hypothesis(
            id="H11",
            claim="Backtest engine skips ENTER opportunities at bar boundaries because lookback uses bars[lo:idx+1] where idx is the entry bar (entry on close), not enough forward bars to confirm.",
            evidence_for=["run_v47_backtest.py uses visible = bars[lo:idx+1]"],
            evidence_against=["Each cycle gets ChartMind, MarketMind a full 500-bar history"],
            test=("Inspect ChartMind setup detector for confirmation lookahead. "
                  "It must NOT use bars beyond the entry bar."),
            risk="If lookahead exists -> reported P&L is fictional.",
        ),
        Hypothesis(
            id="H12",
            claim="Costs (spread + slippage) are missing from the orchestrator's trade candidate, so even ENTER trades over-report when fed to a P&L engine that doesn't deduct.",
            evidence_for=["BrainOutput contract shows no cost field"],
            evidence_against=["pnl_simulator may add cost itself"],
            test=("Read pnl_simulator.py; confirm a cost deduction exists."),
            risk="If costs not deducted -> overstated win rate.",
        ),
        Hypothesis(
            id="H13",
            claim="ChartMind grade calibration (B vs A vs A+) is uncorrelated with future win rate, so loosening to B doesn't actually buy more profitable trades.",
            evidence_for=["shadow_grade_B vs shadow_chart can show win-rate delta"],
            evidence_against=["If win rate of grade-B trades is comparable to grade-A, grading is conservative-only"],
            test=("Compare win rate of shadow_grade_B trades restricted to "
                  "grade-B vs grade-A in same population."),
            risk="If B is genuinely worse, loosening hurts.",
        ),
        Hypothesis(
            id="H14",
            claim="Replay calendar (174 events) misses many high-impact periods — NewsMind permission is correct but the scheduler does not actually elevate news risk during the relevant windows, so NewsMind never gates real news.",
            evidence_for=["NewsMind decision distribution dominated by WAIT"],
            evidence_against=["NewsMind sometimes BLOCKs"],
            test=("Count NewsMind BLOCK occurrences and timestamps. Confirm they "
                  "align with calendar entries."),
            risk="None — informational; a fix would be a calendar enrichment.",
        ),
        Hypothesis(
            id="H15",
            claim="Costs of 1.5 pips for round-trip are too low; real broker would charge 2-4 pips and slippage. Inflated win rate.",
            evidence_for=["Industry norm 2-4 pip round-trip on M15"],
            evidence_against=["spread_pips field in cached bars shows actual mid-bid-ask spread"],
            test=("Compute median spread_pips across cached bars per pair; "
                  "compare to assumed cost. If median > assumed, raise cost in shadow."),
            risk="Raising cost worsens reported P&L; that's the honest direction.",
        ),
    ]


def attach_test_result(h: Hypothesis, result: Dict[str, Any],
                        verdict: str) -> Hypothesis:
    h.test_result = result
    h.verdict = verdict
    return h


def render_markdown(hs: List[Hypothesis]) -> str:
    lines = ["# HYDRA 4.7 — Step 4 Hypothesis Register\n"]
    lines.append("Each row is a candidate explanation for the under-trading. "
                  "The verdict column is filled in once the corresponding test "
                  "runs and the Red Team has had a pass.\n")
    for h in hs:
        lines.append(f"## {h.id}: {h.claim}")
        lines.append(f"**Test:** {h.test}")
        lines.append(f"**Risk if acted on without check:** {h.risk}")
        if h.evidence_for:
            lines.append("Evidence for: " + "; ".join(h.evidence_for))
        if h.evidence_against:
            lines.append("Evidence against: " + "; ".join(h.evidence_against))
        if h.verdict:
            lines.append(f"**Verdict:** {h.verdict}")
        if h.test_result:
            lines.append("Test result:")
            lines.append("```json")
            lines.append(json.dumps(h.test_result, indent=2, default=str))
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


def run(out_dir: Path) -> List[Hypothesis]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hs = hypotheses_register()
    (out_dir / "hypotheses.json").write_text(
        json.dumps([asdict(h) for h in hs], indent=2, default=str),
        encoding="utf-8",
    )
    (out_dir / "hypotheses.md").write_text(
        render_markdown(hs), encoding="utf-8"
    )
    return hs


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args()
    run(args.out_dir)
    print(f"hypothesis register written to {args.out_dir}")
