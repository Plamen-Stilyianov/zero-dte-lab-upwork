# ZeroDTE Lab v0.5 — Statistical significance and multiple-trial accounting

**Research only. Not a live deployment gate, a prediction of future returns, or an assertion of alpha.**

## Why this module exists

The v0.3 bootstrap operated on a single chronological session-level P&L series and did **not** account for the search that led to choosing the final strategy. v0.5 adds a **complete, aligned daily net return panel** of all tried strategy variants; stationary and circular moving-block bootstrap; simultaneous multiple-testing summaries; and advisory Probabilistic/Deflated Sharpe Ratio diagnostics. The v0.3 bootstrap remains available for backwards-compatible P&L analysis.

Three user-supplied methodological references were reviewed:

- [ITheClixs/crypto-return-predictability](https://github.com/ITheClixs/crypto-return-predictability) — purged/embargoed research, stationary bootstrap, Holm, BH and DSR. Its findings illustrate how nominal results disappear after costs and multiple-testing correction. **We do not import its return series or its code.**
- [terrylica/rangebar-py validity audit](https://github.com/terrylica/rangebar-py/blob/main/STATISTICAL_VALIDITY_AUDIT.md) — adversarial checklist of sample dependence and data snooping. Case-specific numerical conclusions are not adopted as general thresholds.
- [HimanshuJ16/Algo-Trading-Skills Monte Carlo standards](https://github.com/HimanshuJ16/Algo-Trading-Skills/blob/main/skills/monte-carlo-strategy-robustness-testing/references/standards.md) — separate order permutations, sampling variation, and execution noise. Its own standard file notes stationary block bootstrap is *not* implemented there.

The primary methodological sources are Politis & Romano (1994), *The Stationary Bootstrap*, Journal of the American Statistical Association; Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure*; Benjamini & Hochberg (1995), *Controlling the False Discovery Rate*; and Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*.

## Install

From the extracted folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m pytest -q
```

The significance module uses only the Python standard library. No external strategy repository code is copied.

## Step 1 — Prepare an aligned, complete daily-return matrix

CSV format in **long form**:

```csv
session,strategy_id,daily_return
2025-01-02,baseline,0.001
2025-01-02,delta075,-0.003
2025-01-03,baseline,0.0
2025-01-03,delta075,0.005
```

- Each row is a full trading *session*, not a fill or 1-minute bar.
- `daily_return` is a *fraction of a consistent capital base*, not dollars: `0.01` means +1% net.
- Every strategy variant must appear for **every** common session, including days with no trades (0.0).
- Do not backfill/fill missing variants, remove losing sessions, mix scales, or silently ignore unprofitable variants.
- Input must reflect **bid/ask spreads, commissions, slippage and any other plausible trading costs** before inference.
- All strategy trials (including failed settings, rules, symbols, delta/volume thresholds and AI-generated versions) must be disclosed. `--declared-trials` can penalize unseen trial count but CANNOT reconstruct unpublished returns, so it is not a substitute for a complete registry.
- Select the evaluation candidate on the **training/validation** data, before the final holdout. An analysis performed on the sample used to select the winner is only exploratory, irrespective of its p-value.

Export from the project's own *complete* historical trade reports using the source market tape for the session calendar:

```bash
zerodte export-return-panel \
  --tape data/research/verified_tape.parquet \
  --config config.example.json \
  --variant base=results/experiments/base/trades.csv \
  --variant delta075=results/experiments/delta075/trades.csv \
  --capital 25000 \
  --out results/research_family.csv
```

The exporter refuses incomplete summary reports, overnight trades, mismatched trade counts/P&L, or missing days on the tape. It converts *realized session P&L divided by a constant capital base*; it is not a sophisticated broker NAV reconstruction. In this 0DTE simulator positions should always close same day. It does not verify external market-data licenses or held-out provenance. A missing session from the source tape remains a concern: compare with an independent exchange calendar.

## Step 2 — Run stationary bootstrap and family-level inference

```bash
zerodte statistical-audit \
  --returns-csv results/research_family.csv \
  --selected delta075 \
  --method stationary \
  --block-length 6 \
  --iterations 5000 \
  --declared-trials 20 \
  --out results/real_statistical_audit.json
```

Default block length is `max(2, round(n_sessions^(1/3)))`, a heuristic and **not an estimated optimal block size**. Explicitly test e.g. 3, 6, 12 and 20 sessions. Use `--method circular` for fixed-block sensitivity. Experiment counts must be pre-registered or reconstructed from an immutable research log, not fabricated after seeing p-values.

### Outputs

Each variant includes:

- Original mean daily net return, naive annualized Sharpe (252 trading sessions/year), and historical compounded closed-session max drawdown.
- Bootstrap percentile interval for mean daily net return and a corresponding **descriptive** interval for annualized Sharpe. Neither is a guarantee of future performance.
- 95th-percentile maximum drawdown of resampled paths (a **stress scenario distribution**, NOT a population confidence interval).
- One-sided centered block-bootstrap p-value for whether mean daily net return exceeds zero; relies on weak stationarity and meaningful bootstrap centering.
- Bonferroni, Holm family-wise error (FWER) and Benjamini–Hochberg false-discovery (FDR) adjusted p-values. Holm is valid with arbitrary dependence **if** each original p-value is valid; BH needs stronger dependence conditions.
- Synchronously resampled joint max-T **exploratory** FWER result, designed to account for co-movement of related variants. This is not formal stepdown Romano–Wolf or CPCV.
- Classic PSR / DSR **advisory** outputs at the raw daily scale. DSR does **not** merely subtract a fixed haircut from Sharpe. It estimates a probability of exceeding an expected best-null Sharpe across multiple tries. The classic approximation is questionable under serial dependence and overlapping/redundant models, and no `effective independent trials` correction is established.

A complete report always states:

```json
"can_promote_to_live": false,
"data_provenance_verified": false,
"model_selection_history_verified": false
```

**Even a strong positive confidence bound does not switch any trading capabilities on.**

## Step 3 — Demonstrate the mechanics with FICTIONAL data

```bash
python scripts/make_stat_demo.py
zerodte statistical-audit \
  --returns-csv data/SYNTHETIC_statistical_panel.csv \
  --selected delta_075 \
  --declared-trials 20 \
  --iterations 1000 \
  --out results/v05_synthetic_statistics.json
```

This data is deliberately manufactured, using shared AR(1) shocks, multiple variants, and zero-return days. Results from this example **must never be described as historical win rate, live risk, or realized alpha**.

## Statistical pitfalls and unimplemented institutional methods

1. Stationarity is a substantial assumption: 0DTE outcomes can shift with rates, gamma, news and volatility. Slice and separately evaluate regimes, but count every new slice as a research trial. A block bootstrap cannot conjure crisis events absent from the sample.
2. The `n^(1/3)` heuristic can be wrong when autocorrelation persists longer. Check ACF and stability across multiple block lengths. Selection of block length based on the winning p-value is itself data snooping.
3. Historical option quotes and Greeks can contain errors even if time-aligned; backtesting 0DTE at minute resolution can miss a stop-crossing and severely understate losses.
4. **Not implemented:** combinatorial purged cross-validation (CPCV), Hansen's SPA / White's Reality Check, block-permuted *signal/outcome* alignment tests, formal Romano–Wolf stepdown, Newey–West HAC t-tests, independent vendor-reconciled live execution.
5. Multiple-testing corrections on daily strategy returns are not a substitute for Clark–West forecast-loss comparisons between a nested forecasting model and its benchmark. Clark–West is a different test, and we did not apply it to option-trading P&L.
6. Converting a trade P&L series into a session return series requires a consistent capital convention. Our exporter divides by the provided fixed account capital. It is not a high-fidelity daily NAV history accounting for cashflows, options mark-to-market, or leverage changes.
7. Small samples, zero variance and too few replications lead to very unstable inference. Fewer than 120 sessions is flagged. The module refuses panels shorter than 30 sessions and sets p-values to 1.0 for zero-variance variants rather than claiming spurious certainty.
8. Choosing the best strategy after inspecting the final holdout contaminates it. A fresh holdout or genuinely forward-generated paper-trading period is necessary if the prior holdout was touched.

## Final gate

This component is a **diagnostic research gate only**. Data provenance, broker execution controls, legal/licensing checks, and independent human sign-off remain unsatisfied and are not automated by this version.
