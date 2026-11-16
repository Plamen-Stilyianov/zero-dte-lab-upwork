"""Interpretable online regime gate; only uses closed trades from earlier dates.

Guardrail: the learner can veto trades, but cannot lower delta/volume requirements,
change stop sizes, increase risk or issue orders.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from statistics import fmean, stdev
from .models import Trade


def regime_report(trades: list[Trade], before: date | None = None) -> dict:
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        if before is None or trade.exit_time.date() < before:
            groups[trade.regime].append(trade.pnl / trade.qty)
    summary = {}
    for regime, pnl in groups.items():
        n = len(pnl)
        avg = fmean(pnl)
        # Lower one-sided confidence estimate. A crude conservatism gate, not a proof of alpha.
        lower = avg - (1.28 * stdev(pnl) / sqrt(n) if n > 1 else float("inf"))
        summary[regime] = {"n": n, "avg_usd_per_contract": avg,
                           "pessimistic_edge_usd": lower,
                           "win_rate": sum(p > 0 for p in pnl) / n}
    return summary


def regime_permitted(regime: str, trades: list[Trade], before: date,
                     min_trades: int, min_edge: float) -> bool:
    stats = regime_report(trades, before).get(regime)
    # In paper trading only: exploration while evidence is too sparse.
    if stats is None or stats["n"] < min_trades:
        return True
    return stats["pessimistic_edge_usd"] > min_edge
