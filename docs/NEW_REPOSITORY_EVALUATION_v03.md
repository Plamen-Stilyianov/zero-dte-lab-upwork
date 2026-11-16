# Review of supplied agentic research and audit repositories

Reviewed documentation (2026-11-08). Decisions are based on stated functionality, not a third-party security audit of every repository file.

1. https://github.com/ult666666/agentic-trading-research — research-first market analysis with AI-generated proposals and deterministic Python validation, provenance, and human review; explicitly no automated execution. **Adopt the proposal/validation separation; do not import its runtime.**
2. https://github.com/yzhao062/awesome-auditable-ai — catalog of decision provenance, reliability, runtime guardrails, failure attribution, reproducibility, and benchmarks. **Adopt verifiable evidence as a design principle, not the entire collection as a dependency.**
3. https://github.com/mnemox-ai/tradememory-protocol — local trade/decision memory and auditable hash-chain records, plus a broker-proxy pilot. Current Alpaca proxy explicitly refuses options, stop-limit, trailing and replacement orders. **Adopt the decision-journal design in a small original module; do not use its proxy to approve options trading.** Outcome-weighted memory may be revisited for post-trade analysis after a real OOS dataset exists.

### Auditing principles translated into implementation

- Signal/features at completed bar, option quotes + Greeks as-of event time, entry only at a later observed frame.
- Never fit scalers or feature transformations before train/test separation.
- Account in cents using `Decimal`, even if market models use float.
- Precompute feature engineering when justified; keep order lifecycle, partial fills, slippage/stop execution state event-driven.
- Preserve trade history and no-trade reasons; append hashes and verify chains.
- Treat network disruption, stale Greeks, market halts, data corruption, and gaps as *unknown exposure* rather than assumed safe fills.
- Separate *stress/reliability tests* from *statistical validation*. A positive shuffled-series Sharpe is not, by itself, proof of leakage; false positives, unsuitable nulls, and metric invariance matter.
- Implementing CPCV would require event-label start/end timestamps, accurate purging of overlapping labels, embargo and train-only transforms. Current block-bootstrap is **not CPCV**.

Source-credit: all research inspiration attributed by URL; no external source code copied. Check all upstream licenses before any future code adoption.
