# ZeroDTE Lab v0.6 — CPCV and Romano–Wolf Statistical Validation

New in v0.6: leak-checked combinatorial purged CV **split planning** and
studentized Romano–Wolf **stepdown** correction for strategy-family daily
return tests. Both are research-only and require honest, point-in-time data
and complete records of all tested strategy variants.

Quick start (after `pip install -e .`):

```bash
python scripts/make_cpcv_demo_labels.py
zerodte cpcv-plan --labels-csv data/SYNTHETIC_cpcv_labels.csv --folds 6 --test-folds 2 --embargo 2
zerodte romano-wolf --returns-csv data/SYNTHETIC_statistical_panel.csv --iterations 1999
python -m pytest -q
```

**All included example data is synthetic.** These diagnostics cannot
establish live profitability and do not authorize live execution. CPCV is not
a forward-only simulation, and Romano–Wolf requires a complete registered
hypothesis family. See [the detailed v0.6 methods and limitations](docs/CPCV_ROMANO_WOLF_v06.md).

---

# ZeroDTE Lab v0.5 — Option Momentum Research & Paper Simulator

## New in v0.5: statistical validity and trial-family inference

Read [Statistical Inference v0.5](docs/STATISTICAL_INFERENCE_v05.md) and
[Release Notes v0.5](docs/RELEASE_NOTES_v05.md). The new `statistical-audit`
command evaluates a complete, aligned **session-level percentage-return panel**
using stationary/circular block resampling, Holm/BH/Bonferroni p-value adjustments,
exploratory joint max-T, advisory PSR/DSR, and uncertainty/drawdown intervals.
It DOES NOT claim an edge or enable trading. A new `export-return-panel` converts
complete backtest trade reports into fixed-capital daily return panels (including
zero-trade sessions); source market-data and trial provenance are unverified.

```bash
# Entirely fictional fixture, NOT a real strategy performance result
python scripts/make_stat_demo.py
zerodte statistical-audit --returns-csv data/SYNTHETIC_statistical_panel.csv \
  --selected delta_075 --declared-trials 20 --iterations 1000 \
  --out results/v05_synthetic_statistics.json
```

## New in v0.4: free-data feasibility + locally modeled Greeks

**Read [Free Data & Greeks v0.4](docs/FREE_DATA_AND_GREEKS_v04.md) before evaluating any results.**
The project now includes a bounded public DoltHub schema inspector, an optional
**research-only** Black-Scholes Greeks enrichment command, and a QuantConnect
**free-cloud, read-only** 0DTE data observer example (`examples/quantconnect/`).

Critical correction: DoltHub `option_chain.vol` reportedly denotes **implied
volatility**, not trading volume. Its daily, irregular and filtered snapshots
cannot reproduce your 2x volume / 0DTE intraday fill simulation. The new tools
**do not convert a daily option snapshot into a trusted intraday quote**. Free
QuantConnect Cloud supports minute options backtests, not subsecond historical
options replay, and its proprietary data cannot be exported to your Droplet.

```bash
zerodte inspect-dolthub --query chain_schema --out results/free_data/chain_schema.json
zerodte enrich-greeks-research --input data/your_intraday_quotes.csv \
  --out results/free_data/estimated_greeks.csv
```

**These tools were tested offline with deterministic fixtures, not against a
live DoltHub HTTP response or QuantConnect backtest in this environment.**


**Status: research prototype, NOT a live automated trading system.**

A runnable Python 3.14+ project for studying long 0DTE calls and puts with 2× underlying minute-volume triggers, a minimum absolute delta of 0.75, and a 40-cent option-premium stop. Supports bid/ask historical replay, DuckDB/Parquet streaming, a frozen chronological walk-forward validation, a local paper account simulator, a 24/7 **read-only** Alpaca market-data watcher for DigitalOcean, and scheduled static/LLM code audits. **No Alpaca order creation, order modification, or live brokerage trades are implemented.**

This is an engineering starting point. **No strategy profitability, positive edge, low loss frequency, or fixed maximum loss is established.**

## New in v0.3 — adversarial fault injection and auditable research decisions

v0.3 extends v0.2; it is still a **research/paper-simulation system**. It does **not** trade on a broker account or autonomously edit its risk settings.

- Deterministic synthetic execution fault scenarios include quote outages, liquidity crises, option-bid price gaps, and one additional *observed frame* of entry delay. Do not confuse this with the requested **50–500 ms latency injection**, which requires subsecond options quote events unavailable in the bundled 1-minute tape.
- An original append-only, SHA-256 chained, locally verifiable research decision ledger records signals, broad rejection reason codes, virtual entries/exits, and configuration fingerprints. This is tamper-evident against partial edits, **not tamper-proof or externally anchored**. Available on Linux.
- A conservative AST code scanner searches for potential leakage, fitted-transform scope, centered rolling averages, and duplicate definitions. Existing `scripts/audit.py` also offers Ruff, Bandit, Vulture and an **opt-in** LLM code review. Static warnings require human investigation.
- Session-block bootstrap intervals, exploratory block-sign-flip null tests, drawdown and recovery diagnostics now exist. **These are not CPCV or full target-permutation tests**; they cannot establish alpha or pass a deployment gate.
- Daily realized P&L and risk budget now use decimal-cent accounting; trade rejection is assigned a broad causal reason code.

From the unpacked project root (run `pip install -e '.[all]'` first), to run a demo **only using the supplied, deliberately optimistic synthetic data**, use:

```bash
zerodte scan-source --root src/zerodte --out results/source_audit.json
zerodte adversarial --data data/SYNTHETIC_12DAY_validation_demo.csv --config config.synthetic.json --out results/adversarial
zerodte audit-replay --data data/SYNTHETIC_demo.csv --config config.synthetic.json --ledger results/replay/decisions.jsonl --out results/replay
zerodte verify-ledger --ledger results/replay/decisions.jsonl
zerodte bootstrap --data data/SYNTHETIC_12DAY_validation_demo.csv --config config.synthetic.json --block 3 --iterations 1000 --out results/bootstrap.json
python scripts/audit.py
```

**Synthetic-only results are NOT evidence of profitability.** In real research runs, retain `config.example.json` (trusted Greek source) and acquire licensed point-in-time bid/ask/Greek data. The 0.75 delta, 2× relative volume, 0DTE and $0.40 premium stop entry rules are preserved. See `docs/RELEASE_NOTES_v03.md` and `docs/NEW_REPOSITORY_EVALUATION_v03.md` for precise omissions and model-risk limitations.

## New in v0.2 — verified Greeks timing, vendor imports and repeatable validation

**Important:** Trusted Greek provenance is the default. Source labels alone do NOT prove vendor correctness or actual feed entitlement; they prevent silent use of synthetic/local model deltas as though they were historical vendor observations. The user must obtain a licensed US options quote/Greek feed separately, provide explicit as-of source fields, and verify its exercise-model assumptions. **No licensed history, broker execution, or Droplet deployment is included.**

- `greek_provider` and `delta_ts` are now **required** for all `provided` delta imports. Supported trusted labels: `thetadata`, `cboe`, `cboe_datashop`, `orats`, `broker_vendor`. Unknown/synthetic/local models cannot trade in trusted mode. Old v0.1 market tapes without source-time columns require normalization before analysis.
- Greek timestamps must be contemporaneous with the quote (default at most 30 seconds old; no future timestamps). An optional **independent** `reference_delta`, `reference_delta_ts`, `reference_provider` are compared with the primary delta; disagreement greater than 0.08 vetoes entry.
- `crosscheck-nautilus` optionally supplies a separate NautilusTrader local model delta (requires independently installed dependency; European-model limitations documented). `merge-tape` streams completed stock minute bars + licensed vendor option data into one time-aligned canonical tape, with explicit field mappings. `audit-tape` produces a structured provenance/timing report.
- `rolling` performs expanding-window train/validate/test folds with complete-session embargo, while `stress` replays adverse per-side transaction costs and shows matched-trade sensitivity separately.
- Additional reporting distinguishes **how often trades lose**, **mean winner/loser**, **worst trade**, and stop exits with true gap slippage beyond worst-case stop + fees (`stop_exits_with_gap_slippage`, alongside legacy `stop_exits_losing_more_than_40usd`). The requested rule is **delta >= 0.75**, with no artificial 0.93 cap in v0.2.
- The v0.2 release originally passed 40 deterministic tests. The current v0.3 package passes **55 tests and 18 subtests** locally, including provenance, ledger tampering, latency-bar delay, decimal accounting, and session bootstrap reproducibility. Optional Ruff/Vulture/Bandit audit executables are not installed in this runtime and have not been executed here.

Detailed guides: [source review](docs/SOURCE_EVALUATION.md), [input contract](docs/DATA_CONTRACT_v02.md), [validation plan](docs/VALIDATION_PLAN.md). No external GitHub code is copied into this project.

## Quick start (no API keys needed)

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[all]'
python scripts/make_demo.py
zerodte backtest --data data/SYNTHETIC_demo.csv --config config.synthetic.json --out results/demo
python scripts/audit.py
```

The generated file is fictional and was intentionally designed to exercise long trend behavior. Its P&L is **meaningless for real markets**. Results appear in `results/demo/summary.json`, `trades.csv`, and `events.log`.

For historical data with a vendor-provided, point-in-time delta:

```bash
zerodte backtest --data /path/to/dated_0dte_quotes.parquet \
  --delta-source provided --config config.example.json --out results/real_backtest
```

If no point-in-time delta is available, use `--delta-source estimated --config config.synthetic.json` for **experimental research only**. It estimates IV/delta from quoted mid via intraday Black–Scholes. These estimates are unstable close to expiration, may be unsuitable for ETF American-style options and skip contracts when a defensible calculation is impossible.

### Train / validate / test in strict time order

Choose chronological cutoffs that correspond to your actual historical dataset. Use enough sessions per split; the five-day synthetic demo is deliberately insufficient.

```bash
zerodte walk-forward --data /path/to/0dte_quotes.parquet \
  --train-end 2025-12-31 --validation-end 2026-06-30 \
  --out results/holdout
```

The system trains a **simple interpretable regime gate** on historical completed trades (not an autonomous model changing code). The allowed trade regimes are frozen before validation and untouched testing. It blocks unproven regimes; it never relaxes the 2× volume, delta, 40-cent stop or size limits. It does not automatically ship anything to a live account. Unknown regimes are vetoed in frozen validation. More sophisticated Qlib/ML models belong in an isolated future research module after substantially more data and reliable market microstructure features are available.

## Exact strategy (starting hypotheses, not recommendations)

1. **Underlying trigger:** trade only after the minute bar closes, with volume at least 2× the mean of **20 previous completed 1-minute underlying bars** (the current bar never enters its own baseline).
2. **Trend confirmation:** bullish = EMA(9) > EMA(21), price above cumulative session VWAP, and close above the highs of the previous 10 bars. Bearish mirrors those conditions; prefer long calls in bullish regimes and long puts in bearish regimes. These are reference filters that need real-world validation and may miss pullbacks.
3. **Options filter:** same-day expiry, standard unadjusted 100-share multiplier, volume at least 10 contracts observed in the option market, bid/ask spread <= $0.12, delta absolute value at least 0.75 (at most 1.0), real quote not stale, correct call/put delta sign. Choose the eligible delta closest to 0.75.
4. **Entry:** signal determined from a *completed* minute cannot enter until next recorded quote/frame. Buy at ask + $0.02 simulated adverse slippage. The engine does not pretend fills happen at midpoint or at the breakout candle's past price.
5. **Hard stop trigger:** sell when observed **bid** falls to entry premium - $0.40. Actual simulated exit is bid - $0.02 slippage; a gap can produce a loss **larger than $40 per contract**, even before fees.
6. **Winners:** at +$0.55 observed favorable movement, tighten stop to about breakeven; at +$0.65, trail best observed bid by $0.45. Stops never widen. There is no fixed take-profit cap.
7. **Time limits:** new entries from 9:50 to 15:00 ET; simulate forced sale at 15:20 ET, ahead of a broker's 15:30 expiration-day risk window. On early-close sessions, the live data watcher moves simulated closing earlier using the actual market clock. **A missing quote creates an incomplete tape, not a fabricated execution.**
8. **Exposure defaults:** $25,000 fictional balance, one contract, one position, three entries per day, $150 realized daily stop, 0.2% of capital risk budget per trade, 10% maximum premium notional, estimated $0.65/side commission. Note: a stop is not a fixed loss cap; actual real-world downside includes the entire long premium plus fees.
9. **Learning:** distinguish `C:standard`, `C:surge`, `P:standard`, `P:surge`. After at least 30 trades of a regime closed **before the current trading day**, require a positive conservative historical per-contract expectancy estimate, or the regime is disabled. This is a conservative filter, not evidence that the strategy improves performance.

**Important interpretation:** "2× volume" is assumed to mean **the underlying's most recent 1-minute bar versus its preceding 20 bars**. Contract volume has a separate liquidity requirement; changing the definition of 2× volume is a new research hypothesis and needs its own out-of-sample test. Delta >=0.75 also makes the options more in-the-money and often more expensive than low-delta lottery-ticket contracts.

## Historical data contract

The input CSV, Parquet, or folder of Parquet parts needs these columns:

| Column | Required representation |
|---|---|
| `ts` | Offset-aware UTC ISO 8601 **minute observation / completed bar time** |
| `underlying` | `SPY`, `QQQ`, etc. |
| `close`, `high`, `low`, `volume` | Historical underlying minute bar |
| `option_symbol` | Full OCC-style contract identifier, including **expired** symbols |
| `expiry` | Option expiration date (YYYY-MM-DD) |
| `right` | `C` or `P` |
| `strike` | Decimal strike in dollars |
| `bid`, `ask` | Contemporaneous *executable-side* option market quote, valid NBBO where available |
| `option_volume` | Observed option traded volume up to this timestamp, not total future-day volume |
| `quote_ts` | UTC timestamp when bid/ask were observed, never later than `ts` in historical replay |
| `delta` | Required vendor model-derived delta when `--delta-source provided` |
| `greek_provider`, `delta_ts` | **Required** source label and source timestamp for vendor provided delta; model Greeks cannot silently masquerade as observed vendor data |
| `reference_delta`, `reference_delta_ts`, `reference_provider` | Optional independently computed as-of delta; disagreement triggers veto |

Keep input **sorted by UTC `ts`, then by underlying**. One row per option contract per minute; underlying bar fields repeat across that minute's contracts. No reconstructed today's Greeks for yesterday, no hindsight option selection, no daily settlement prices for minute fills. Invalid quotes, stale quotes, missing delta or adjusted contract multipliers must veto entry.

**Historical depth:** Alpaca reports historical options since February 2024; free indicative prices are **not OPRA execution quotes**. Paid OPRA access or a licensed vendor with expired option series, point-in-time bid/ask and preferably Greeks is needed for credible intraday evaluation. The backtester streams CSV incrementally; the optional DuckDB path can query a Parquet partition directory while spilling sorting to disk. Large datasets still require adequate storage/CPU and careful vendor coverage audits. `results` contain aggregate reports; `.parquet` rows are not bundled with this project.

## 24/7 DigitalOcean deployment (READ-ONLY market watcher)

The process stays up around the clock, **but US listed options trade only during their market session**. It performs **virtual** entries and exits in a local in-memory account, writes its input tape for current-day restart replay, and never calls broker order endpoints. If OPRA/SIP subscriptions or API keys are missing, it fails closed; it does **not** silently switch to 15-minute delayed indicative quotes. **v0.2 additionally defaults to `greek_policy=trusted`: the Alpaca read-only watcher currently computes a local experimental Black–Scholes delta and thus cannot open even virtual entries under the production research config.** That is deliberate. A validated and timestamped licensed historical/live Greeks adapter needs to be connected before using `trusted` mode for trading-signal simulation. Do not switch to `experimental` to claim that modeled Greeks were vendor observations.

1. Provision a basic Ubuntu Droplet with Docker Engine and Compose plugin; use an SSH key, updates, and a minimal firewall. Do not expose any application port.
2. Copy this project to the Droplet; install Compose if needed.
3. Obtain **Alpaca paper credentials plus OPRA/SIP market-data entitlements**. The bot cannot infer or invent credentials. A paper brokerage account alone may not grant the necessary feeds.
4. Copy `.env.example` to `.env` and fill `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` (and leave `ALPACA_OPTION_FEED=opra`, `ALPACA_STOCK_FEED=sip`). Never commit `.env` or paste tokens into chats.
5. Change ownership of bind-mount directories and start:

```bash
mkdir -p data results
sudo chown -R 10001:10001 data results
docker compose build
docker compose up -d
# Examine errors and simulation log; NO real/paper broker orders are sent.
docker compose logs -f --tail=100 bot
```

The watcher records `data/paper_sim_YYYY-MM-DD.jsonl` and reports in `results/paper_sim_YYYY-MM-DD/`. Its 10-second polling and option-chain snapshot cadence **are not sufficient for a production 0DTE order-management system**; a real execution system needs streaming order-book updates, fill reconciliation, broker-aware protection, market-disconnect recovery, kill-switches, notifications, holidays/half-day handling and external paper-account verification before ever considering funded trades.

## Adversarial AI auditor: find bugs, redundant code and leakage

```bash
# Local lint, tests, compiled syntax, vulture dead-code scan, Bandit security scan
python scripts/audit.py
# Opt-in external LLM code review: only source and tests; NO .env, data or tokens
export OPENAI_API_KEY='(use environment/secret manager)'
python scripts/audit.py --llm
```

The read-only LLM is instructed to seek future-data leakage, options stop/execution errors, backtest overfitting, logic holes, stale quote and DST handling, bugs, redundant/dead code and missing tests. Output: `results/audit/latest.json`. **It never changes trading code, risk rules or deployments.** Audit scripts may incur LLM usage costs. Audit is an advisory, not a guarantee of security. See `tests/test_core.py` for reproducible failure cases.

For a nightly audit on the Droplet (host cron), install audit dependencies (built into the container image) and run a one-shot check in the image:

```bash
# One-time; the application container continues on its own
# Replace $PROJECT_DIR with your actual deployment path.
0 2 * * 2-6 cd /path/to/zero-dte-lab && /usr/bin/docker compose run --rm --no-deps bot python scripts/audit.py
```

That crontab expression is an example that executes 02:00 **server-local time** Tuesday–Saturday (after the US market's prior trading day); change the timezone/cadence for the host. On weekends and market holidays the watcher stays idle, as appropriate. An opt-in AI audit is a separate operation and not enabled in cron by default.

## Architecture

```text
                  licensed, timestamped options quote data
                                 |
                 +---------------+-------------------+
                 |                                   |
          Historical Parquet/CSV                 Alpaca OPRA + SIP
                 |                                   |
       sorted event-by-event replay            read-only watcher
                 |                                   |
                 +----------- Market Frames --------+
                                     |
                    2x volume + EMA9/EMA21 + VWAP
                                     |
                             next-frame signal
                                     |
                  delta, expiry, NBBO, liquidity checks
                                     |
                   account & daily-loss hard limits
                                     |
                    virtual fill at ask / bid - costs
                                     |
                          option premium stop
                                     |
                       trailing and early exit
                                     |
                    P&L, trade log, regime analysis
                                     |
                   research, frozen holdout evaluation
                                     |
                  optional LLM/static code auditor
                     (READ-ONLY; never orders)
```

### Relationship to the supplied repositories

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents): optional *nightly research* framework. LLMs are too slow/non-deterministic to control a 0DTE stop or order. Apache-2.0 repo. No external repo source has been copied into this project.
- [charliedream1/ai_quant_trade](https://github.com/charliedream1/ai_quant_trade): broad educational reference for quant models and trading platforms; not imported into the MVP.
- [leoncuhk/awesome-quant-ai](https://github.com/leoncuhk/awesome-quant-ai): reading and experiment catalog, not a runtime dependency.
- [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib): potential multi-strategy risk contribution/CVaR research. Not required for one-contract prototype. BSD-3-Clause.
- [microsoft/qlib](https://github.com/microsoft/qlib): future offline feature and model research, not needed in hot path. MIT. Check release-specific artifact loading security changes before storing/loading external models.
- [Reddit trend-following discussion](https://www.reddit.com/r/Daytrading/s/TBVq79etkS): subjective inspiration, **not evidence of returns**.

The MVP contains **original code** and does not bundle, modify or redistribute these repositories.

## Required development before funded trading

**Do not fund or live-enable this prototype.** A subsequent professional execution layer must at least implement audited broker-side paper OMS, position/restart reconciliation, order idempotency, exchange halts, partial-fill logic, no-trade/restrict orders, ask/bid depth, intra-minute stop monitoring, real account exposure checks, emergency liquidation, alerts with human escalation, clearing/corporate actions and operational runbooks. An external review of licensing and regulatory obligations is also sensible if the service operates beyond personal use.

Evaluate out-of-sample by month, long and short trend, volatility regime, P&L after realistic fees and spread, 95th/99th-percentile losing trades, maximum intraday drawdown, no-quote frequency, price-gap stops, model drift, and performance of fixed rules against the adaptive veto. The confidence calculation here is simplistic and must not be interpreted as rigorous predictive statistics. Limit any future AI feature to *suggesting reviewed experiments*; it must never autonomously lower risk guardrails, rewrite deployed code or make unapproved trades.

## Primary documentation

- [Alpaca historical option data](https://docs.alpaca.markets/us/docs/historical-option-data) — paid OPRA vs free indicative, availability since Feb 2024.
- [Alpaca chain snapshots](https://docs.alpaca.markets/us/reference/optionchain) — quotes/Greeks, pagination.
- [Alpaca Greeks FAQ](https://docs.alpaca.markets/us/docs/market-data-faq) — Greeks missing for 0DTE.
- [Alpaca options trading](https://docs.alpaca.markets/us/docs/options-trading-overview) — 15:30 ET risk management at expiration.
- [FINRA 0DTE risk explanation](https://syndication.finra.org/content/zeroing-options-trading-strategy-0dte).
- [OCC contract specifications](https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications) — standard 100-share contract multiplier.

Educational/research software. Option trading can produce rapid substantial losses. No investment or return guarantee.
