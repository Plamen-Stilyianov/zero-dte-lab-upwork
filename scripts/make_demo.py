"""Create clearly synthetic option-market test data, NEVER backtest proof."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
FIELDNAMES = ["ts", "underlying", "close", "high", "low", "volume",
              "option_symbol", "expiry", "right", "strike", "bid", "ask",
              "option_volume", "quote_ts", "delta", "greek_provider", "delta_ts"]


def make(path: str = "data/SYNTHETIC_demo.csv", days: int = 5) -> None:
    rng = Random(9010)
    out = Path(path)
    out.parent.mkdir(exist_ok=True, parents=True)
    d = date(2026, 10, 26)
    with out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        generated = 0
        while generated < days:
            if d.weekday() >= 5:
                d += timedelta(days=1)
                continue
            price = 650.0
            for minute in range(390):
                start = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY)
                ts = (start + timedelta(minutes=minute + 1)).astimezone(timezone.utc).isoformat()
                movement = 0.016 + rng.uniform(-0.035, 0.035)
                if 65 <= minute % 120 <= 68:
                    movement += 0.25
                old = price
                price += movement
                high, low = max(old, price) + 0.01, min(old, price) - 0.01
                v = rng.randint(10000, 18000) if minute % 120 not in (66, 67, 68) else 42000
                for side, strike, base_delta in (("C", 649.0, 0.8), ("P", 651.0, -0.8)):
                    symbol = f"SPY{d:%y%m%d}{side}{round(strike * 1000):08d}"
                    intrinsic = max(price - strike, 0) if side == "C" else max(strike - price, 0)
                    # Controlled illustration of bid/ask stop logic, not traded data.
                    premium = max(intrinsic + 0.04, 2.5 + (price - 650) * base_delta)
                    bid = max(0.01, round(premium - 0.03, 2))
                    ask = round(bid + 0.06, 2)
                    writer.writerow({"ts": ts, "underlying": "SPY", "close": round(price, 3),
                                     "high": round(high, 3), "low": round(low, 3), "volume": v,
                                     "option_symbol": symbol, "expiry": d.isoformat(),
                                     "right": side, "strike": strike, "bid": bid, "ask": ask,
                                     "option_volume": 250, "quote_ts": ts, "delta": base_delta,
                                     "greek_provider": "synthetic", "delta_ts": ts})
            d += timedelta(days=1)
            generated += 1
    print(f"Wrote {out} [SYNTHETIC; not a profitability test]")


if __name__ == "__main__":
    make()
