"""Export comparable daily *net* returns from COMPLETE research trade reports.

Daily closed P&L / constant research capital is a fixed-capital proxy, not
mark-to-market daily NAV for multi-day positions. ZeroDTE positions are expected
to open and close within their own session. A separate session calendar built
from the underlying market tape makes non-trading days explicit.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo


def _read_trade_report(path: Path, days: list[date], capital: Decimal,
                       timezone: str) -> list[Decimal]:
    summary_file = path.parent / "summary.json"
    if not summary_file.exists():
        raise ValueError(f"Missing completion summary for {path}")
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    if not summary.get("complete_tape", False):
        raise ValueError(f"Incomplete trading tape; cannot infer from {path}")
    zone = ZoneInfo(timezone)
    daily: dict[date, Decimal] = {day: Decimal(0) for day in days}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not {"entry_time", "exit_time", "pnl"}.issubset(reader.fieldnames):
            raise ValueError(f"Malformed trades.csv: {path}")
        count = 0
        for row in reader:
            if not row["exit_time"] or not row["entry_time"]:
                raise ValueError("Incomplete entry/exit timestamps")
            entry = datetime.fromisoformat(row["entry_time"].replace("Z", "+00:00"))
            exit_ = datetime.fromisoformat(row["exit_time"].replace("Z", "+00:00"))
            if entry.utcoffset() is None or exit_.utcoffset() is None:
                raise ValueError("Trade timestamps must include explicit offsets")
            day = exit_.astimezone(zone).date()
            if entry.astimezone(zone).date() != day:
                raise ValueError("An overnight position cannot be exported as closed-session 0DTE return")
            if day not in daily:
                raise ValueError(f"Trade date {day} absent from tape session calendar")
            try:
                pnl = Decimal(row["pnl"])
            except InvalidOperation as error:
                raise ValueError("Unparseable trade P&L") from error
            if not pnl.is_finite():
                raise ValueError("Nonfinite trade P&L")
            daily[day] += pnl
            count += 1
    if count != summary.get("trades"):
        raise ValueError("Trades CSV count disagrees with summary.json")
    if abs(sum(daily.values()) - Decimal(str(summary.get("pnl_usd_after_costs")))) > Decimal("0.011"):
        raise ValueError("Trade P&L total disagrees with summary.json")
    returns = [daily[d] / capital for d in days]
    if any(x <= -1 for x in returns):
        raise ValueError("Daily loss >=100% of research capital; invalid fixed-capital approximation")
    return returns


def export_returns(tape: str, config: str, variants: list[str], capital: str,
                   out: str, source: str = "provided") -> dict:
    from .config import load_settings
    from .rolling import session_calendar
    try:
        denominator = Decimal(capital)
    except InvalidOperation as error:
        raise ValueError("--capital must be a finite positive number") from error
    if not denominator.is_finite() or denominator <= 0:
        raise ValueError("--capital must be a finite positive number")
    conf = load_settings(config)
    days = session_calendar(tape, conf, source)
    if not days:
        raise ValueError("Tape has no recorded sessions")
    results: dict[str, list[Decimal]] = {}
    for entry in variants:
        if "=" not in entry:
            raise ValueError("--variant must be NAME=path/to/trades.csv")
        name, filename = entry.split("=", 1)
        name = name.strip()
        if not name or name in results:
            raise ValueError("Variant name missing or duplicated")
        results[name] = _read_trade_report(Path(filename), days, denominator, conf.timezone)
    if not results:
        raise ValueError("At least one --variant needed")
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["session", "strategy_id", "daily_return"])
        for i, day in enumerate(days):
            for name in results:
                writer.writerow([day.isoformat(), name, str(results[name][i])])
    return {"days": len(days), "strategies": list(results), "capital_usd": str(denominator),
            "output": str(target), "warnings": [
                "Daily closed realized P&L divided by fixed capital; not a full marked-to-market NAV account series.",
                "Completeness from local summary.json is only a structural claim, not third-party data validation.",
                "Results from the same dataset used for parameter selection are NOT independent holdout evidence."]}
