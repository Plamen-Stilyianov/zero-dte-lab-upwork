"""Intraday model estimate of Black-Scholes delta when no sourced delta is present.

This is a research approximation for American-style ETF options; dividend/early-exercise,
underlying quote misalignment, discrete ticks and near-expiry gamma can cause errors.
Fail closed if IV cannot be inferred from an actual quoted premium.
"""
from __future__ import annotations

from datetime import datetime, time
from math import erf, exp, log, sqrt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def _phi(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def _price_delta(spot: float, strike: float, t: float, sigma: float, right: str,
                 interest: float = 0.04, yield_: float = 0.0) -> tuple[float, float]:
    if min(spot, strike, t, sigma) <= 0:
        raise ValueError("Invalid pricing input")
    srt = sigma * sqrt(t)
    d1 = (log(spot / strike) + (interest - yield_ + sigma * sigma / 2) * t) / srt
    d2 = d1 - srt
    if right == "C":
        return (spot * exp(-yield_ * t) * _phi(d1) - strike * exp(-interest * t) * _phi(d2),
                exp(-yield_ * t) * _phi(d1))
    if right == "P":
        return (strike * exp(-interest * t) * _phi(-d2) - spot * exp(-yield_ * t) * _phi(-d1),
                -exp(-yield_ * t) * _phi(-d1))
    raise ValueError("Unknown right")


def estimated_delta(spot: float, strike: float, mid: float, right: str, ts: datetime,
                    interest: float = 0.04) -> float | None:
    if ts.tzinfo is None or min(spot, strike, mid) <= 0:
        return None
    local = ts.astimezone(NY)
    expiry_time = datetime.combine(local.date(), time(16, 0), tzinfo=NY)
    seconds = (expiry_time - local).total_seconds()
    if seconds <= 20 * 60:
        return None
    t = seconds / (365.25 * 86400)
    intrinsic = max(spot - strike, 0) if right == "C" else max(strike - spot, 0)
    if mid < intrinsic - 0.03 or mid > spot * 1.05:
        return None
    lo, hi = 0.01, 5.0
    try:
        p_lo, _ = _price_delta(spot, strike, t, lo, right, interest)
        p_hi, _ = _price_delta(spot, strike, t, hi, right, interest)
        if not p_lo <= mid <= p_hi:
            return None
        for _ in range(70):
            sigma = (lo + hi) / 2
            p, _ = _price_delta(spot, strike, t, sigma, right, interest)
            if p < mid:
                lo = sigma
            else:
                hi = sigma
        _, d = _price_delta(spot, strike, t, (lo + hi) / 2, right, interest)
        return d
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
