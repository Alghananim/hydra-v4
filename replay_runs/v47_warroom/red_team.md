# HYDRA 4.7 — Step 5 Red Team

Probes passed: **3 / 8**

## P1_no_lookahead_in_simulator — PASS
```json
[
  "loop bound and entry-bar reference are clean"
]
```

## P2_costs_deducted — PASS
```json
[
  "all three exit branches deduct COST_PIPS"
]
```

## P3_realistic_spread_floor — FAIL
```json
{
  "median_spread_pips_per_pair": {
    "EUR_USD": 1.5,
    "USD_JPY": 1.7
  },
  "assumed_round_trip_cost": 1.5,
  "verdict_note": "FAIL: actual median spread exceeds assumed cost; raise COST_PIPS"
}
```

## P4_segmented_robustness — FAIL
```json
{
  "shadow_chart": {
    "segments_pips": [
      -12.1,
      -21.2,
      -35.6,
      10.2
    ],
    "all_positive": false
  },
  "shadow_grade_B": {
    "segments_pips": [
      -12.1,
      -21.2,
      -35.6,
      10.2
    ],
    "all_positive": false
  },
  "shadow_2_of_3": {
    "segments_pips": [
      -12.1,
      -21.2,
      -35.6,
      10.2
    ],
    "all_positive": false
  }
}
```

## P5_per_pair_robustness — FAIL
```json
{
  "shadow_chart": {
    "EUR_USD": 16.8,
    "USD_JPY": -75.5
  },
  "shadow_grade_B": {
    "EUR_USD": 16.8,
    "USD_JPY": -75.5
  },
  "shadow_2_of_3": {
    "EUR_USD": 16.8,
    "USD_JPY": -75.5
  }
}
```

## P6_per_window_robustness — FAIL
```json
{
  "shadow_chart": {
    "in_window_morning": -97.2,
    "in_window_pre_open": 38.5
  },
  "shadow_grade_B": {
    "in_window_morning": -97.2,
    "in_window_pre_open": 38.5
  },
  "shadow_2_of_3": {
    "in_window_morning": -97.2,
    "in_window_pre_open": 38.5
  }
}
```

## P7_drawdown_floor — FAIL
```json
{
  "shadow_chart": {
    "net_pips": -58.7,
    "max_drawdown": 97.2,
    "drawdown_to_net_ratio": Infinity,
    "passed": false
  },
  "shadow_grade_B": {
    "net_pips": -58.7,
    "max_drawdown": 97.2,
    "drawdown_to_net_ratio": Infinity,
    "passed": false
  },
  "shadow_2_of_3": {
    "net_pips": -58.7,
    "max_drawdown": 97.2,
    "drawdown_to_net_ratio": Infinity,
    "passed": false
  }
}
```

## P8_loose_modes_dont_explode_drawdown — PASS
```json
{
  "baseline": 97.2,
  "shadow_chart": {
    "dd": 97.2,
    "ratio_vs_baseline": 1.0,
    "passed": true
  },
  "shadow_grade_B": {
    "dd": 97.2,
    "ratio_vs_baseline": 1.0,
    "passed": true
  }
}
```
