# HYDRA V5 — Limitations & Risks

This document is deliberately direct. The system has real limits, and the user deserves to read them in plain language before relying on V5 for anything financial.

## Performance limits (architectural)

- **Trade rate ceiling.** The strict V4.7 rule (ChartMind directional A/A+ + News/Market non-opposing + 6-hour NY window) caps the upper bound on ENTER candidates at whatever rate ChartMind emits directional A/A+ inside the trading windows. The partial-run projection is ~0.06 trades/day. Until a calibration sweep proves a safe-range knob raises this, **the 2-trades-per-day target is structurally not met**.
- **Return ceiling.** 150 % over 2 years requires roughly 4,500–10,000 net pips after costs. The shadow P&L simulator under V4.7's strict rule does not yet reach that. The honest reading: 150 % is currently **not achievable** without either (a) a successful V4.8 calibration that survives Red Team, or (b) a redesign of the instrument set or timeframe.

## Engineering limits

- **Live OANDA writer is not in this release.** Even when armed, controlled-live degrades to dry-run because there is no `live_data/oanda_live_client.py` shipped. This is intentional. A writer client must be hand-written, audited, and signed off separately. This document blocks live execution from happening accidentally.
- **No backtest of the calibration variants on live data.** Backtests run on cached bars only. Real-world fills, slippage, and broker quirks are not modelled beyond the 1.5-pip cost assumption. Real fills will likely be worse.
- **Sandbox `/tmp` size.** SmartNoteBook writes per-cycle records. Long replay runs in constrained environments (like the in-conversation Linux sandbox) fill `/tmp`. The cloud workflow uses GitHub Actions runners which have ample disk; the laptop has ample disk. Only the in-conversation sandbox was wedged, and that is no longer used.
- **Pre-existing test bug.** `orchestrator/v4/tests/test_scalability.py::test_no_internal_state_between_cycles` asserts non-determinism that contradicts the documented `make_audit_id` contract. This test fails on every run. It is unrelated to V4.7 and pending cleanup.

## Risk limits

- **Risk per trade.** Hard cap at 0.25 % of equity (guard G10). V4.9 default is 0.10 %. Above-cap settings cannot be passed to the live launcher.
- **Daily loss.** Hard cap at 1.0 % of equity (guard G15). On hit, no further orders that day.
- **Trades per day.** Hard cap at 4 (guard G16). On hit, no further orders that day.
- **Spread.** Orders blocked when spread > 2.5 pips on the entry bar (guard G08).
- **Data freshness.** Orders blocked when the last bar is older than 1.5 × bar interval (guard G09).
- **Kill switch.** `replay_runs\controlled_live\KILL` file presence stops trading instantly (guard G14).

## Known unknowns

- We do not yet know the V4.7 backtest's full-run number (cloud run in progress at writing time).
- We do not yet know whether any safe-range calibration variant in V4.8 will survive Red Team.
- We do not yet know whether the M15 + 6h-window + 2-pair combination is feasible for the user's stated goals; that question is answered only by V4.8.
- We do not know how the system behaves under a fast news event that arrives between bar boundaries; the freshness guard partly mitigates but does not eliminate this risk.

## What V5 is not

- It is **not** a guarantee of profit.
- It is **not** a guarantee of the 2-trades/day target.
- It is **not** a guarantee of the 150 % target.
- It is **not** a substitute for the user's own oversight of the launcher window.
- It is **not** approved for use on a live OANDA account in V4.9. V4.9 is a practice-account exercise.

## Trade-offs the user is making by adopting V5

| Choice | Cost | Benefit |
|---|---|---|
| GitHub repo Public (private blocked by region) | The code is world-readable. | Zero-cost cloud CI; no laptop dependency. |
| Strict A/A+ grade gate by default | Few trades. | Fewer false positives. |
| 16-condition pre-trade guard | Extra latency per cycle (single-digit ms). | Defence in depth on top of LIVE_ORDER_GUARD. |
| Per-day approval token | Manual step every day. | Cannot accidentally trade days when the user is not watching. |

These are not bugs. They are the deliberate choices the user committed to with the project's principles ("fail-CLOSED, when in doubt → BLOCK").
