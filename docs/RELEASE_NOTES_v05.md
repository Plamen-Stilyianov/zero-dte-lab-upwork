# v0.5 release notes — robustness and multiple-hypothesis inference

- Added `statistical-audit`: stationary and circular block bootstrap for complete daily net returns; mean/Sharpe intervals; drawdown scenario tails; centered one-sided p-values; Holm, Bonferroni and Benjamini-Hochberg adjustments; synchronized exploratory max-T; advisory PSR/DSR with caveats.
- Added `export-return-panel`: converts multiple complete 0DTE trades.csv backtest reports into a comparable complete-session returns panel with explicit fixed research capital; checks trade P&L against corresponding summaries and refuses incomplete reporting.
- Added 14 regression tests and synthetic multi-strategy daily return generator.
- Applied no changes to risk limits, 2x volume rule, 0.75 delta rule, 0DTE contract selection, entry/exit state machine, Greek trust settings, or broker connectivity.
- No real-data significance claims. No automatic strategy promotion. No CPCV or formal Romano-Wolf stepdown.

See [STATISTICAL_INFERENCE_v05.md](STATISTICAL_INFERENCE_v05.md).
