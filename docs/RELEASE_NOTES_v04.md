# v0.4 — Free-data feasibility and research-only Greeks

- Added bounded, read-only DoltHub SQL schema/example inspection with no automatic transition to trusted intraday tape.
- Fixed DoltHub branch to `master` based on third-party 2026 reconnaissance; verify against live platform.
- Identified `vol` in DoltHub chain schema as **implied volatility, NOT traded volume**; dataset not a 2x-volume options tape.
- Added pure stdlib Black-Scholes price/Greek calculator, IV bracketing and numerical tests; preserves local research-only labeling.
- Added CSV enrichment with no-look-ahead checks for spot, option quotes, rates, decision time, and explicit expiry timestamp.
- Added LEAN Cloud data-inspection sample with no trading or price-history exfiltration.
- Added tests for API failures and future-dated observations; keeps v0.3 backtest/paper prototype unchanged.
- Did not download any market data, confirm Dolt live table schema, validate against an external American-style Greek vendor, or run a QuantConnect job.
- Hardened v0.3 `--delta-source estimated` loader: it now refuses to use the later underlying-bar close to value an earlier quote (point-in-time leakage correction).
