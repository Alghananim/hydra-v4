# HYDRA V5 CODE

The actual code that V5 runs lives at the parent `HYDRA V4` tree, **not** here. This is intentional:

- Single source of truth: every module is in exactly one place.
- No duplication: a fix to `gatemind/v4/consensus_check.py` does not need to be mirrored.
- Smaller V5 folder: easy to back up, easy to diff between releases.

The folders that V5 depends on (in `HYDRA V4/`):

| Folder | What's in it |
|---|---|
| `contracts/` | The shared `BrainOutput` contract and frozen invariants. |
| `newsmind/v4/` | NewsMind brain. |
| `marketmind/v4/` | MarketMind brain. |
| `chartmind/v4/` | ChartMind brain. |
| `gatemind/v4/` | GateMind + V4.7 consensus_check. |
| `smartnotebook/v4/` | Audit ledger. |
| `orchestrator/v4/` | The 5-brain orchestrator. |
| `live_data/` | OANDA read-only client. |
| `live/` | V4.8 dry-run, V4.9 controlled-live, 16-condition safety guards. |
| `replay/` | 2-year backtest runner + War Room toolkit + V4.8 calibration. |
| `data_cache/` | M15 cached bars for EUR/USD and USD/JPY. |
| `.github/workflows/` | GitHub Actions cloud pipeline. |

Run `Run_HYDRA_V5.bat` (one folder up) — it sets `PYTHONPATH=HYDRA V4` and dispatches to the appropriate module.

## Why no copy here

A previous V3 → V4 step duplicated brains into per-brain folders, each with its own `.git`. That created the partial-push bug we hit on the first GitHub upload. Lesson: keep the code in one place. V5 inherits cleanly from V4 by reference, not by copy.
