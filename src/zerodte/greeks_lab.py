"""Explicitly research-only European Black-Scholes Greeks / implied volatility.

Not a substitute for American-style ETF options pricing, quote NBBO validation,
point-in-time entitlements, market microstructure or a licensed data feed.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from math import erf, exp, isfinite, log, pi, sqrt
from pathlib import Path

from .models import parse_ts


def _n(x: float) -> float:
    return .5 * (1 + erf(x / sqrt(2)))


def _pdf(x: float) -> float:
    return exp(-x * x / 2) / sqrt(2 * pi)


@dataclass(frozen=True)
class EuropeanGreeks:
    price: float
    delta: float
    gamma: float
    theta_per_calendar_day: float
    vega_per_vol_point: float
    rho_per_rate_point: float


def european_bs(spot: float, strike: float, years: float, sigma: float,
                right: str, rate: float, dividend_yield: float) -> EuropeanGreeks:
    values = (spot, strike, years, sigma, rate, dividend_yield)
    if not all(isfinite(v) for v in values) or min(spot, strike, years, sigma) <= 0:
        raise ValueError('European Greeks require finite positive prices, time and volatility')
    if right not in {'C', 'P'}:
        raise ValueError('Option right must be C or P')
    st = sigma * sqrt(years)
    d1 = (log(spot / strike) + (rate - dividend_yield + sigma ** 2 / 2) * years) / st
    d2 = d1 - st
    df_q, df_r = exp(-dividend_yield * years), exp(-rate * years)
    if right == 'C':
        price = spot * df_q * _n(d1) - strike * df_r * _n(d2)
        delta = df_q * _n(d1)
        theta_year = (-spot * df_q * _pdf(d1) * sigma / (2 * sqrt(years))
                      - rate * strike * df_r * _n(d2)
                      + dividend_yield * spot * df_q * _n(d1))
        rho = strike * years * df_r * _n(d2)
    else:
        price = strike * df_r * _n(-d2) - spot * df_q * _n(-d1)
        delta = -df_q * _n(-d1)
        theta_year = (-spot * df_q * _pdf(d1) * sigma / (2 * sqrt(years))
                      + rate * strike * df_r * _n(-d2)
                      - dividend_yield * spot * df_q * _n(-d1))
        rho = -strike * years * df_r * _n(-d2)
    gamma = df_q * _pdf(d1) / (spot * st)
    vega = spot * df_q * _pdf(d1) * sqrt(years)
    return EuropeanGreeks(price, delta, gamma, theta_year / 365,
                          vega * .01, rho * .01)


def solve_iv(mid: float, spot: float, strike: float, years: float,
             right: str, rate: float, dividend_yield: float) -> float | None:
    """Invert European BS for quote mid, returning None if no stable solution.

    A monotone price function in sigma is bracketed then bisected. This inversion
    cannot prove option prices or mid fills are executable.
    """
    if not isfinite(mid) or mid <= 0:
        return None
    try:
        low, high = 0.00001, 5.0
        p_low = european_bs(spot, strike, years, low, right, rate, dividend_yield).price
        p_high = european_bs(spot, strike, years, high, right, rate, dividend_yield).price
        if not p_low + 1e-8 < mid < p_high - 1e-8:
            return None
        for _ in range(90):
            sigma = (low + high) / 2
            p_mid = european_bs(spot, strike, years, sigma, right, rate, dividend_yield).price
            if p_mid < mid:
                low = sigma
            else:
                high = sigma
        return (low + high) / 2
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


INPUT = ('quote_ts', 'spot_ts', 'decision_ts', 'expiry_ts', 'option_symbol', 'right',
         'spot', 'strike', 'bid', 'ask', 'rate', 'rate_observed_at', 'dividend_yield')
OUTPUT = list(INPUT) + ['iv', 'delta', 'gamma', 'theta_per_calendar_day',
                        'vega_per_vol_point', 'rho_per_rate_point', 'greek_provider',
                        'delta_ts', 'model_name', 'data_classification']


def _compute_row(row: dict[str, str], max_spot_quote_skew_seconds: int = 60) -> dict[str, str]:
    quote_ts = parse_ts(row['quote_ts'])
    spot_ts = parse_ts(row['spot_ts'])
    decision_ts = parse_ts(row['decision_ts'])
    expiry_ts = parse_ts(row['expiry_ts'])
    rate_ts = parse_ts(row['rate_observed_at'])
    if not spot_ts <= quote_ts <= decision_ts or not rate_ts <= quote_ts:
        raise ValueError('Future-dated spot, option quote, or risk-free rate: look-ahead leak')
    if abs((spot_ts - quote_ts).total_seconds()) > max_spot_quote_skew_seconds:
        raise ValueError('Underlying spot and option quote observations are misaligned')
    if (decision_ts - quote_ts).total_seconds() > 90:
        raise ValueError('Option quote is too stale for minute-level research')
    if (expiry_ts - decision_ts).total_seconds() <= 20 * 60:
        raise ValueError('Insufficient expiry buffer for research Greek')
    # Do not assume daily EOD chain data is intraday just because a date was supplied.
    if any('T' not in row[k] and ' ' not in row[k] for k in ('quote_ts', 'spot_ts', 'decision_ts')):
        raise ValueError('Quote timestamps need explicit intraday times')
    vals = {k: float(row[k]) for k in ('spot', 'strike', 'bid', 'ask', 'rate', 'dividend_yield')}
    if not all(isfinite(x) for x in vals.values()):
        raise ValueError('Nonfinite research input')
    if not 0 < vals['bid'] <= vals['ask']:
        raise ValueError('Invalid two-sided option bid/ask')
    if not 0 < vals['spot'] or not 0 < vals['strike']:
        raise ValueError('Invalid underlying price or strike')
    if abs(vals['rate']) > 1 or abs(vals['dividend_yield']) > 1:
        raise ValueError('Rates must be decimals rather than percent and be plausible')
    from zoneinfo import ZoneInfo
    ny = ZoneInfo('America/New_York')
    if expiry_ts.astimezone(ny).date() != quote_ts.astimezone(ny).date():
        raise ValueError('0DTE research requires expiry on the quote trading date')
    years = (expiry_ts - quote_ts).total_seconds() / (365 * 86400)
    iv = solve_iv((vals['bid'] + vals['ask']) / 2, vals['spot'], vals['strike'], years,
                  row['right'], vals['rate'], vals['dividend_yield'])
    if iv is None:
        raise ValueError('No stable European implied volatility for this option midpoint')
    greeks = european_bs(vals['spot'], vals['strike'], years, iv, row['right'],
                         vals['rate'], vals['dividend_yield'])
    return {**row, 'iv': f'{iv:.9f}', 'delta': f'{greeks.delta:.9f}',
            'gamma': f'{greeks.gamma:.9f}',
            'theta_per_calendar_day': f'{greeks.theta_per_calendar_day:.9f}',
            'vega_per_vol_point': f'{greeks.vega_per_vol_point:.9f}',
            'rho_per_rate_point': f'{greeks.rho_per_rate_point:.9f}',
            'greek_provider': 'local_bs_research', 'delta_ts': quote_ts.isoformat(),
            'model_name': 'european_black_scholes_continuous_dividend_approx',
            'data_classification': 'RESEARCH_ONLY_NOT_EXECUTION_VERIFIED'}


def enrich_research_csv(source: str, output: str, reject_file: str | None = None) -> dict:
    """Enrich real two-sided quote inputs with local Greeks; never label them trusted.

    Invalid rows are rejected into a separate report; output may be incomplete.
    """
    source_path, output_path = Path(source), Path(output)
    if source_path.resolve() == output_path.resolve():
        raise ValueError('Refuse to overwrite original observations')
    if reject_file and Path(reject_file).resolve() in {source_path.resolve(), output_path.resolve()}:
        raise ValueError('Reject report must not overwrite input or output')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    count = 0
    with source_path.open(newline='', encoding='utf-8') as src, output_path.open('w', newline='', encoding='utf-8') as dst:
        reader = csv.DictReader(src)
        if not reader.fieldnames or set(INPUT) - set(reader.fieldnames):
            raise ValueError('Missing research quote columns: ' + str(sorted(set(INPUT) - set(reader.fieldnames or []))))
        writer = csv.DictWriter(dst, fieldnames=list(dict.fromkeys([*reader.fieldnames, *OUTPUT])), extrasaction='ignore')
        writer.writeheader()
        for i, row in enumerate(reader, start=2):
            try:
                writer.writerow(_compute_row(row))
                count += 1
            except (ValueError, OverflowError, ZeroDivisionError) as exc:
                errors.append({'line': i, 'reason': str(exc)})
    report = {'source': source, 'output': output, 'enriched_rows': count,
              'rejected_rows': len(errors), 'classification': 'research_only_not_trusted',
              'not_a_validated_historical_options_dataset': True,
              'rejections': errors[:25]}
    if reject_file:
        import json
        dest = Path(reject_file)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
