"""HYDRA V4.8 — one-parameter-at-a-time sweep harness.

Given a base backtest output (V4.7 baseline), runs a sweep where ONE
knob is varied across its safe_range while every other knob stays at
production value. Each variant produces:

  - cycles.jsonl                    (variant-specific)
  - shadow_pnl.json                  (re-using the war_room simulator)
  - red_team.json                    (re-using all 8 probes)
  - summary row appended to compare.jsonl

The sweep is *deliberately conservative*: only safe_range is exercised
without explicit user approval. extreme_range requires a separate
architectural review and is gated behind a CLI flag.

Important: this harness does NOT modify the frozen orchestrator. It
applies variants by passing override kwargs at instantiation time only.
The live trading code path can never see a swept variant.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import parameters


@dataclass
class VariantSpec:
    knob: str
    value: Any
    label: str  # e.g. "grade_gate_minimum=B"

    @classmethod
    def for_safe_range(cls, knob_name: str) -> List["VariantSpec"]:
        k = parameters.by_name(knob_name)
        if k is None:
            return []
        out = []
        for v in k.safe_range:
            out.append(cls(knob=knob_name, value=v,
                            label=f"{knob_name}={v}"))
        return out


def planned_variants(allow_extreme: bool = False) -> List[VariantSpec]:
    out: List[VariantSpec] = []
    for k in parameters.registry():
        rng = k.extreme_range if allow_extreme and k.extreme_range else k.safe_range
        for v in rng:
            out.append(VariantSpec(knob=k.name, value=v,
                                    label=f"{k.name}={v}"))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--allow-extreme", action="store_true",
                   help="Include extreme_range values (requires user "
                        "approval; default off).")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--knob", type=str, default=None,
                   help="If set, only sweep this knob.")
    args = p.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.knob:
        variants = VariantSpec.for_safe_range(args.knob)
    else:
        variants = planned_variants(allow_extreme=args.allow_extreme)

    plan_path = args.out_dir / "sweep_plan.json"
    plan_path.write_text(
        json.dumps([asdict(v) for v in variants], indent=2),
        encoding="utf-8",
    )
    print(f"Sweep plan written: {plan_path}")
    print(f"Variants planned: {len(variants)}")
    print("(Actual per-variant backtest runs are kicked off by the V4.8 "
          "GitHub Actions workflow once you green-light the sweep "
          "from the V4.7 final report.)")


if __name__ == "__main__":
    main()
