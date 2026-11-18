"""Fuzz-shaped edge cases and broker-data corruption rejection; deterministic seeds."""
import csv
from datetime import date, timedelta
from math import nan, inf
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from zerodte.config import Settings
from zerodte.data import read_frames
from zerodte.models import OptionQuote
from test_core import T, frame
from zerodte.engine import StrategyEngine


class AdversarialTests(unittest.TestCase):
    def test_nonfinite_risk_settings_fail_closed(self):
        for field in ("equity_usd", "daily_loss_limit_usd", "max_risk_fraction", "max_spread"):
            for bad in (nan, inf, -inf):
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    Settings(**{field: bad})

    def test_bad_quotes_rejected(self):
        for bid, ask in ((nan, 3.1), (3, nan), (3, 2), (-1, 2), (0, 0), (inf, inf)):
            with self.subTest(bid=bid, ask=ask), self.assertRaises(ValueError):
                OptionQuote(T, "O", "SPY", date(2026, 10, 26), "C", 649, bid, ask, .8, 20)

    def test_random_fuzz_does_not_bypass_position_limit(self):
        random = Random(101)
        bot = StrategyEngine(Settings(allow_model_gate=False, greek_policy="experimental"))
        for i in range(500):
            ts = T + timedelta(minutes=i)
            # Arbitrarily bad bid paths; entry requires completed bar signals.
            value = random.uniform(.01, 10)
            f = frame(now=ts, option_bid=value, option_ask=value + .05, volume=random.randint(100, 100000))
            bot.on_frame(f)
            self.assertLessEqual(int(bot.position is not None), 1)
            if bot.position:
                self.assertGreater(bot.position.qty, 0)
                self.assertLessEqual(bot.position.qty, bot.c.max_contracts)

    def test_missing_delta_column_does_not_silently_report_zero_trades(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "tape.csv"
            with path.open("w", newline="") as f:
                names = ["ts", "underlying", "close", "high", "low", "volume",
                         "option_symbol", "expiry", "right", "strike", "bid", "ask",
                         "option_volume", "quote_ts"]
                writer = csv.DictWriter(f, fieldnames=names)
                writer.writeheader()
                writer.writerow({"ts": T.isoformat(), "underlying": "SPY", "close": 650,
                                 "high": 651, "low": 649, "volume": 2000, "option_symbol": "O",
                                 "expiry": "2026-10-26", "right": "C", "strike": 649,
                                 "bid": 2, "ask": 2.05, "option_volume": 200,
                                 "quote_ts": T.isoformat()})
            with self.assertRaises(ValueError):
                list(read_frames(str(path), "provided"))


if __name__ == "__main__":
    unittest.main()
