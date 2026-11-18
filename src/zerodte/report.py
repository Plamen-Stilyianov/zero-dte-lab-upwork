"""Outcome reporting. Honest about missing evidence."""
from __future__ import annotations

import csv
import json
from math import sqrt
from pathlib import Path
from statistics import fmean, stdev

from .engine import StrategyEngine
from .learn import regime_report


def make_report(engine: StrategyEngine, output_dir: str, label: str = "backtest") -> dict:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    trades = engine.trades
    pnl = [t.pnl for t in trades]
    cum = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for p in pnl:
        cum += p
        peak = max(peak, cum)
        max_drawdown = min(max_drawdown, cum - peak)
    profit = sum(p for p in pnl if p > 0)
    loss = -sum(p for p in pnl if p < 0)
    positive = [p for p in pnl if p > 0]
    negative = [p for p in pnl if p < 0]
    days = len(set(t.entry_time.date() for t in trades))
    summary = {
        "kind": label,
        "validated": False,  # not automatically promoted by a backtest
        "historical_data_verified": False,
        "complete_tape": not engine.incomplete,
        "trades": len(trades),
        "days_with_trades": days,
        "pnl_usd_after_costs": round(sum(pnl), 2),
        "avg_trade_usd": round(fmean(pnl), 2) if pnl else None,
        "win_rate": round(sum(p > 0 for p in pnl) / len(pnl), 4) if pnl else None,
        "loss_frequency": round(len(negative) / len(pnl), 4) if pnl else None,
        "avg_winner_usd": round(fmean(positive), 2) if positive else None,
        "avg_loser_usd": round(fmean(negative), 2) if negative else None,
        "win_to_loss_size_ratio": round(fmean(positive) / -fmean(negative), 3) if positive and negative else None,
        "largest_trade_loss_usd": round(min(pnl), 2) if pnl else None,
        "stop_exits_losing_more_than_40usd": sum(
            t.reason == "stop_or_trailing" and t.pnl < -40 * t.qty for t in trades),
        "stop_exits_with_gap_slippage": sum(
            t.reason == "stop_or_trailing"
            and t.pnl < -(
                (engine.c.stop_premium + engine.c.exit_slippage) * 100
                + 2 * engine.c.commission_per_contract_per_side
            ) * t.qty - 0.01
            for t in trades
        ),
        "profit_factor": round(profit / loss, 3) if loss else None,
        "max_closed_trade_drawdown_usd": round(max_drawdown, 2),
        "standard_error_usd": round(stdev(pnl) / sqrt(len(pnl)), 2) if len(pnl) > 1 else None,
        "regimes": regime_report(trades),
        "warnings": [
            "Quote backtests cannot capture queue priority, market impact, exchange halts or all slippage.",
            "0DTE exits and $0.40 stops are not guaranteed; stop fill may be worse than trigger.",
            "A signal evaluated at bar close enters only at the next observed quote.",
            "Historical research must use surviving AND delisted/expired contracts, point-in-time delta and valid quotes.",
        ],
    }
    if engine.incomplete:
        summary["warnings"].append("OPEN POSITION OR MISSING FORCE-EXIT QUOTE: result is incomplete.")
    if days < 30:
        summary["warnings"].append("Fewer than 30 trading days with trades; not meaningful evidence of robustness.")
    (path / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with open(path / "trades.csv", "w", newline="", encoding="utf-8") as f:
        if trades:
            writer = csv.DictWriter(f, fieldnames=list(trades[0].as_dict()))
            writer.writeheader()
            writer.writerows(t.as_dict() for t in trades)
        else:
            f.write("option,underlying,right,regime,entry_time,exit_time,entry_price,exit_price,qty,pnl,reason,entry_delta,entry_volume_ratio\n")
    (path / "events.log").write_text("\n".join(engine.events) + "\n")
    return summary
