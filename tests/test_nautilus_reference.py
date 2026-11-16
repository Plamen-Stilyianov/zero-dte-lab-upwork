"""No external NautilusTrader dependency required for adapter contract tests."""
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import csv
import sys

from zerodte.data import read_frames
from zerodte.nautilus_reference import checked_nautilus_delta, crosscheck_csv
from test_core import T


@contextmanager
def mocked_nautilus(value=.8):
    root = ModuleType("nautilus_trader")
    model = ModuleType("nautilus_trader.model")
    observed = []

    def calc(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(delta=value)

    model.imply_vol_and_greeks = calc
    with patch.dict(sys.modules, {"nautilus_trader": root, "nautilus_trader.model": model}):
        yield observed


class NautilusAdapterTests(TestCase):
    def test_explicit_carry_and_bid_ask_mid(self):
        with mocked_nautilus(-.78) as observed:
            delta = checked_nautilus_delta(650, 655, 5, "P", T, interest_rate=.04,
                                           dividend_yield=.01)
        self.assertEqual(delta, -.78)
        self.assertAlmostEqual(observed[0]["b"], .03)
        self.assertFalse(observed[0]["is_call"])
        self.assertEqual(observed[0]["price"], 5)

    def test_terminal_window_has_no_model_delta(self):
        with mocked_nautilus() as observed:
            end = T.replace(hour=19, minute=50)  # 15:50 ET
            self.assertIsNone(checked_nautilus_delta(650, 649, 2, "C", end))
            self.assertFalse(observed)

    def test_csv_crosscheck_records_reference_timestamp_and_source(self):
        with TemporaryDirectory() as tmp:
            src, dst = Path(tmp)/"base.csv", Path(tmp)/"checked.csv"
            row = dict(ts=T.isoformat(), underlying="SPY", close=650, high=651, low=649,
                       volume=2000, option_symbol="SPY261026C00649000",
                       expiry="2026-10-26", right="C", strike=649, bid=2,
                       ask=2.06, option_volume=250, quote_ts=T.isoformat(), delta=.8,
                       greek_provider="thetadata", delta_ts=T.isoformat())
            with src.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(row))
                w.writeheader()
                w.writerow(row)
            with mocked_nautilus() as calls:
                out = crosscheck_csv(str(src), str(dst))
            self.assertEqual(out["independent_model_estimates"], 1)
            quotes = list(read_frames(str(dst)))
            self.assertEqual(quotes[0].quotes[0].reference_provider, "nautilus_local")
            self.assertEqual(quotes[0].quotes[0].reference_delta, .8)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
