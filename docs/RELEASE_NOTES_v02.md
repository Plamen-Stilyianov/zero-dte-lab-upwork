# ZeroDTE Lab v0.2 — Release notes (2026-11-08)

## Delivered in this version

- Added as-of source timestamp and provider for every historical vendor delta, strict Greek age/skew rejection and optional *separately sourced* reference comparison.
- Default production research config rejects synthetic/local-model Greeks. `config.synthetic.json` is explicitly labelled experimental for sample runs only.
- Added vendor-CSV + underlying-minute CSV streaming importer, a structural/audit report, and explicit option source field mapping. No vendor credentials or data subscriptions are bundled.
- Added optional `nautilus_trader` low-level reference solver and CSV cross-check command; this is European Black–Scholes and is **not** a verified source of market truth for SPY/QQQ.
- Added expanding rolling forward validation with 0–10 purged sessions between train, validation and test windows; added pessimistic slippage scenarios and conditional same-trade sensitivity.
- Expanded P&L reporting to show loss frequency, size of winners/losers, and outsized stop executions; expanded unit/adversarial test coverage.

## Verification performed in this environment

- Python 3.13 + `PYTHONPATH=src python -m unittest discover -s tests -q`: **40 tests passed**.
- `PYTHONPATH=src python -m pytest -q`: **40 passed** (plus 18 parameterized subtests).
- `python -m compileall -q src scripts tests`: passed.
- Five-session entirely synthetic demo backtest: completed. **Financial results are intentionally not presented as historical returns.**
- Twelve-session entirely synthetic rolling example: two folds completed; neither allowed any new test trades because the sample had insufficient completed trades to qualify a model gate. This is correct no-go behavior, **not** evidence of outperformance.
- Trusted-mode data audit rejected every synthetic delta in that sample.
- `scripts/audit.py` ran stdlib tests and compile checks; Ruff/Vulture/Bandit were unavailable in this environment and have **not** been claimed as completed.
- NautilusTrader integration was unit-tested against a mocked public API signature; actual package/native model computations were **not** executed locally.
- Optional DuckDB-backed Parquet reading was not executed locally because DuckDB was unavailable.

## Remaining blockers for actionable paper/live execution

1. Licensed historical and/or real-time 0DTE option quotes with timestamped Greeks, real underlying bars, and independently checked data coverage.
2. An authenticated vendor ingestion integration (current tools import exports only), a robust options microstructure model and executed-price calibration.
3. Real paper broker order management, partial fill reconciliation, trading-calendar safeguards, alerts, risk kill switch, persistent state recovery.
4. Extended untouched historical holdout and longer-term paper trading. There is currently **no brokerage order execution** and no actual Droplet deployment.

**Status: research prototype only. No real-money trades, no promise of profitability, stop-loss guarantee, or low loss frequency.**
