# HYDRA V4

> **Multi-brain decision system for FX. Clean rebuild — not a port of V3.**

## Status

| Brain        | Status        | Notes                                                          |
|--------------|---------------|----------------------------------------------------------------|
| NewsMind V4  | **BUILT**     | Foundation. Fail-CLOSED. Contract-enforced. Tests in place.    |
| MarketMind V4| not started   | blocked on NewsMind passing Red Team                            |
| ChartMind V4 | not started   |                                                                 |
| GateMind V4  | not started   |                                                                 |
| SmartNoteBook| not started   |                                                                 |
| EngineV4     | not started   |                                                                 |

## Principles (non-negotiable)

1. **No trust without evidence.** Every "done/works/ready" claim must produce: code + test + log + artifact.
2. **No skip-ahead.** Each brain must survive Red Team **before** the next brain starts.
3. **No wholesale copy from V3.** Only audited modules pass through. The rest is rebuilt clean.
4. **Contracts before code.** Every brain emits the shared `BrainOutput` dataclass. Wrong combinations RAISE.
5. **Fail-CLOSED.** When in doubt → `BLOCK`.

## Hard NO

- A / A+ grade without concrete evidence
- Claude (LLM reviewer) raising `BLOCK` to `ENTER` (downgrade-only authority)
- Empty sources treated as "all clear"
- Hardcoded confidence values (e.g., 0.95) without justification
- Live orders during backtest
- Lookahead / data leakage
- Catching broad `Exception` to hide root cause

## NewsMind V4 — what it is

A read-only news intelligence brain. Pulls from 5 authoritative + tier-1 cross-confirmation
sources (Fed, ECB, BoJ, FairEconomy calendar, ForexLive). Returns a `BrainOutput` with:

- `decision`: `BUY` | `SELL` | `WAIT` | `BLOCK`
- `grade`: `A+` | `A` | `B` | `C` | `BLOCK`
- `evidence`: list of concrete headlines / event ids / numeric values that justify the grade
- `should_block`: hard veto

NewsMind V4 **only emits `BLOCK` or `WAIT` directly** in this version — it does not by itself
produce `BUY` / `SELL`. Direction comes from the bias in `keywords.yaml` and the `eur_usd_dir` /
`usd_jpy_dir` fields, but the actual entry decision is owned by GateMind. NewsMind owns:

1. **Blackout detection** (scheduled events, ±5 min default).
2. **Source health surveillance** (silent feeds → BLOCK, never "all good").
3. **Surprise scoring** (actual − consensus, in σ units, mapped via `pip_per_sigma`).
4. **Headline keyword bias** (with a hard cap at grade C for unverified social sources).

## Layout

```
HYDRA V4\
  README.md
  ENGINEERING_PROTOCOL.md
  contracts\
    brain_output.py        # the shared BrainOutput contract
  config\
    news\
      events.yaml          # 10 curated EUR/USD + USD/JPY events
      keywords.yaml        # headline → bias map
  newsmind\
    v4\
      __init__.py
      models.py            # NewsItem, NewsVerdict, EventSchedule, NewsSummary
      sources.py           # stdlib RSS + JSON fetchers, no feedparser
      config_loader.py     # loads events.yaml + keywords.yaml
      event_scheduler.py   # blackout windows
      freshness.py         # KEEP from V3 — staleness detection
      permission.py        # KEEP from V3 — decision matrix
      intelligence.py      # surprise score + keyword bias
      llm_review.py        # Claude downgrade-only reviewer
      NewsMindV4.py        # orchestrator → BrainOutput
      NEWSMIND_V4_REPORT.md
      tests\
        test_contract.py
        test_sources.py
        test_blackout.py
        test_evaluate_end_to_end.py
```

## Running tests

```bash
cd "C:\Users\Mansur\Desktop\HYDRA V4"
python -m pytest newsmind/v4/tests -v
```
