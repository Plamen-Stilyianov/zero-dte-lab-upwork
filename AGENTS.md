# ZeroDTE Lab v0.6 — CPCV and Romano–Wolf Statistical Validation

Research-only 0DTE options simulation and statistical validation prototype. Never live trading or broker order execution.

## Environment & Tool Execution Rules
- Python 3.14+ environment: `/home/orajava/.myenv/zero-dte-lab/bin/python`
- Run test suite: `/home/orajava/.myenv/zero-dte-lab/bin/pytest -q`
- Run full static & security audit: `/home/orajava/.myenv/zero-dte-lab/bin/python scripts/audit.py`
- CLI entry point: `/home/orajava/.myenv/zero-dte-lab/bin/zerodte`
- Always execute shell commands with `bash` (never use JavaScript `execute` / Code Mode).
- Always reference files using plain relative paths (e.g. `src/zerodte/engine.py`), not `@` prefixes.
- **Verification Discipline (Mandatory):** Never claim tests pass without actually executing `/home/orajava/.myenv/zero-dte-lab/bin/pytest -q` and pasting the real exit status and summary line.
- **Test Integrity:** Never swallow broad `Exception` or `ValueError` in tests unless asserting a specific error message with `pytest.raises(..., match=...)`. Only reference existing fixtures in `data/` or programmatic builders from `tests/test_core.py`.

## Key Module Layout
- `src/zerodte/cli.py` — Main CLI entry points (`backtest`, `walk-forward`, `cpcv-plan`, `romano-wolf`, `statistical-audit`, `adversarial`, `audit-replay`, `verify-ledger`)
- `src/zerodte/engine.py` — Core 0DTE strategy simulation, regime gating, and risk limits
- `src/zerodte/models.py` — Core dataclasses and quote/bar validation (`OptionQuote`, fills, positions)
- `src/zerodte/signal.py` — Rolling 20-bar volume baseline, 10-bar high/low, VWAP, EMA(9/21), and regime bucketing
- `src/zerodte/data.py` & `vendor_merge.py` — Sorted minute-bar ingestion, DuckDB/Parquet streaming, bar-to-quote merging, and quote validation
- `src/zerodte/config.py` — System configuration and fail-closed risk defaults
- `src/zerodte/learn.py`, `validation.py`, `rolling.py` — Online/frozen regime gating, holdout, and rolling walk-forward evaluation
- `src/zerodte/report.py` — Backtest performance and stop-slippage diagnostics
- `src/zerodte/greeks.py` & `greeks_quality.py` — Black-Scholes Greeks enrichment and trusted provenance/as-of timestamp checks
- `src/zerodte/cpcv.py` — Combinatorial Purged Cross-Validation (CPCV) split planning and embargo logic
- `src/zerodte/romano_wolf.py` — Studentized block bootstrap Romano–Wolf stepdown FWER correction
- `src/zerodte/statistical_audit.py` & `statistics.py` — Stationary/circular bootstrap, Holm/BH corrections, PSR/DSR diagnostics
- `src/zerodte/audit_ledger.py`, `audit_replay.py`, `source_audit.py` — SHA-256 decision ledger and AST leakage scanner
- `src/zerodte/adversarial.py`, `stress.py`, `paper_watch.py`, `alpaca.py` — Fault injection, cost stress, and read-only Alpaca watcher
- `tests/` — Deterministic unit tests (`test_core.py`, `test_quality_v02.py`, `test_audit_v03.py`, `test_free_data_v04.py`, `test_statistical_audit_v05.py`, `test_v06_cpcv_rw.py`, `test_adversarial.py`, `test_nautilus_reference.py`)

## Domain Glossary
- **CPCV:** Combinatorial Purged Cross-Validation (`cpcv.py`)
- **RW:** Romano–Wolf stepdown multiple-hypothesis FWER correction (`romano_wolf.py`)
- **PSR / DSR:** Probabilistic Sharpe Ratio / Deflated Sharpe Ratio (`statistical_audit.py`)
- **HAC:** Heteroskedasticity and Autocorrelation Consistent variance (Newey–West weighting)

## Safety & Research Guardrails
- Default to synthetic data (`data/SYNTHETIC_*.csv`) for all tests and demos; verify exact filenames in `data/` before referencing them.
- Never commit `.env` secrets or paste API keys.
- Preserve fail-closed Greek provenance checks (`greek_provider`, `delta_ts`), SHA-256 audit ledger integrity, and 0DTE risk rules (`delta >= 0.75`, 2x underlying volume trigger, $0.40 stop).

## Strategy & Backtest Invariants (Audit Findings — Enforce on All Edits)
- **Bar Timestamp Convention & Lookahead Prevention (`src/zerodte/vendor_merge.py`, `src/zerodte/data.py`, `src/zerodte/alpaca.py`):**
  - `alpaca.py` shifts bar-start timestamps by `+1 minute`; `vendor_merge.py` and `data.py` must enforce and verify the same bar-end availability convention before joining bars to option quotes so no future bar `close` leaks into an earlier quote timestamp.
- **Zero-Bid Option Quotes (`src/zerodte/models.py`, `src/zerodte/engine.py`, `src/zerodte/alpaca.py`):**
  - `OptionQuote` (`models.py`) must allow `bid == 0.0` (only rejecting `bid < 0` or `ask <= 0` / crossed markets) so deep-OTM 0DTE contracts trigger stop exits cleanly rather than aborting replay or returning `None` in `alpaca._quote`.
  - When exiting on `bid == 0.0`, clamp the fill price at `max(0.0, bid - exit_slippage)` (`$0.00` minus commissions) rather than filling at a negative option price.
- **0DTE Day Rollover & Streaming Tape Completeness (`src/zerodte/engine.py`, `src/zerodte/validation.py`, `src/zerodte/rolling.py`):**
  - On day rollover in `engine.py`, do **not** look up yesterday's option symbol in today's quotes. Flag the run incomplete (`engine.incomplete = True`) and force-close the open position using the **last observed quote and timestamp from the prior session** so P&L is booked to that trading day.
  - `run_rolling` (`rolling.py`) and `run_holdout` (`validation.py`) must gate frozen allowlist learning on `train_engine.incomplete` (and use streaming gap checks without materializing entire multi-day tapes into memory or using naive `datetime.replace(minute=...)` arithmetic).
- **Continuous Bar Series & Pending Signal TTL (`src/zerodte/data.py`, `src/zerodte/engine.py`):**
  - Underlying 1-minute bar windows (`20-bar` volume baseline, `10-bar` high/low) must not silently collapse across missing option quote minutes, and `pending` entries must enforce a strict maximum frame/time TTL so stale signals expire across tape gaps.
- **Regime Gate & Timezone Consistency (`src/zerodte/validation.py`, `src/zerodte/rolling.py`, `src/zerodte/learn.py`):**
  - Keep frozen allowlist rules (`validation.py`, `rolling.py`) aligned with online `regime_permitted` semantics, and normalize `exit_time` to `America/New_York` before comparing dates in `regime_report` (`learn.py`).
- **Diagnostics & Live/Backtest Parity (`src/zerodte/report.py`, `src/zerodte/alpaca.py`, `src/zerodte/paper_watch.py`, `src/zerodte/signal.py`):**
  - Set gap-slippage thresholds in `report.py` relative to full worst-case initial stop cost (`-$43.30` including slippage + commissions, not `-$40.00`), and keep saved report keys/README documentation consistent.
  - Document `signal.py` surge bucket thresholds (`ratio >= 3`, `strength >= 0.001`) in `config.py`/README and keep `min_option_volume` definitions aligned between `alpaca.py` and backtest data ingestion.
- **Required Regression Test Coverage (`tests/`):**
  - Maintain unit tests covering: bar-timestamp convention / no-lookahead merge, `bid == 0.0` stop execution, open position forced close at day rollover (booked to prior session), `entry_delay_bars > 1` and `pending` TTL expiry, positive signal generation, and breakeven (`+$0.55`) / trailing (`+$0.65 / -$0.45`) stop-out paths.
