# NewsMind V4 — Build Report

**Date:** 2026-04-27
**Author:** NewsMind V4 Build Agent
**Target:** `C:\Users\Mansur\Desktop\HYDRA V4`

---

## 1. What was built

19 deliverables, all under `C:\Users\Mansur\Desktop\HYDRA V4\`:

| #  | Path                                                         | Role                                  |
|----|--------------------------------------------------------------|---------------------------------------|
| 1  | `README.md`                                                  | overview, status table, principles    |
| 2  | `contracts\__init__.py`                                      | re-exports                            |
| 3  | `contracts\brain_output.py`                                  | **the** shared BrainOutput contract   |
| 4  | `config\news\events.yaml`                                    | 10 curated EUR/USD + USD/JPY events   |
| 5  | `config\news\keywords.yaml`                                  | hawkish/dovish + risk maps            |
| 6  | `newsmind\__init__.py`                                       | package marker                        |
| 7  | `newsmind\v4\__init__.py`                                    | public surface                        |
| 8  | `newsmind\v4\models.py`                                      | NewsItem, NewsVerdict, NewsSummary, EventSchedule, SourceHealth |
| 9  | `newsmind\v4\sources.py`                                     | stdlib RSS+JSON adapters, **no feedparser** |
| 10 | `newsmind\v4\config_loader.py`                               | YAML loader (PyYAML or stdlib mini-YAML) |
| 11 | `newsmind\v4\event_scheduler.py`                             | actually loads events.yaml + occurrence registry |
| 12 | `newsmind\v4\freshness.py`                                   | KEEP (V3 spirit, V4 imports)          |
| 13 | `newsmind\v4\permission.py`                                  | KEEP (decision matrix, fail-CLOSED)   |
| 14 | `newsmind\v4\chase_detector.py`                              | KEEP (pure function)                  |
| 15 | `newsmind\v4\intelligence.py`                                | REBUILT — uses `pip_per_sigma`        |
| 16 | `newsmind\v4\NewsMindV4.py`                                  | orchestrator → BrainOutput            |
| 17 | `newsmind\v4\llm_review.py`                                  | Claude downgrade-only reviewer        |
| 18 | `newsmind\v4\tests\test_contract.py`                         | BrainOutput invariants                |
| 19 | `newsmind\v4\tests\test_sources.py`                          | RSS/JSON parser + SourceHealth + no-feedparser |
| -  | `newsmind\v4\tests\test_blackout.py`                         | fail-CLOSED + chase + confirmations   |
| -  | `newsmind\v4\tests\test_evaluate_end_to_end.py`              | full path tests                       |
| -  | `newsmind\v4\tests\conftest.py`                              | sys.path setup                        |
| -  | `newsmind\v4\NEWSMIND_V4_REPORT.md`                          | this file                             |

(The 19 listed deliverables plus a few package markers, conftest, and tests for the core paths.)

---

## 2. Tests added

| Category               | Test file                          | Purpose |
|------------------------|------------------------------------|---------|
| Contract invariants    | `test_contract.py`                 | A/A+ requires evidence + good data; should_block coupled to BLOCK; tz-aware UTC enforced; brain_name and decision enums; fail_closed factory shape |
| Source layer           | `test_sources.py`                  | RSS title+pubDate extraction; missing-pubDate skip; SourceTimeout typed; SourceHealth records last_fetch_utc; distinct error classes; **`feedparser` not imported**; JSON calendar parses; JSON parse error surfaces |
| Blackout / fail-CLOSED | `test_blackout.py`                 | silent sources at NFP → BLOCK; ±5 min FOMC → BLOCK; outside window does not blackout-block; social chase capped at C (never A); chase_detector unit; grade A requires ≥2 confirmations; two confirmations can reach A |
| End-to-end             | `test_evaluate_end_to_end.py`      | no-news returns BLOCK; events.yaml actually loads ≥10 events with real `pip_per_sigma`; BrainOutput contract holds; orchestrator fails-CLOSED on unexpected exception (monkeypatched); last_verdict attached |

Live verification I ran in the workspace:

- **BrainOutput contract**: 5 invariants individually triggered as expected (A+ no-evidence raises; A stale raises; should_block=True with B raises; BLOCK construction passes; `fail_closed` factory passes).
- **events.yaml**: parsed by both PyYAML and the stdlib mini-YAML; 10 events; `pip_per_sigma` populated for every event; tiers 1+2 distinguished.
- **RSS parser**: 2-item fixture parsed; pubDate → tz-aware UTC; items without pubDate dropped (the V3 leak).
- **Grade ladder**: 9 scenarios, all match spec including `tier-2 cannot reach A+` and `chase always caps at C`.

---

## 3. What was REJECTED from V3 (with reason)

| V3 artefact / behaviour                                         | Verdict | Why                                                                 |
|-----------------------------------------------------------------|---------|---------------------------------------------------------------------|
| `feedparser` dependency                                          | REJECT  | Heavy 3rd-party; stdlib `urllib + xml.etree` is sufficient and audit-friendly |
| V3 `event_scheduler.py` (hardcoded empty list)                   | REJECT  | Silently produced "no blackout" — a critical fail-OPEN bug          |
| V3 `intelligence.py` flat "high impact = 50 pips"                | REJECT  | Ignored the per-event calibration that already existed in the repo |
| V3 `NewsVerdict` fields: `published_at`, `received_at`, `conflicting_sources`, `sources_checked` | DROP | Redundant with `normalized_utc_time`; V4 uses `confirmation_count` + `source_health` |
| `27 events` from V3                                              | TRIM    | Many were JPY-cross or commodity-driven; V4 is EUR/USD + USD/JPY only |
| LLM "approve / enter / upgrade" suggestions                      | REJECT  | LLM is downgrade-only. Enum surface excludes any upgrade pathway   |
| Hardcoded 0.95 confidence in V3 grade-A path                     | REJECT  | Confidence is now derived from observable facts (data_quality, freshness, confirmations, surprise) |
| V3 `permission.decide(item, ...)` exception swallowing returning verdict with grade C | KEEP-but-tightened | Kept as last-line fail-CLOSED safety net; V4 wraps it inside the orchestrator's outer fail-CLOSED |

---

## 4. KEPT vs REBUILT

**KEPT (semantics; imports & interface adapted to V4):**
- `freshness.py` — staleness tiers; missing timestamp → conservative classification
- `permission.py` — top-down decision matrix, fail-CLOSED on internal exception
- `chase_detector.py` — pure function with the same heuristics

**REBUILT:**
- `sources.py` — entirely rewritten on stdlib (`urllib.request`, `xml.etree.ElementTree`, `email.utils.parsedate_to_datetime`, `json`); distinct error taxonomy (`SourceTimeout`, `SourceParseError`, `SourceEmpty`, `SourceHTTPError`); `SourceHealth` per source.
- `event_scheduler.py` — actually reads `events.yaml`, exposes `is_in_blackout` and `get_active_event` and tracks an `EventOccurrence` registry.
- `intelligence.py` — `surprise_score` (sigma units), `pip_impact` / `signed_pip_impact` derived from `events.yaml.pip_per_sigma` per event, `keyword_bias` / `bias_to_pair_direction` for keyword-derived direction.
- `NewsMindV4.py` — new orchestrator; emits `BrainOutput`; never `BUY/SELL` directly (always `WAIT` or `BLOCK`); single fail-CLOSED boundary.
- `llm_review.py` — Claude tool-call schema with enum `("agree","downgrade","block")` only; caller-side enum clamp re-maps any off-enum value to `"block"`; `audit_hash = sha256(prompt+response)[:16]`; gracefully stubs to `severity="unknown"` when API key or SDK is absent.

---

## 5. Lines of code

```
contracts/brain_output.py        ~152
newsmind/v4/models.py            ~150
newsmind/v4/sources.py           ~280
newsmind/v4/config_loader.py     ~262
newsmind/v4/event_scheduler.py    ~95
newsmind/v4/freshness.py          ~55
newsmind/v4/permission.py         ~60
newsmind/v4/chase_detector.py     ~50
newsmind/v4/intelligence.py      ~190
newsmind/v4/llm_review.py        ~190
newsmind/v4/NewsMindV4.py        ~390
tests/* (4 files)                ~410
README.md                        ~85
events.yaml + keywords.yaml      ~190
NEWSMIND_V4_REPORT.md            (this file)
                              ─────
                                ~2.6k SLOC of Python + ~270 of YAML/MD
```

---

## 6. Gaps / TODOs

1. **Anthropic API call**: `llm_review.review()` requires `ANTHROPIC_API_KEY` env var AND the `anthropic` SDK installed to actually run. Without either, it returns a stub with `severity="unknown"` and `suggestion="agree"` — i.e. the LLM is a no-op. Red Team should test BOTH paths: with API present (real downgrade behaviour) and without (stubbed agree).
2. **Calendar → EventOccurrence wiring**: `JSONCalendarSource.fetch()` returns `NewsItem`s but does NOT auto-populate `EventScheduler.load_occurrences(...)`. In production the orchestrator/scheduler integration must be wired so a calendar entry like `{title: "Non-Farm Employment Change", date: "..."}` results in `(event_id="us_nfp", scheduled_utc=...)`. The mapping table from calendar `title` → `events.yaml.id` is not yet implemented; for now scheduled occurrences must be loaded explicitly via `scheduler.load_occurrences(...)`.
3. **`surprise_score` real values**: V4 currently returns `0.0` for surprise unless the orchestrator is fed a wired-in actual+consensus+std_dev triple. The math is in `intelligence.surprise_score()` and the calibration is in `events.yaml.pip_per_sigma`, but the data path `calendar JSON → (actual, consensus, std_dev)` is not yet computed (the calendar JSON often lacks `std_dev`, only `forecast` and `actual`). Until calibrated std_dev is sourced, A+ grade is effectively unreachable through the live path — which is the **safe** default for a freshly-built brain.
4. **No live HTTP test in this report**. Tests use injected fixture sources (`_StaticSource`, `_FixtureRSS`) — they do NOT hit the network. That's intentional for hermetic CI; a separate smoke-test must be added before going live.
5. **PyYAML availability**: production must either ship PyYAML or accept the bundled `_mini_yaml_parse`. The mini-parser was tested against the real `events.yaml` and returned an identical structure (10 events, correct tiers, correct `pip_per_sigma`).
6. **DST / timezone edge**: `NewsItem.normalized_utc_time` is enforced tz-aware UTC, but the per-source parsers fall back to assuming UTC if the source omits a timezone. That is conservative for the 5 default sources but a custom source emitting `"2026-04-27 13:00:00"` with no offset will be tagged UTC even if the source meant local time.
7. **No persistence of SourceHealth across calls**. Each `evaluate()` re-instantiates SourceHealth via the source's own attribute, but `consecutive_failures` is preserved across calls only if the same `NewsMindV4` instance is reused. CLI/cron callers that build a new instance each tick will lose the streak counter.

---

## 7. ONE adversarial test for the next Red Team agent

> **`test_silent_majority_pretending_clear`** — point all 5 default sources at a fixture that returns HTTP 200 with an empty `<rss><channel></channel></rss>` body (no `<item>` elements). Each source should raise `SourceEmpty` and record `last_status="empty"`. The orchestrator must:
>
> 1. Set `data_quality` to `"missing"` (NOT `"good"`).
> 2. Return `BrainOutput` with `decision=="BLOCK"`, `grade==BLOCK`, `should_block==True`.
> 3. Include `risk_flags` containing `"src:<name>:empty"` for each source.
> 4. Critically: **the `evidence` list must NOT be empty** — it must contain the per-source health states (`source_health=federalreserve.gov:empty,...`).
>
> The kill condition: if the brain ever returns `decision="WAIT"` with `data_quality="good"` while every source is silent, the V4 fail-CLOSED guarantee is broken. Silence is **never** all-clear.
