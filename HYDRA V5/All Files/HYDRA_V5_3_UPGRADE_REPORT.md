# HYDRA V5.3 — Drop `no_liquidity_sweep` Evidence Flag

**Theme:** Single-knob calibration. Drop a different evidence flag.

## 1. What was weak

The `no_liquidity_sweep` flag excludes setups right after a stop hunt. But Wyckoff shake-out / spring patterns are exactly when high-quality moves originate. Excluding them filters out potentially the best setups.

## 2. Hypothesis

Dropping `no_liquidity_sweep` will increase ENTER count and POSSIBLY improve win rate (post-sweep moves often have momentum).

## 3. Code

`replay/variants/v5_3_drop_no_liquidity_sweep.py`. Same monkey-patch pattern as V5.2.

## 4. Decision criteria

**APPROVED if:** ENTER > 53 AND win rate ≥ 30 % AND no per-pair regression AND Red Team 8/8. Bonus credit if win rate UP vs V5.0.

**REJECTED if:** post-sweep cycles continue extending (i.e. SL hit before TP) more than 60 % of new trades.

## 5. Comparison table

(filled at runtime by the variant runner + war room)

## 6. Risk

Trading right after a sweep can mean trading INTO the sweep's continuation. If the sweep didn't reverse, we're early. The variant runner reports per-bar timing post-sweep so we can see this.

## 7. Next

If APPROVED → flag is structurally costing us trades; contributes to V10.
If REJECTED → the flag IS necessary; keep it.
