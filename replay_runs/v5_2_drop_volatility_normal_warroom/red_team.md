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
      52.5,
      29.6,
      81.9,
      -60.7
    ],
    "all_positive": false
  },
  "shadow_grade_B": {
    "segments_pips": [
      52.5,
      29.6,
      81.9,
      -60.7
    ],
    "all_positive": false
  },
  "shadow_2_of_3": {
    "segments_pips": [
      52.5,
      29.6,
      81.9,
      -60.7
    ],
    "all_positive": false
  }
}
```

## P5_per_pair_robustness — FAIL
```json
{
  "shadow_chart": {
    "USD_JPY": -53.8,
    "EUR_USD": 157.1
  },
  "shadow_grade_B": {
    "USD_JPY": -53.8,
    "EUR_USD": 157.1
  },
  "shadow_2_of_3": {
    "USD_JPY": -53.8,
    "EUR_USD": 157.1
  }
}
```

## P6_per_window_robustness — FAIL
```json
{
  "shadow_chart": {
    "in_window_morning": -152.5,
    "in_window_pre_open": 255.8
  },
  "shadow_grade_B": {
    "in_window_morning": -152.5,
    "in_window_pre_open": 255.8
  },
  "shadow_2_of_3": {
    "in_window_morning": -152.5,
    "in_window_pre_open": 255.8
  }
}
```

## P7_drawdown_floor — FAIL
```json
{
  "shadow_chart": {
    "net_pips": 103.3,
    "max_drawdown": 159.1,
    "drawdown_to_net_ratio": 1.54,
    "passed": false
  },
  "shadow_grade_B": {
    "net_pips": 103.3,
    "max_drawdown": 159.1,
    "drawdown_to_net_ratio": 1.54,
    "passed": false
  },
  "shadow_2_of_3": {
    "net_pips": 103.3,
    "max_drawdown": 159.1,
    "drawdown_to_net_ratio": 1.54,
    "passed": false
  }
}
```

## P8_loose_modes_dont_explode_drawdown — PASS
```json
{
  "baseline": 159.1,
  "shadow_chart": {
    "dd": 159.1,
    "ratio_vs_baseline": 1.0,
    "passed": true
  },
  "shadow_grade_B": {
    "dd": 159.1,
    "ratio_vs_baseline": 1.0,
    "passed": true
  }
}
```
