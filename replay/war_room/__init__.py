"""HYDRA 4.7 War Room — total-failure investigation toolkit.

Modules (each is a separate sub-agent):
  diagnostics            : Step 1 - raw counts, distributions, top-N reasons
  bottleneck_attribution : Step 2 - which mind blocks how often, where
  shadow_pnl             : Step 3 - simulate forward P&L on rejected trades
  hypotheses             : Step 4 - one-rule-at-a-time experiments
  red_team               : Step 5 - adversarial integrity probes
  report_writer          : Step 6 - assembles the final markdown report

Entry point: war_room/run_war_room.py
"""
