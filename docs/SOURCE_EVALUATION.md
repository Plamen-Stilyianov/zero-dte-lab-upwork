# Source evaluation — 0DTE Greeks, option quotes and testing methodology

Reviewed November 8, 2026. This document records **why** sources are used or not used; it is not an endorsement of any vendor's data correctness, speed or suitability for live trades. Confirm licensing, entitlements and terms with providers. Source URLs are references only; no outside repository code is copied into this project.

## Greeks and market data

| Resource | What it actually provides | Decision |
|---|---|---|
| [NautilusTrader Greeks documentation](https://nautilustrader.io/docs/latest/concepts/greeks/) | Local Black–Scholes model and Greeks data types; venue-provided Greeks on supported venues; it explicitly models American options as European in the built-in BS computation | **Use for conceptual and mathematical cross-checks, not as an exchange source of truth.** SPY/QQQ are American-style; check dividend/early-exercise limitations. |
| [openalgo-portfoliogreeks](https://github.com/marketcalls/openalgo-portfoliogreeks) | OpenAlgo portfolio Greek aggregation and IV calculation, primarily for Indian option brokerage workflow. Assumptions include 0% interest in example; dynamic lots. | Useful for exposure-sign conventions but **not a source of US SPY/QQQ delta/NBBO**. |
| [option-greeks topic](https://github.com/topics/option-greeks) | Uncurated GitHub discovery page | Not a data feed or a validated options model. |
| [api-evangelist/thetadata](https://github.com/api-evangelist/thetadata) | Independent API catalog/profile for ThetaData | **Use official ThetaData docs instead for data-field semantics and endpoint functionality.** |
| [streamlet-dev/greeks](https://github.com/streamlet-dev/greeks) | Redirects to `1kbgz/greeks`, a derivatives/stream processing library | Research-only math/tooling, not a US OPRA/NBBO market source. |
| [ThetaData v3 option Greeks](https://docs.thetadata.us/Articles/Data-And-Requests/Option-Greeks.html) | Time-aligned historical Greeks on quotes/trades; reports IV solve errors; documents binomial-tree alternative for American-style options | **Primary provider candidate** for historical options quotes plus delta. Validate official export fields and `iv_error` semantics against your subscription/version. The quote is observed; the Greek is **model-derived**. |
| [ThetaData v3 historical first-order Greeks](https://thetadata.net/docs/operations/option_history_greeks_first_order.html) | Historical first-order Greeks for options at intraday intervals | Practical source for a time-aligned Greek series. The associated bid/ask quote series is still required for simulated fills. |
| [Cboe DataShop Option Quote Intervals](https://datashop.cboe.com/option-quote-intervals) | Exchange-sourced NBBO intervals for US options and optional implied vol/Greeks, 1-minute or custom | **Independent second-provider benchmark** for snapshots and Greek quality. Know the aggregation convention and delay; interval snapshot is not a tick-execution guarantee. |
| [ORATS Historical Intraday API](https://orats.com/docs/historical-intraday-api) | 1-minute historical options chain data including analytics/Greeks | Alternative vendor for strike snapshots. Their own documentation says derived underlying values are *not* real equity ETF trades, so obtain actual underlying OHLCV separately. |
| [piekstra/options-data](https://github.com/piekstra/options-data) | Parquet-backed 5-minute option bar store using Alpaca and Rust | Useful for partition/storage ideas, but its README says **Greeks not provided yet**, and five-minute bars are insufficient to establish stop-trigger fills. |
| [options-data topic](https://github.com/topics/options-data) | Uncurated repositories | Discovery only. |

**Source-of-truth principle:** OPRA-derived observed bid/ask **are** market observations; delta is a model-calculated sensitivity conditioned on actual as-of market inputs and model conventions. The bot can validate timestamps and compare two deltas, but cannot prove a vendor's Greek is ground truth. Trust ≠ unconditional correctness.

**Preferred hierarchy for the current prototype:**

1. Licensed contemporaneous option NBBO quotes, including expired contracts; contemporaneous underlying SIP quotes/1-minute bars.
2. As-of vendor delta (ThetaData candidate) calculated from synchronized observations, including exercise model, rate, dividends/forward assumptions.
3. A **separate** independent Greek estimator (Nautilus local BS as a research cross-check; American binomial model when suitable), with disagreement flag rather than numerical averaging.
4. Missing/unverifiable/stale Greek => no entry. No historical synthetic Greek substitution for market research.

## Backtesting and validation references

| Resource | What transfers to US 0DTE | What not to import blindly |
|---|---|---|
| [historical-trading-strategy-research](https://github.com/DhruvShah-Dev/historical-trading-strategy-research/blob/main/README.md) | Reproducible records, chronological splits, costs, as-of feature constraints | Its equity **daily** signals and 5-day outcomes do not prove intraday options fill behavior. |
| [walk-forward-validation topic](https://github.com/topics/walk-forward-validation?o=desc&s=stars) | Discovery of time-series methods | Repo star count is not a test of strategy robustness. |
| [quant-backtesting-validation](https://github.com/Hussain0327/quant-backtesting-validation) | Walk-forward, block bootstrap, statistical validation, deflated-Sharpe *ideas* | Its data/strategies are general equities, not certified OPRA historical 0DTE quote execution. |
| [trading-backtest-optimizer](https://github.com/akaiHuang/trading-backtest-optimizer) | Cost-sensitivity runs, rolling windows, paper/live comparison approaches | Core framework is mainly crypto/Binance/dYdX; transfer the methodology, not its market microstructure assumptions. |
| [wshobson backtesting-frameworks skill](https://github.com/wshobson/agents/blob/main/plugins/quantitative-trading/skills/backtesting-frameworks/SKILL.md) | Bias-checklist, forward splits, costs, metrics, event-driven replay | An LLM skill is advice, not independently validated code or market evidence. |

## Unfinished evidence required for actual economic edge

- Licensed historical 0DTE options **quote snapshots or ticks**, enough to include fast stop losses, for multiple years and different volatility regimes; full options universe including expired listings.
- Underlying stock bars with **bar-ending timestamp semantics**; option quotes and source Greeks aligned as-of the frame.
- Realistic bid-side exits, ask-side entries, fees, option tick sizes, market halts, delayed/missing quotes, 0DTE pin/assignment and broker liquidation policies.
- Separate locked outer holdout, expanding chronological folds with sessions omitted between segments, multiple-testing corrections for all strategies and all configurations evaluated, no optimization on final holdout.
- Paper broker execution with real fill and position reconciliation. Cross-vendor benchmark for sampled Greeks.

None of these are established simply by finding a GitHub project.
