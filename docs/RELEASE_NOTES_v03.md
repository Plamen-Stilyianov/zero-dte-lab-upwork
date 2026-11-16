# Release notes — v0.3 Adversarial Research & Decision Provenance

Research-only add-on to ZeroDTE Lab v0.2, built entirely as original code. **No trade-order integration, external data entitlement, or statistically established market edge.**

## New features

1. `adversarial`: reproducible deterministic scenarios — baseline, 10:30–11:30 ET synthetic liquidity crisis, 11:00–11:04 synthetic option-bid gap, 0.1–1.5% per-event quote deterioration with 8% missing quote events, +1 observed bar of entry delay, and forced-exit quote disconnection. The 50–500 ms user-requested subsecond latency trial is **NOT IMPLEMENTED**, since this project's minute-bar historical tape cannot resolve it.
2. `audit-replay`: independent hash-chain JSONL decision records for generated signals, signal vetoes, virtual entries and virtual exits. A reason code now shows the broad filter or risk gate that rejected a signal. Research configuration is SHA-256 fingerprinted. The ledger covers simulated decisions only; it is not anchored, broker-signed, or protected against a privileged adversary rewriting the complete log. Linux `fcntl` lock is required.
3. `verify-ledger`: detect partial JSONL edits/truncation and broken hash/sequence links.
4. `scan-source`: AST-based heuristic review for future lagged features, centered rolling data, fit-scope, shadowed top-level definitions, hot-path loops, and time joins. Existing Vulture/Bandit/Ruff (when installed) remain the dead-code/security/style checks. No static check proves absence of leakage.
5. `bootstrap`: circular moving-block resampling of daily simulated after-cost P&L, including sessions with no trades, plus a block sign-flip exploratory null comparison. **Not CPCV, not a market-signal permutation, and not a statistically defensible proof of alpha.** Results cannot authorize live trading.
6. Exact-cent `Decimal` arithmetic for realized USD P&L and daily realized cash totals / risk budget, plus explicit test cases. Quotes and indicator calculation still use floats (appropriate for numerical modeling; different from settlement accounting).
7. Optional `entry_delay_bars` (default 1, where 1 means the original next-frame entry), bounded to 1–20 observed option-bar events. Does not simulate 50–500 milliseconds unless future event data resolve that frequency.

## Adversarial warnings

- Stress changing option quotes without consistently repricing delta is a **fault injection**, not an internally coherent sample for data-driven forecasting. Never train on perturbed quote data.
- Complete intraday drawdown requires mark-to-market position equity and tick/quote path; current closed-trade/session P&L is insufficient.
- The $0.40 premium stop is a trigger, not a guarantee of a $40 maximum loss on a 100-share option contract.
- If a market disconnect prevents a forced exit, the simulator sets `complete_tape=false`. Such a scenario has unresolved exposure and must not be graded by its apparent P&L alone.
- The block sign-flip null assumes approximately symmetric block sums; short samples and dependence undermine p-values. Every change based on that evaluation consumes a research trial. Keep a fresh untouched test period and record the number of candidate strategies tested before calculating adjusted significance measures like a Deflated Sharpe Ratio.
- TradeMemory's public Alpaca proxy presently **refuses options orders**, so we do not connect it to the 0DTE order path.

## Not implemented

Licensed SPY/QQQ options tick-by-tick history; subsecond order latency and feed-order simulation; L2 order-book queue/impact models; event labels and purged/combinatorial cross-validation; leakage-provable ML pipeline; market-wide correlated gamma shock calibrated from real historical data; external ledger anchoring; automatic patch deployment; real broker reconciliation. Any of these would be distinct engineering projects.

## Tests

Run `python -m pytest -q` and `python scripts/audit.py`. A passing unit test suite demonstrates regression coverage, not predictive trading performance. The synthetic 12-day tape is intentionally **not representative** of real market returns.
