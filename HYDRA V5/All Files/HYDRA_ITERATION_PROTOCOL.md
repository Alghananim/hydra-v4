# HYDRA Iteration Protocol — V5.1 → V10

This document governs every version after V5. No version is released until each step below is completed and recorded.

## The 8-step cycle (mandatory per version)

```
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ 1 Research │ → │ 2 Debate   │ → │ 3 Diagnose │ → │ 4 Hypothesis│
└────────────┘   └────────────┘   └────────────┘   └────────────┘
                                                          ↓
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│ 8 Decide   │ ← │ 7 Compare  │ ← │ 6 Red Team │ ← │ 5 Build/Fix │
└────────────┘   └────────────┘   └────────────┘   └────────────┘
                                                          ↓
                                                    ┌────────────┐
                                                    │ Tests run  │
                                                    └────────────┘
```

### 1. Research
Look at: previous version's data, recent literature on the problem, and any analogous open-source systems. Cite sources.

### 2. Debate
Each agent (Performance, Risk, Code Quality, Red Team, Architecture) writes a 1–2 paragraph position. The debate must surface dissent, not simulate consensus.

### 3. Diagnose
State the **single** root cause this version will address. Multiple causes ⇒ split into multiple versions.

### 4. Hypothesis
Write the change as a falsifiable hypothesis: "If we change X, then metric Y will improve from Z₀ to Z₁ on the same backtest data, without regressing metric Y′."

### 5. Build / Fix
Implement. Keep the diff small. Single concern. No drive-by improvements.

### 6. Tests
Unit + integration + replay + Red Team. The 8 War Room probes (P1–P8) must all pass on the new version before it can claim improvement.

### 7. Compare
A `before_after.md` table per version. Required columns:

| Metric | Before | After | Δ | Verdict |
|---|---|---|---|---|
| ENTER_CANDIDATE | … | … | … | improved/regressed/flat |
| WAIT | … | … | … | … |
| Win rate (excl. timeout) | … | … | … | … |
| Net pips | … | … | … | … |
| Max drawdown | … | … | … | … |
| Per-pair EUR/USD net | … | … | … | … |
| Per-pair USD/JPY net | … | … | … | … |
| Red Team probes passed | x/8 | y/8 | … | … |

### 8. Decide
APPROVED only if all of:
- Hypothesis statement holds with evidence in column "After".
- No regression on a non-target metric.
- Red Team 8/8 (or no probe regressed from previous version).
- Code review clean.

Otherwise REJECTED. Rejected versions are documented as a rejected branch (`HYDRA_V5_2_REJECTED_REPORT.md`) — failure is data, not shame.

## Per-version artefacts (mandatory)

Every version commits these files together:

```
HYDRA_V<N>_UPGRADE_REPORT.md       — narrative + evidence
replay_runs/v<N>_warroom/           — auto-generated diagnostics
HYDRA V5/All Files/                 — synced report copies
```

## Versioning naming

- `V5.X` (X >= 1) = small incremental upgrade, single-concern.
- `V6` = first major (e.g. ChartMind redesign).
- `V7` = second major (e.g. multi-timeframe).
- `V8` = third major.
- `V9` = pre-final hardening pass.
- `V10` = final, only released when V9 + 30-day live-paper observation passes Red Team.

## Hard rules (cannot be relaxed by any version)

- No look-ahead.
- No data leakage.
- No live execution without 16-condition guard + arming + token.
- No risk > 0.25 % equity per trade in V4.9; reviewed per major version.
- No secrets in tracked source.
- No version released without a written upgrade report.
- No version released without a before/after comparison.
- No version released without Red Team verdict.
- No version released purely "looks better" without numbers.

## Decision audit trail

Each accepted version's commit message follows the pattern:

```
hydra-v<N> APPROVED: <one-line claim>

Hypothesis: <statement>
Evidence: <metric> <before> → <after>
Red Team: 8/8 (or N/8 with documented exception)
```

This makes `git log --oneline` a readable history of accepted improvements.

## What "stop" looks like

The iteration stops at V<N> when all of:
- Three consecutive proposed versions are REJECTED for the same root-cause family.
- Red Team cannot break the current state on any probe.
- A 30-day live-paper run on practice account shows live-vs-backtest divergence < 10 %.

At that point, V<N> is renamed V10 and frozen.

## What this protocol is NOT

- Not a guarantee that the system will reach 2 trades/day or 150 % return. Those targets may prove structurally infeasible. The protocol guarantees only that we will know, by evidence, whether they are feasible.
- Not a substitute for the user's judgement. The user can override an APPROVED verdict (rare, but allowed). Overrides are logged.
- Not faster than the underlying compute. Each version requires a full cloud backtest. That's ~6 minutes of GitHub Actions per version.
