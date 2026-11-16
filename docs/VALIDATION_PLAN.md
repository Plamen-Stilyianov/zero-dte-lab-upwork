# Validation plan and acceptance gates

An economic edge must survive every stage, not just a green backtest chart.

## Stage A — market data QA

**Block trading whenever:** no license/subscription, unverified volume timestamp, missing expiry, nonstandard multiplier, crossed/invalid quotes, `quote_ts` in the future, stale quotes, unknown Greek source, stale/as-of mismatched delta, or inconsistent independent delta.

Use `zerodte audit-tape --data ...` first. It detects *structural/timestamp* errors only. A vendor can have stale or incorrect data even when its label and timestamps are present; cross-vendor sampling and market-size checks are required separately.

## Stage B — deterministic backtest

Use the exact entry signal after the closing 1-minute bar and the next recorded quote for entry. Long options buy at observed ask plus adverse slippage and close at observed bid minus adverse slippage. Commissions included. No hindsight bar-high fills or mid fills; incomplete forced exits invalidate the tape.

## Stage C — expanding rolling walk-forward

```bash
zerodte rolling --data data/research/tape.parquet \
  --train-sessions 120 --validation-sessions 30 --test-sessions 30 \
  --step-sessions 30 --embargo-sessions 1 --max-folds 8 \
  --out results/rolling
```

`train` = older sessions. `validation` = later untouched sessions used to evaluate a *frozen* gate fit in train. `test` = still later untouched sessions. There is a complete-session embargo between segments. Test results are for post-hoc assessment **only**. Do not tune on tests or pick only profitable folds. The rolling engine replays the dataset once to identify sessions, then once for each fold, storing one fold at a time; memory remains controlled but disk/network IO rises with fold count. The final dataset and chosen parameters must also face one separately reserved outer holdout.

## Stage D — explicit adverse execution assumptions

```bash
zerodte stress --data data/research/tape.parquet \
  --cents-per-side 0.02,0.05,0.10,0.20 --out results/stress
```

The stress report shows two different measures. `risk_gated_replay_*` is a fresh deterministic replay with new costs, so risk sizing can veto trades. `conditional_same_trades_pnl_usd` re-prices the original trades assuming higher fill slippage, holding their trade sequence fixed, and **cannot** predict fill probability or stop paths. Both are limitations, not guarantees.

## Stage E — statistical and operational review

- Report separately per symbol, month, hour, bull/bear/flat market, implied/realized volatility regime, high-volatility news windows, and spread/liquidity conditions.
- Report net profit **after** bid/ask and fees; drawdown, payoff ratio (mean winner / mean loser), worst losing trade, frequency of losses, loss clustering, skewness, stop-gap overshoot and days without fills.
- Confidence bounds should be blocked by **trading session**, not IID option ticks. Include *every* hyperparameter/configuration tested in any multiple-testing correction. A statistically positive result is not a guarantee of a repeatable edge.
- Run a paper-account order management service with real order acknowledgements/partial fills, reconciled positions, external kill switch, alerts, outages, holidays, and restarts. The delivered app has **no** brokerage order execution.
- Do not auto-publish or auto-deploy strategies. A written review and an entirely fresh holdout are mandatory for any strategy rule change proposed by AI.

**Failure policy:** No edge after costs; too few completed trades; stale/partial source; or unstable fold results => NO-GO. A system that never trades because risk limits reject all candidates is **not** proof of safety or effectiveness.
