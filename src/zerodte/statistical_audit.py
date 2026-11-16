"""Research-only inference on a *frozen*, aligned panel of daily net strategy returns.

This module does NOT establish point-in-time validity of trading data or independence
from the researcher's previous selection decisions. Inputs must be complete daily
mark-to-market percentage returns on comparable, fixed capital conventions, including
zero-trade days, before this module can produce meaningful numbers.

Stationary bootstrap (Politis-Romano) and circular moving-block bootstrap treat daily
sessions as the dependence unit. Synchronous resampling preserves between-strategy
co-movement, and the family-wise max-T bootstrap is an exploratory dependence-aware
multiple-comparison check, not a replacement for a truly frozen holdout.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from random import Random
from statistics import NormalDist, fmean, pstdev


@dataclass(frozen=True)
class ReturnPanel:
    dates: tuple[date, ...]
    names: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]  # row = trading session, column = variant
    sha256: str


def load_return_panel(source: str | Path) -> ReturnPanel:
    """Read long-form CSV: session,strategy_id,daily_return. No forward-filling.

    daily_return is a dimensionless net return (e.g. 0.01 == +1% of capital).
    A complete panel requires every declared variant for every session, including
    zero-return days; missing rows are fatal, not assumed to be zero.
    """
    path = Path(source)
    raw = path.read_bytes()
    rows_by_day: dict[date, dict[str, float]] = {}
    names: list[str] = []
    seen_names: set[str] = set()
    last_date: date | None = None
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or not {"session", "strategy_id", "daily_return"}.issubset(reader.fieldnames):
            raise ValueError("CSV must have session,strategy_id,daily_return columns")
        count = 0
        for row in reader:
            count += 1
            if any(row.get(k) is None for k in ("session", "strategy_id", "daily_return")):
                raise ValueError(f"Incomplete row {count}")
            day = date.fromisoformat(row["session"].strip())
            name = row["strategy_id"].strip()
            if not name:
                raise ValueError(f"Empty strategy_id on row {count}")
            if last_date is not None and day < last_date:
                raise ValueError("CSV sessions must be chronological; do not sort into place silently")
            last_date = day
            value = float(row["daily_return"].strip())
            if not math.isfinite(value) or value <= -1.0:
                raise ValueError(f"Invalid daily return on row {count}")
            if name in rows_by_day.setdefault(day, {}):
                raise ValueError(f"Duplicate variant/session: {name}/{day}")
            rows_by_day[day][name] = value
            if name not in seen_names:
                seen_names.add(name)
                names.append(name)
    if not rows_by_day:
        raise ValueError("At least one complete session is required")
    if len(names) > 500:
        raise ValueError("At most 500 explicitly declared strategy variants are supported")
    for day, row in rows_by_day.items():
        if set(row) != seen_names:
            missing = sorted(seen_names - set(row))
            raise ValueError(f"Incomplete aligned panel on {day}; missing {missing[:5]} (no implicit zeros)")
    days = tuple(rows_by_day)
    return ReturnPanel(days, tuple(names), tuple(tuple(rows_by_day[day][name] for name in names)
                                                       for day in days), hashlib.sha256(raw).hexdigest())


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("Empty sample")
    idx = (len(sorted_values) - 1) * quantile
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (idx - lo)


def _interval(values: list[float], alpha: float) -> list[float | None]:
    vals = sorted(x for x in values if math.isfinite(x))
    if len(vals) < 20:
        return [None, None]
    return [round(_percentile(vals, alpha / 2), 8), round(_percentile(vals, 1 - alpha / 2), 8)]


def bootstrap_indices(n: int, mean_block: int, rng: Random,
                      method: str = "stationary") -> list[int]:
    if n < 2 or not 1 <= mean_block <= n:
        raise ValueError("Invalid block length or panel size")
    if method not in {"stationary", "circular"}:
        raise ValueError("Bootstrap method must be stationary or circular")
    selected: list[int] = []
    if method == "stationary":
        # A new random start with probability 1/L, else stay within the
        # consecutive circular block (geometric expected block length L).
        index = rng.randrange(n)
        for t in range(n):
            if t and rng.random() < 1.0 / mean_block:
                index = rng.randrange(n)
            selected.append(index)
            index = (index + 1) % n
    else:
        while len(selected) < n:
            start = rng.randrange(n)
            selected.extend((start + k) % n for k in range(mean_block))
        selected = selected[:n]
    return selected


def adjust_pvalues(p_values: list[float], declared_count: int | None = None) -> dict:
    """Adjusted p-values, preserving original positions. Missing logged trials p=1.

    Unreported experiments cannot be reconstructed; `declared_count` only applies
    a conservative family-size allowance and cannot repair selective reporting.
    BH requires appropriate dependence (independent or PRDS-like p-values). Holm
    is valid under arbitrary dependence when individual p-values are valid.
    """
    m_present = len(p_values)
    if not m_present or any(not math.isfinite(p) or not 0 <= p <= 1 for p in p_values):
        raise ValueError("Finite p-values in [0,1] required")
    m = m_present if declared_count is None else declared_count
    if m < m_present:
        raise ValueError("declared_count must cover all observed variants")
    if m > 100000:
        raise ValueError("declared_count is limited to 100000")
    all_p = p_values + [1.0] * (m - m_present)
    sorted_pair = sorted(enumerate(all_p), key=lambda item: item[1])
    holm = [1.0] * m
    bh = [1.0] * m
    previous = 0.0
    for rank, (idx, value) in enumerate(sorted_pair):
        previous = max(previous, (m - rank) * value)
        holm[idx] = min(1.0, previous)
    previous = 1.0
    for rank in range(m - 1, -1, -1):
        idx, value = sorted_pair[rank]
        previous = min(previous, value * m / (rank + 1))
        bh[idx] = min(1.0, previous)
    return {"bonferroni": [min(1.0, m * p) for p in p_values],
            "holm": holm[:m_present], "benjamini_hochberg": bh[:m_present]}


def _mean_std(values: list[float] | tuple[float, ...]) -> tuple[float, float]:
    return fmean(values), pstdev(values)


def _sharpe(values: list[float] | tuple[float, ...]) -> float | None:
    mu, sigma = _mean_std(values)
    return mu / sigma if sigma > 1e-14 else None


def _max_compounded_drawdown(returns: list[float]) -> float:
    wealth = peak = 1.0
    maximum = 0.0
    for r in returns:
        wealth *= (1 + r)
        if wealth > peak:
            peak = wealth
        else:
            maximum = max(maximum, 1 - wealth / peak)
    return maximum


def _moments(returns: list[float]) -> tuple[float, float] | None:
    mean, sigma = _mean_std(returns)
    if sigma < 1e-14:
        return None
    centered = [(x - mean) / sigma for x in returns]
    return (fmean(x ** 3 for x in centered), fmean(x ** 4 for x in centered))


def probabilistic_sharpe(returns: list[float], benchmark: float) -> float | None:
    """PSR probability estimate (non-excess kurtosis, session-scale Sharpe).

    The classic PSR approximation assumes sufficiently many near-independent
    observations. When returns cluster, it may overstate confidence; report as
    an advisory only alongside the dependence-aware bootstrap diagnostics.
    """
    if len(returns) < 30:
        return None
    sr = _sharpe(returns)
    moments = _moments(returns)
    if sr is None or moments is None:
        return None
    skew, kurtosis = moments
    denominator_squared = 1 - skew * sr + ((kurtosis - 1) / 4) * sr ** 2
    if denominator_squared <= 1e-12:
        return None
    z = (sr - benchmark) * math.sqrt(len(returns) - 1) / math.sqrt(denominator_squared)
    return NormalDist().cdf(z)


def deflated_sharpe(returns: list[float], all_trial_sharpes: list[float | None],
                    declared_trials: int) -> dict:
    """DSR is PSR evaluated against an expected *selected maximum* Sharpe.

    A variance estimate across observed trial Sharpe ratios is required. Using
    declared_trials > observed_trials is indicative because unreported trial
    outcomes cannot be reconstructed. Related strategies violate the independent
    trial approximation. No raw Sharpe is overwritten with a 'haircut'.
    """
    good = [s for s in all_trial_sharpes if s is not None and math.isfinite(s)]
    if len(good) < 2 or len(returns) < 30:
        return {"probability": None, "benchmark_sharpe_per_session": None,
                "reason": "Requires at least two nondegenerate variants and 30 complete sessions"}
    spread = pstdev(good)
    if spread < 1e-12:
        return {"probability": None, "benchmark_sharpe_per_session": None,
                "reason": "Observed trial Sharpe variance is zero; cannot estimate selection benchmark"}
    n = declared_trials
    if n < 2:
        raise ValueError("At least two declared trials needed")
    nd = NormalDist()
    gamma = 0.5772156649015329
    # Following Bailey and Lopez de Prado's null-mean approximation.
    threshold = spread * ((1 - gamma) * nd.inv_cdf(1 - 1/n)
                          + gamma * nd.inv_cdf(1 - 1/(n * math.e)))
    prob = probabilistic_sharpe(returns, threshold)
    return {"probability": round(prob, 6) if prob is not None else None,
            "benchmark_sharpe_per_session": round(threshold, 8),
            "observed_trial_sharpe_std": round(spread, 8),
            "assumed_independent_trials": n,
            "reason": "Advisory only: cross-strategy dependence and serial returns weaken classic DSR assumptions"}


def analyze_panel(panel: ReturnPanel, selected: str, *,
                  iterations: int = 2000, method: str = "stationary",
                  block_length: int | None = None, alpha: float = 0.05,
                  seed: int = 731, declared_trials: int | None = None,
                  annualization: int = 252, min_sessions: int = 120) -> dict:
    if selected not in panel.names:
        raise ValueError("Selected strategy must be present in the declared variant family")
    if not 200 <= iterations <= 20000:
        raise ValueError("iterations must be 200..20000")
    if not 0 < alpha < 0.5:
        raise ValueError("alpha must be between 0 and 0.5")
    if not 1 <= annualization <= 100000:
        raise ValueError("annualization must be positive")
    if min_sessions < 30:
        raise ValueError("min_sessions must be >= 30")
    n = len(panel.dates)
    if n < 30:
        raise ValueError("At least 30 complete daily sessions required; 120+ recommended")
    block = max(2, round(n ** (1 / 3))) if block_length is None else block_length
    if not 1 <= block <= n:
        raise ValueError("block_length must fit session panel")
    if method not in {"stationary", "circular"}:
        raise ValueError("method must be stationary or circular")
    count = len(panel.names)
    m = count if declared_trials is None else declared_trials
    if m < count or m > 100000:
        raise ValueError("declared_trials must include all variants and be <=100000")
    rng = Random(seed)
    series = [[row[j] for row in panel.values] for j in range(count)]
    means = [fmean(s) for s in series]
    sigmas = [pstdev(s) for s in series]
    centered = [[x - means[j] for x in series[j]] for j in range(count)]
    boot_means = [[] for _ in range(count)]
    boot_sharpes = [[] for _ in range(count)]
    boot_drawdowns = [[] for _ in range(count)]
    null_ge = [0] * count
    max_t_ge = [0] * count
    observed_t = [(means[j] * math.sqrt(n) / sigmas[j]) if sigmas[j] > 1e-14 else None
                  for j in range(count)]
    for _ in range(iterations):
        indices = bootstrap_indices(n, block, rng, method)
        null_t = []
        for j in range(count):
            sample = [series[j][k] for k in indices]
            centered_sample = [centered[j][k] for k in indices]
            mu = fmean(sample)
            boot_means[j].append(mu)
            sr = _sharpe(sample)
            if sr is not None:
                boot_sharpes[j].append(sr * math.sqrt(annualization))
            boot_drawdowns[j].append(_max_compounded_drawdown(sample))
            if fmean(centered_sample) >= means[j] - 1e-14:
                null_ge[j] += 1
            null_sigma = pstdev(centered_sample)
            null_t.append(fmean(centered_sample) * math.sqrt(n) / null_sigma
                          if null_sigma > 1e-14 else None)
        valid_null_t = [x for x in null_t if x is not None and math.isfinite(x)]
        if valid_null_t:
            family_max = max(valid_null_t)
            for j, observed in enumerate(observed_t):
                if observed is not None and family_max >= observed - 1e-14:
                    max_t_ge[j] += 1
    # Degenerate constant-return strategies cannot be assigned meaningful p-values.
    raw_p = [(null_ge[j] + 1) / (iterations + 1) if sigmas[j] > 1e-14 else 1.0
             for j in range(count)]
    adj = adjust_pvalues(raw_p, m)
    all_trial_sharpes = [_sharpe(s) for s in series]
    variants = []
    for j, name in enumerate(panel.names):
        sr = all_trial_sharpes[j]
        draws = sorted(boot_drawdowns[j])
        variants.append({
            "strategy_id": name,
            "mean_daily_net_return": round(means[j], 8),
            "annualized_sharpe_naive": round(sr * math.sqrt(annualization), 5) if sr is not None else None,
            "mean_daily_net_return_percentile_interval": _interval(boot_means[j], alpha),
            "annualized_sharpe_percentile_interval": _interval(boot_sharpes[j], alpha),
            "historical_max_compounded_drawdown": round(_max_compounded_drawdown(series[j]), 6),
            "resampled_max_drawdown_95th_percentile": round(_percentile(draws, .95), 6),
            "one_sided_centered_block_bootstrap_p": round(raw_p[j], 6),
            "holm_fwer_adjusted_p": round(adj["holm"][j], 6),
            "bh_fdr_adjusted_p": round(adj["benjamini_hochberg"][j], 6),
            "bonferroni_adjusted_p": round(adj["bonferroni"][j], 6),
            "joint_max_t_fwer_exploratory_p": (round((max_t_ge[j] + 1) / (iterations + 1), 6)
                                                    if observed_t[j] is not None else None),
            "psr_benchmark_zero_advisory": (round(value, 6) if (value := probabilistic_sharpe(
                series[j], 0.0)) is not None else None),
            "dsr_advisory": deflated_sharpe(series[j], all_trial_sharpes, m),
            "insufficient_session_count": n < min_sessions,
        })
    selected_row = next(row for row in variants if row["strategy_id"] == selected)
    report = {
        "kind": "statistical_family_audit_research_only",
        "panel_sha256": panel.sha256,
        "selected_strategy": selected,
        "session_count": n,
        "start_session": panel.dates[0].isoformat(),
        "end_session": panel.dates[-1].isoformat(),
        "present_variants": count,
        "declared_total_trials": m,
        "declared_missing_variant_results": m - count,
        "resampling": {"method": method, "mean_block_length_sessions": block,
                       "iterations": iterations, "seed": seed, "alpha": alpha,
                       "annualization_sessions": annualization},
        "variants": variants,
        "selected_exploratory_statistical_screen": {
            "holm_fwer_below_alpha": selected_row["holm_fwer_adjusted_p"] < alpha,
            "bh_fdr_below_alpha": selected_row["bh_fdr_adjusted_p"] < alpha,
            "ci_lower_mean_daily_return_above_zero": (
                selected_row["mean_daily_net_return_percentile_interval"][0] is not None
                and selected_row["mean_daily_net_return_percentile_interval"][0] > 0),
            "minimum_sessions_met": n >= min_sessions,
        },
        "can_promote_to_live": False,
        "data_provenance_verified": False,
        "model_selection_history_verified": False,
        "limitations": [
            "Panel source is user-supplied; no independent verification of genuine OOS results or quote-based fill assumptions.",
            "All tried models/assets/windows/hyperparameters must be included; omitted experiments cannot be repaired statistically.",
            "Daily returns must include zero-trade sessions and be net of spreads, fees, slippage and other realistic costs.",
            "Requires constant/comparable capital conventions; daily return units are fractions, not dollars.",
            "Block length is a sensitivity parameter. Repeat analysis at several lengths and inspect dependence/regime stability.",
            "Stationary bootstrap assumes weakly stationary dependence; regime breaks can invalidate confidence intervals.",
            "Percentile intervals are descriptive; resampled drawdown percentiles are scenarios, not population confidence intervals.",
            "BH control assumes suitable p-value dependence; Holm is a safer family-wise adjustment under arbitrary dependence.",
            "Joint max-T is an exploratory synchronized-bootstrap statistic, not a formal stepdown or CPCV guarantee.",
            "Classic PSR/DSR assumes approximately independent returns/trials; DSR is advisory when these assumptions fail.",
            "Statistical significance cannot replace independent holdout, stress tests or broker paper execution.",
        ],
    }
    return report


def audit_csv(path: str | Path, selected: str, out: str | Path, **kwargs) -> dict:
    panel = load_return_panel(path)
    report = analyze_panel(panel, selected, **kwargs)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report
