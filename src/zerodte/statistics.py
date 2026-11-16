"""Session-clustered research diagnostics; not proof of trading alpha.

A moving-block bootstrap quantifies uncertainty on a frozen OOS daily P&L
sequence. A block-wise sign-flip null requires approximately symmetric
block-sum innovations; it is not CPCV and not a 'shuffled target' test.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from random import Random
from statistics import fmean


def drawdown_profile(daily_pnl: list[float]) -> dict:
    equity = peak = 0.0
    trough = 0.0
    peak_index = 0
    longest_recovery = 0
    in_drawdown = False
    unresolved = 0
    for i, profit in enumerate(daily_pnl):
        equity += profit
        if equity >= peak:
            if in_drawdown:
                longest_recovery = max(longest_recovery, i - peak_index)
            peak = equity
            peak_index = i
            in_drawdown = False
            unresolved = 0
        else:
            in_drawdown = True
            unresolved = i - peak_index
            trough = min(trough, equity - peak)
    return {"max_closed_session_drawdown_usd": round(trough, 2),
            "longest_recovered_drawdown_sessions": longest_recovery,
            "unresolved_drawdown_sessions": unresolved if in_drawdown else 0,
            "recovery_factor": round(sum(daily_pnl) / abs(trough), 4) if trough < 0 else None}


def _percentile(v: list[float], p: float) -> float:
    sorted_v = sorted(v)
    point = (len(sorted_v) - 1) * p
    low = math.floor(point)
    high = math.ceil(point)
    return sorted_v[low] + (sorted_v[high] - sorted_v[low]) * (point - low)


def validate_session_pnl(daily_pnl: list[float], block: int = 5,
                         replications: int = 1000, seed: int = 741) -> dict:
    if not daily_pnl or any(not math.isfinite(v) for v in daily_pnl):
        raise ValueError("Finite nonempty chronological session P&Ls required")
    if not (1 <= block <= len(daily_pnl)):
        raise ValueError("Block must fit series")
    if not (100 <= replications <= 10000):
        raise ValueError("Replications must be 100..10000")
    if not isinstance(seed, int):
        raise ValueError("Seed must be an integer")
    rng = Random(seed)
    n = len(daily_pnl)
    actual = fmean(daily_pnl)
    resampled_means = []
    null_means = []
    # Circular moving-block bootstrap keeps short-lag dependence in the sampled path.
    # Blocks are contiguous; single observations are never independently reshuffled.
    for _ in range(replications):
        sample = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(daily_pnl[(start + j) % n] for j in range(block))
        resampled_means.append(fmean(sample[:n]))
        # Non-overlapping fixed blocks, randomized sign at block level; the
        # symmetry/null-exchangeability assumption is stronger than bootstrap CI.
        null_sample = []
        for i in range(0, n, block):
            sign = -1 if rng.randrange(2) else 1
            null_sample.extend(sign * x for x in daily_pnl[i:i+block])
        null_means.append(fmean(null_sample))
    p_one_sided = (1 + sum(v >= actual for v in null_means)) / (replications + 1)
    return {"kind": "session_block_bootstrap_exploratory",
            "session_count": n, "block_size_sessions": block,
            "replications": replications, "seed": seed,
            "mean_daily_pnl_usd": round(actual, 4),
            "bootstrap_mean_95pct_interval_usd": [round(_percentile(resampled_means, x), 4)
                                                   for x in (.025, .975)],
            "block_sign_flip_one_sided_p_value": round(p_one_sided, 6),
            "drawdown": drawdown_profile(daily_pnl),
            "can_promote_to_live": False,
            "limitations": [
                "Only valid for a frozen out-of-sample, complete session P&L sequence (include zero-trade days).",
                "Dependent observations and few sessions can make confidence intervals unreliable.",
                "Block sign-flip null requires distributional symmetry; its p-value is exploratory.",
                "Does not adjust for strategy selection, multiple comparisons or repeated peeking.",
                "Not combinatorial purged cross-validation (CPCV) and not a causal signal permutation test.",
                "Session-level closed P&L ignores intraday marked-to-market equity troughs."],
            }


def from_trades(trades: list, sessions: list, block: int, replications: int, seed: int,
                timezone: str = "America/New_York") -> dict:
    """Construct UTC/calendar-compatible session panel. Caller supplies local-session dates."""
    from datetime import date
    from zoneinfo import ZoneInfo
    zone = ZoneInfo(timezone)
    dates = [d if isinstance(d, date) else date.fromisoformat(str(d)) for d in sessions]
    if sorted(set(dates)) != dates:
        raise ValueError("Sessions must be unique, sorted dates")
    realized = {d: 0.0 for d in dates}
    for trade in trades:
        d = trade.exit_time.astimezone(zone).date()
        if d not in realized:
            raise ValueError(f"Trade exit outside sampled sessions: {d}")
        realized[d] += trade.pnl
    report = validate_session_pnl([realized[d] for d in dates], block, replications, seed)
    report["zero_trade_sessions"] = sum(realized[d] == 0 for d in dates)
    return report


def write_statistics(report: dict, output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n")
