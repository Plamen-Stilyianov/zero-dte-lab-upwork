"""Transaction-cost sensitivity on the same immutable input tape.

Deliberately only worsens per-side slippage; a backtest that fails realistic
fills should be rejected, never optimized to 'fix' the historical test.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from .config import Settings
from .data import read_frames
from .engine import StrategyEngine
from .report import make_report


def run_slippage_stress(data: str, c: Settings, cents_per_side: list[float],
                        out: str, delta_source: str = "provided") -> dict:
    if not cents_per_side or len(cents_per_side) > 12:
        raise ValueError("Supply 1..12 slippage scenarios")
    if any(not (0 <= v <= 0.50) for v in cents_per_side):
        raise ValueError("Slippage scenarios must be between $0 and $0.50 per share")
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    # A fixed-fill perturbation isolates fee/slippage drag on the same baseline
    # decisions. It does NOT change stop paths or infer fill probability.
    baseline = StrategyEngine(c)
    for frame in read_frames(data, delta_source):
        baseline.on_frame(frame)
    baseline.finalize()
    rows = []
    for i, amount in enumerate(cents_per_side):
        config = replace(c, entry_slippage=amount, exit_slippage=amount)
        engine = StrategyEngine(config)
        for frame in read_frames(data, delta_source):
            engine.on_frame(frame)
        engine.finalize()
        summary = make_report(engine, str(root / f"scenario_{i+1:02d}"))
        additional_cost = (max(0, amount - c.entry_slippage)
                           + max(0, amount - c.exit_slippage)) * 100
        fixed_fill_pnl = sum(t.pnl - additional_cost * t.qty for t in baseline.trades)
        rows.append({"slippage_usd_per_option_share_per_side": amount,
                     "risk_gated_replay_trades": summary["trades"],
                     "risk_gated_replay_pnl_usd_after_costs": summary["pnl_usd_after_costs"],
                     "conditional_same_trades_pnl_usd": round(fixed_fill_pnl, 2),
                     "conditional_same_trades_count": len(baseline.trades),
                     "complete_tape": summary["complete_tape"]})
    report = {"kind":"slippage_sensitivity_not_validated_market_impact_model",
              "scenarios":rows,
              "warnings":["No scenario models fill probability, exchange queue, market impact or halt gaps.",
                          "Conditional same-trades P&L holds signals/stop paths fixed; it is a sensitivity bound, not a simulated fill path.",
                          "Slippage impacts position sizing; risk-gated replay counts may differ or fall to zero."]}
    (root / "stress.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
