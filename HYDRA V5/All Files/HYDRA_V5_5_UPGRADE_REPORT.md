# HYDRA V5.5 — Combined V5.2 + V5.4

Stacks two single-concern improvements: drop `volatility_normal` AND lower grade-A min to 4. This is the LAST variant in the V5.x calibration tree. If V5.5 fails, V6 redesigns rather than tunes.

## Hypothesis

Compositions of accepted single-knob variants are usually accepted; the failure mode is non-additive interaction.

## Acceptance criteria

- Net pips > BEST OF V5.2, V5.4 individually (composition must beat each component)
- Red Team 8/8
- ENTER > 300

If V5.5 doesn't beat its components, the V5.x tree is exhausted and we move to V6.

## Decision tree

```
V5.5 better than V5.4 alone? → contribute to V10
V5.5 worse than V5.4 alone but still APPROVED? → V5.4 alone goes to V10
Both rejected? → V5.x calibration tree is dead, V6 begins
```
