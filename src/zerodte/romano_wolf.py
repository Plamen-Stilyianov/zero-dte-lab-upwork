"""Studentized Romano-Wolf stepdown for synchronously observed daily return panels.

One-sided nulls: mean(net_return_j) <= 0 vs mean > 0.
Synchronous stationary/circular block bootstrap estimates the joint centered
null law; Newey-West/Bartlett long-run variance studentizes each return series.
Uses max over remaining hypotheses, plus-one Monte Carlo p-values, and stepdown
monotonicity. Strong FWER control is asymptotic and CONDITIONAL on a valid
bootstrap for the dependence, stable test definitions, and complete trial family.

Not a substitute for selection provenance, CPCV or chronological holdout.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from random import Random
from statistics import fmean
from .statistical_audit import ReturnPanel, bootstrap_indices, load_return_panel, adjust_pvalues


def _hac_variance(xs: list[float], lags: int) -> float:
    """Bartlett/HAC estimate of n * Var(sample mean), not SD of observations."""
    n = len(xs)
    m = fmean(xs)
    c = [v - m for v in xs]
    result = sum(x*x for x in c) / n
    for lag in range(1, min(lags, n - 1) + 1):
        gamma = sum(c[i] * c[i-lag] for i in range(lag, n)) / n
        result += 2 * (1 - lag / (lags + 1)) * gamma
    return max(0.0, result)


def _t_stat(xs: list[float], centering: float, lags: int) -> float | None:
    scale = _hac_variance(xs, lags)
    if scale < 1e-22:
        # All-zero returns are a degenerate null; any fixed nonzero return path
        # cannot be studentized and is rejected at the input validation stage.
        if max(xs) - min(xs) <= 1e-12 and abs(fmean(xs)) <= 1e-12:
            return 0.0
        return None
    return math.sqrt(len(xs)) * (fmean(xs) - centering) / math.sqrt(scale)


def romano_wolf_panel(panel: ReturnPanel, *, iterations: int = 1999,
                       block_length: int | None = None, method: str = 'stationary',
                       lags: int | None = None, alpha: float = 0.05,
                       seed: int = 731, declared_trials: int | None = None,
                       min_sessions: int = 120) -> dict:
    n, m = len(panel.dates), len(panel.names)
    if n < min_sessions or min_sessions < 30:
        raise ValueError('Need at least min_sessions complete sessions (minimum 30)')
    if not 0 < alpha < 1 or iterations < 199 or iterations > 100000:
        raise ValueError('Require 0 < alpha < 1 and 199 <= iterations <= 100000')
    block = block_length if block_length is not None else max(2, round(n ** (1/3)))
    if not 1 <= block <= n:
        raise ValueError('Invalid block length')
    lag_count = lags if lags is not None else max(1, round(n ** (1/3)))
    if not 0 <= lag_count < n:
        raise ValueError('Invalid HAC lags')
    if declared_trials is None:
        declared_trials = m
    if declared_trials < m:
        raise ValueError('declared_trials cannot be below observed trial count')
    columns = [[panel.values[i][j] for i in range(n)] for j in range(m)]
    observed: list[float] = []
    original_means: list[float] = []
    for name, xs in zip(panel.names, columns):
        mu = fmean(xs)
        t = _t_stat(xs, 0.0, lag_count)
        if t is None:
            raise ValueError(f'Cannot studentize degenerate strategy {name}; inspect constant returns')
        original_means.append(mu)
        observed.append(t)
    rng = Random(seed)
    replicates: list[list[float]] = []
    for _ in range(iterations):
        indices = bootstrap_indices(n, block, rng, method=method)
        row: list[float] = []
        for j in range(m):
            sample = [columns[j][i] for i in indices]
            t = _t_stat(sample, original_means[j], lag_count)
            if t is None:
                # Null recentered constant series has zero sampling variation.
                # A nonzero collapsed estimate is not reliably studentized.
                if max(sample) - min(sample) <= 1e-12 and abs(fmean(sample) - original_means[j]) <= 1e-12:
                    t = 0.0
                else:
                    raise ValueError('Bootstrap variance collapsed; choose longer sample or other block length')
            row.append(t)
        replicates.append(row)
    # One-sided positive-edge hypotheses: rank largest observed t first.
    rank = sorted(range(m), key=lambda j: (-observed[j], j))
    unadjusted = [(1 + sum(b[j] >= observed[j] for b in replicates)) / (iterations + 1)
                  for j in range(m)]
    p_rw = [1.0] * m
    p_single = [1.0] * m
    previous = 0.0
    for k, j in enumerate(rank):
        active = rank[k:]
        exceed = sum(max(b[v] for v in active) >= observed[j] for b in replicates)
        current = (exceed + 1) / (iterations + 1)
        previous = max(previous, current)
        p_rw[j] = previous
    max_all = [max(row) for row in replicates]
    for j in range(m):
        p_single[j] = (1 + sum(v >= observed[j] for v in max_all)) / (iterations + 1)
    other = adjust_pvalues(unadjusted, declared_count=declared_trials)
    hypotheses = []
    for j, name in enumerate(panel.names):
        hypotheses.append({'strategy_id': name, 'observed_t': round(observed[j], 8),
                           'mean_daily_return': round(original_means[j], 9),
                           'unadjusted_bootstrap_p': round(unadjusted[j], 6),
                           'romano_wolf_stepdown_p': round(p_rw[j], 6),
                           'single_step_max_t_p': round(p_single[j], 6),
                           'holm_declared_family_p': round(other['holm'][j], 6),
                           'pass_rw_alpha': p_rw[j] < alpha and declared_trials == m})
    return {'method': 'romano_wolf_studentized_block_bootstrap',
            'hypothesis': 'H0: mean net daily return <= 0; H1: > 0',
            'resampling_method': method, 'iterations': iterations,
            'block_length_sessions': block, 'newey_west_lags': lag_count,
            'alpha': alpha, 'seed': seed, 'session_count': n,
            'supplied_strategy_count': m, 'declared_trials': declared_trials,
            'entire_declared_family_supplied': declared_trials == m,
            'input_sha256': panel.sha256, 'hypotheses': hypotheses,
            'limitations': [
                'Asymptotic FWER interpretation depends on valid stationary/mixing dependence and studentization.',
                'Joint resamples preserve dependence across supplied strategies; no claim about unreported variants.',
                'A declared_trials value larger than supplied_strategy_count makes RW p-values incomplete-family only.',
                'Use fully reconciled daily net returns, including days with zero trades and all strategy attempts.',
                'No test here proves point-in-time market data accuracy or execution feasibility.',
                'An independent chronological holdout and forward paper trading are still required.'
            ], 'can_promote_to_live': False}


def romano_wolf_csv(source: str | Path, out: str | Path, **kwargs) -> dict:
    panel = load_return_panel(source)
    report = romano_wolf_panel(panel, **kwargs)
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
