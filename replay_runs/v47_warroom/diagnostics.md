# HYDRA 4.7 — Step 1 Diagnostics

Input: `replay_runs/v47_2y/cycles.jsonl`  
Total records analysed: **22,386**

## final_status counts
- BLOCK: 22,361
- WAIT: 13
- ENTER_CANDIDATE: 12

## In-trading-window breakdown
- Cycles inside NY pre-open or morning: **5,600**
  - BLOCK: 5,575
  - WAIT:  13
  - ENTER_CANDIDATE: 12

## Top final_reason counts
- `outside_new_york_trading_window`: 16,786
- `grade_below_threshold`: 5,574
- `R7_unanimous_wait:WAIT`: 13
- `all_brains_unanimous_enter`: 12
- `kill_flag_active`: 1

## Session distribution
- outside_window: 16,786
- in_window_morning: 3,744
- in_window_pre_open: 1,856

## Pair distribution
- EUR_USD: 11,193
- USD_JPY: 11,193

## Grade distribution by mind
- NewsMind: A=22,229, BLOCK=157
- MarketMind: B=6,558, C=3,813, A=535, BLOCK=11,480
- ChartMind: B=6,716, C=4,125, A=60, BLOCK=11,480, A+=5

## Decision distribution by mind
- NewsMind: WAIT=22,229, BLOCK=157
- MarketMind: WAIT=10,906, BLOCK=11,480
- ChartMind: WAIT=10,873, SELL=9, BLOCK=11,480, BUY=24

## Data-quality distribution by mind
- NewsMind: good=22,386
- MarketMind: good=17,962, stale=4,424
- ChartMind: good=22,386

## Top 20 decision triples (news, market, chart)
- ('WAIT', 'BLOCK', 'BLOCK'): 11,323
- ('WAIT', 'WAIT', 'WAIT'): 10,873
- ('BLOCK', 'BLOCK', 'BLOCK'): 157
- ('WAIT', 'WAIT', 'BUY'): 24
- ('WAIT', 'WAIT', 'SELL'): 9

## Top 30 (triple, final_reason) combos
- ('WAIT', 'BLOCK', 'BLOCK') -> `outside_new_york_trading_window`: 9,995
- ('WAIT', 'WAIT', 'WAIT') -> `outside_new_york_trading_window`: 6,700
- ('WAIT', 'WAIT', 'WAIT') -> `grade_below_threshold`: 4,160
- ('WAIT', 'BLOCK', 'BLOCK') -> `grade_below_threshold`: 1,328
- ('BLOCK', 'BLOCK', 'BLOCK') -> `grade_below_threshold`: 86
- ('BLOCK', 'BLOCK', 'BLOCK') -> `outside_new_york_trading_window`: 71
- ('WAIT', 'WAIT', 'BUY') -> `outside_new_york_trading_window`: 13
- ('WAIT', 'WAIT', 'WAIT') -> `R7_unanimous_wait:WAIT`: 13
- ('WAIT', 'WAIT', 'BUY') -> `all_brains_unanimous_enter`: 10
- ('WAIT', 'WAIT', 'SELL') -> `outside_new_york_trading_window`: 7
- ('WAIT', 'WAIT', 'SELL') -> `all_brains_unanimous_enter`: 2
- ('WAIT', 'WAIT', 'BUY') -> `kill_flag_active`: 1
