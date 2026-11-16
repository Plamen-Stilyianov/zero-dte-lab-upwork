"""OPTIONAL independent local European-BS cross-check using NautilusTrader.

Do not call this a validated 0DTE Greek source: SPY/QQQ are American-style,
close-bar spot is not tick-synchronized with the option quote, and dividends,
fast gamma and IV smile can affect the answer. Non-convergence => no reference.
"""
from __future__ import annotations

import csv
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .data import REQUIRED, PROVENANCE
from .models import parse_ts

FIELDS = list(REQUIRED) + ["delta", *PROVENANCE,
                           "reference_delta", "reference_delta_ts", "reference_provider"]
NY = ZoneInfo("America/New_York")


def checked_nautilus_delta(spot: float, strike: float, mid: float, right: str,
                           event: datetime, interest_rate: float = 0.04,
                           dividend_yield: float = 0.0) -> float | None:
    """Use the installed package's public low-level solver; do not silently fall back."""
    try:
        from nautilus_trader.model import imply_vol_and_greeks
    except ImportError as exc:
        raise RuntimeError("Install nautilus_trader separately for crosschecks") from exc
    if event.tzinfo is None or min(spot, strike, mid) <= 0 or right not in ("C", "P"):
        return None
    local = event.astimezone(NY)
    end = datetime.combine(local.date(), time(16), tzinfo=NY)
    remaining = (end - local).total_seconds()
    if remaining < 20 * 60:
        return None
    if not (0 <= interest_rate <= 0.25 and 0 <= dividend_yield <= 0.25):
        raise ValueError("Rate and dividend assumptions must be explicit and plausible")
    try:
        result = imply_vol_and_greeks(
            s=float(spot), r=float(interest_rate), b=float(interest_rate - dividend_yield),
            is_call=(right == "C"), k=float(strike), t=remaining/(365.25*86400),
            price=float(mid),
        )
        delta = float(result.delta)
        if not -1 <= delta <= 1:
            return None
        return delta
    except (ValueError, OverflowError, ArithmeticError):
        return None


def crosscheck_csv(source: str, output: str, interest_rate: float = .04,
                   dividend_yield: float = 0.0) -> dict:
    path = Path(output)
    if Path(source).resolve() == path.resolve():
        raise ValueError("Source and output must differ")
    path.parent.mkdir(parents=True, exist_ok=True)
    successful = 0
    attempted = 0
    with open(source, newline="", encoding="utf-8") as src, \
         path.open("w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        if not reader.fieldnames or set(FIELDS[:len(REQUIRED)+3]) - set(reader.fieldnames):
            raise ValueError("Source must be a canonical tape with delta, greek_provider and delta_ts")
        writer = csv.DictWriter(dst, fieldnames=FIELDS)
        writer.writeheader()
        for row in reader:
            attempted += 1
            if row.get("reference_delta"):
                raise ValueError("Existing independent references must not be silently overwritten")
            quote_at = parse_ts(row["quote_ts"])
            number = checked_nautilus_delta(float(row["close"]), float(row["strike"]),
                                            (float(row["bid"]) + float(row["ask"])) / 2,
                                            row["right"], quote_at,
                                            interest_rate, dividend_yield)
            if number is not None:
                row["reference_delta"] = str(number)
                row["reference_delta_ts"] = quote_at.isoformat()
                row["reference_provider"] = "nautilus_local"
                successful += 1
            writer.writerow({key: row.get(key, "") for key in FIELDS})
    return {"output": str(path), "greeks_attempted": attempted,
            "independent_model_estimates": successful,
            "warning": "European Black-Scholes approximation, close-bar underlying, explicit rates/dividend assumption; not independently verified market data."}
