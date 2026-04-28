# HYDRA 4.7 — Step 1 Diagnostics

Input: `replay_runs/v5_2_drop_volatility_normal/cycles.jsonl`  
Total records analysed: **99,298**

## final_status counts
- BLOCK: 99,205
- ENTER_CANDIDATE: 53
- WAIT: 40

## In-trading-window breakdown
- Cycles inside NY pre-open or morning: **24,816**
  - BLOCK: 24,723
  - WAIT:  40
  - ENTER_CANDIDATE: 53

## Top final_reason counts
- `outside_new_york_trading_window`: 74,482
- `grade_below_threshold`: 24,721
- `all_brains_unanimous_enter`: 53
- `R7_unanimous_wait:WAIT`: 40
- `kill_flag_active`: 2

## Session distribution
- outside_window: 74,482
- in_window_pre_open: 8,272
- in_window_morning: 16,544

## Pair distribution
- EUR_USD: 49,649
- USD_JPY: 49,649

## Grade distribution by mind
- NewsMind: A=98,572, BLOCK=726
- MarketMind: BLOCK=50,635, C=17,279, B=29,277, A=2,107
- ChartMind: BLOCK=50,635, C=18,492, B=29,920, A=216, A+=35

## Decision distribution by mind
- NewsMind: WAIT=98,572, BLOCK=726
- MarketMind: BLOCK=50,635, WAIT=48,658, BUY=5
- ChartMind: BLOCK=50,635, WAIT=48,524, BUY=93, SELL=46

## Data-quality distribution by mind
- NewsMind: good=99,298
- MarketMind: missing=8, good=72,525, stale=26,765
- ChartMind: missing=58, good=99,240

## Top 20 decision triples (news, market, chart)
- ('WAIT', 'BLOCK', 'BLOCK'): 49,909
- ('WAIT', 'WAIT', 'WAIT'): 48,523
- ('BLOCK', 'BLOCK', 'BLOCK'): 726
- ('WAIT', 'WAIT', 'BUY'): 89
- ('WAIT', 'WAIT', 'SELL'): 46
- ('WAIT', 'BUY', 'BUY'): 4
- ('WAIT', 'BUY', 'WAIT'): 1

## Top 30 (triple, final_reason) combos
- ('WAIT', 'BLOCK', 'BLOCK') -> `outside_new_york_trading_window`: 43,979
- ('WAIT', 'WAIT', 'WAIT') -> `outside_new_york_trading_window`: 30,074
- ('WAIT', 'WAIT', 'WAIT') -> `grade_below_threshold`: 18,409
- ('WAIT', 'BLOCK', 'BLOCK') -> `grade_below_threshold`: 5,930
- ('BLOCK', 'BLOCK', 'BLOCK') -> `grade_below_threshold`: 382
- ('BLOCK', 'BLOCK', 'BLOCK') -> `outside_new_york_trading_window`: 344
- ('WAIT', 'WAIT', 'BUY') -> `outside_new_york_trading_window`: 47
- ('WAIT', 'WAIT', 'BUY') -> `all_brains_unanimous_enter`: 40
- ('WAIT', 'WAIT', 'WAIT') -> `R7_unanimous_wait:WAIT`: 40
- ('WAIT', 'WAIT', 'SELL') -> `outside_new_york_trading_window`: 33
- ('WAIT', 'WAIT', 'SELL') -> `all_brains_unanimous_enter`: 13
- ('WAIT', 'BUY', 'BUY') -> `outside_new_york_trading_window`: 4
- ('WAIT', 'WAIT', 'BUY') -> `kill_flag_active`: 2
- ('WAIT', 'BUY', 'WAIT') -> `outside_new_york_trading_window`: 1
