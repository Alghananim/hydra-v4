"""HYDRA live runtime package.

Two entry points only:
  - dry_run.py        : reads live data, runs all 5 brains + GateMind +
                        SmartNoteBook, but EVERY order-placement code
                        path is replaced with a no-op assertion. Used to
                        prove the system reads live data correctly.
  - controlled_live.py: same as dry_run but ONE additional gate is
                        unlocked: if HYDRA_LIVE_ARMED=1 in the env AND
                        a fresh per-day approval token is present,
                        controlled micro-orders may be placed. Every
                        single one of the 16 safety conditions in
                        safety_guards.py must be true; failure of any
                        one immediately aborts and never retries.

Live trading is NEVER on by default. The default state of every
production launcher is dry_run.
"""
