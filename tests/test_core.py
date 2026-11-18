import unittest
from datetime import date, datetime, timedelta, timezone

from zerodte.config import Settings
from zerodte.engine import StrategyEngine
from zerodte.greeks import estimated_delta
from zerodte.learn import regime_permitted
from zerodte.models import Bar, Frame, OptionQuote, Signal, Trade
from zerodte.signal import TrendSignal

T = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)  # 11:00am ET


def frame(now=T, price=650, option_bid=2.00, option_ask=2.06,
          delta=0.80, volume=20000, quote_ts=None, expiry=date(2026, 10, 26)):
    bar = Bar(now, "SPY", price, price + 0.05, price - 0.05, volume)
    q = OptionQuote(quote_ts or now, "SPY261026C00649000", "SPY", expiry,
                    "C", 649.0, option_bid, option_ask, delta, 100, 100,
                    "synthetic", quote_ts or now)
    return Frame(bar, (q,))


class ConfigTests(unittest.TestCase):
    def test_stop_rejects_wider_than_40_cents(self):
        with self.assertRaises(ValueError):
            Settings(stop_premium=0.75)

    def test_multiplier_rejected(self):
        with self.assertRaises(ValueError):
            OptionQuote(T, "BAD", "SPY", date(2026, 10, 26), "C", 649, 2, 2.1, .8, 50, 10)

    def test_bad_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            Bar(datetime(2026, 10, 26), "SPY", 650, 651, 649, 100)

    def test_0dte_delta_model_can_fail_closed(self):
        d = estimated_delta(650, 649, 2.00, "C", T)
        self.assertTrue(d is None or 0 <= d <= 1)
        later = datetime(2026, 10, 26, 19, 59, tzinfo=timezone.utc)
        self.assertIsNone(estimated_delta(650, 649, 2.00, "C", later))


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.c = Settings(equity_usd=25000, allow_model_gate=False, greek_policy="experimental")
        self.bot = StrategyEngine(self.c)
        self.bot.last_day["SPY"] = "2026-10-26"
        self.sig = Signal("SPY", "C", "C:standard", T, 2.1, .002)

    def test_no_trade_without_signal(self):
        self.bot.on_frame(frame())
        self.assertIsNone(self.bot.position)

    def test_entry_requires_next_frame(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        self.assertIsNotNone(self.bot.position)
        self.assertEqual(self.bot.position.entry_price, 2.08)

    def test_spread_and_delta_filters(self):
        self.assertFalse(self.bot._eligible(frame(option_bid=1.0, option_ask=1.25).quotes[0], self.sig, T))
        self.assertFalse(self.bot._eligible(frame(delta=.65).quotes[0], self.sig, T))
        self.assertFalse(self.bot._eligible(frame(delta=None).quotes[0], self.sig, T))
        self.assertFalse(self.bot._eligible(frame(expiry=date(2026, 10, 27)).quotes[0], self.sig, T))

    def test_stale_quote(self):
        q = frame(quote_ts=T - timedelta(minutes=5)).quotes[0]
        self.assertFalse(self.bot._eligible(q, self.sig, T))

    def test_stop_is_not_guarantee(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        self.assertAlmostEqual(self.bot.position.current_stop, 1.68)
        # Quote gaps through stop: fill BELOW stop; proper adverse slippage.
        self.bot.on_frame(frame(T + timedelta(minutes=2), option_bid=1.1, option_ask=1.16))
        self.assertEqual(self.bot.trades[0].exit_price, 1.08)
        self.assertLess(self.bot.trades[0].pnl, -40)

    def test_trail_only_tightens(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        self.bot.on_frame(frame(T + timedelta(minutes=2), option_bid=2.85, option_ask=2.91))
        self.assertGreater(self.bot.position.current_stop, 2.08)
        new_stop = self.bot.position.current_stop
        self.bot.on_frame(frame(T + timedelta(minutes=3), option_bid=2.8, option_ask=2.86))
        self.assertGreaterEqual(self.bot.position.current_stop, new_stop)

    def test_no_late_entry(self):
        self.bot.pending["SPY"] = self.sig
        late = datetime(2026, 10, 26, 19, 5, tzinfo=timezone.utc)  # 15:05 ET
        self.bot.on_frame(frame(late))
        self.assertIsNone(self.bot.position)

    def test_force_exit(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        exit_ts = datetime(2026, 10, 26, 19, 30, tzinfo=timezone.utc)
        self.bot.on_frame(frame(exit_ts))
        self.assertEqual(self.bot.trades[0].reason, "forced_intraday_exit")

    def test_unclosed_marked_incomplete(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        self.bot.finalize()
        self.assertTrue(self.bot.incomplete)

    def test_daily_risk_fails_closed(self):
        self.bot.pending["SPY"] = self.sig
        self.bot.daily_realized["2026-10-26"] = -150
        self.bot.on_frame(frame(T + timedelta(minutes=1)))
        self.assertIsNone(self.bot.position)

    def test_zero_bid_quote_stops_out_at_zero_and_blocks_new_entry(self):
        # New entries must never buy a zero-bid quote
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=1), option_bid=0.0, option_ask=0.05))
        self.assertIsNone(self.bot.position)
        self.assertEqual(self.bot.last_entry_reject_reason, "no_eligible_contract_or_greek")

        # An open position receiving bid=0.0 must stop out at fill=0.0
        self.bot.pending["SPY"] = self.sig
        self.bot.on_frame(frame(T + timedelta(minutes=2), option_bid=2.45, option_ask=2.50))
        self.assertIsNotNone(self.bot.position)
        self.bot.on_frame(frame(T + timedelta(minutes=3), option_bid=0.0, option_ask=0.05))
        self.assertIsNone(self.bot.position)
        self.assertEqual(len(self.bot.trades), 1)
        self.assertEqual(self.bot.trades[0].exit_price, 0.0)
        self.assertEqual(self.bot.trades[0].reason, "stop_or_trailing")

    def test_day_rollover_closes_open_position_on_prior_session_quote(self):
        self.bot.pending["SPY"] = self.sig
        entry_ts = T + timedelta(minutes=1)
        self.bot.on_frame(frame(entry_ts, option_bid=2.45, option_ask=2.50))
        self.assertIsNotNone(self.bot.position)

        # Next trading day arrives with a new contract symbol (yesterday's contract absent)
        next_day_ts = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
        next_day_quote = OptionQuote(
            next_day_ts, "SPY261027C00650000", "SPY", date(2026, 10, 27), "C", 650.0,
            2.45, 2.50, 0.78, 50, 100, "local_bs_research", next_day_ts
        )
        next_day_frame = Frame(Bar(next_day_ts, "SPY", 650.0, 650.1, 649.9, 1000), (next_day_quote,))
        self.bot.on_frame(next_day_frame)

        self.assertTrue(self.bot.incomplete)
        self.assertIsNone(self.bot.position)
        self.assertEqual(len(self.bot.trades), 1)
        self.assertEqual(self.bot.trades[0].exit_time, entry_ts)
        self.assertEqual(self.bot.trades[0].reason, "day_rollover_incomplete_close")
        self.assertIn("2026-10-26", self.bot.daily_realized)
        self.assertNotIn("2026-10-27", self.bot.daily_realized)

    def test_walk_forward_rejects_incomplete_training_tape(self):
        import tempfile
        from unittest.mock import patch
        from zerodte.validation import run_holdout
        from zerodte.rolling import run_rolling

        d1_sig = datetime(2026, 10, 26, 14, 59, tzinfo=timezone.utc)
        d1_entry = datetime(2026, 10, 26, 15, 0, tzinfo=timezone.utc)
        d2 = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
        d3 = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)
        d4 = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)

        def make_day_frame(ts: datetime, day_date: date, sym: str) -> Frame:
            q = OptionQuote(ts, sym, "SPY", day_date, "C", 650.0, 2.45, 2.50, 0.78, 50, 100, "thetadata", ts, 0.78, ts, "orats")
            return Frame(Bar(ts, "SPY", 650.0, 650.1, 649.9, 1000), (q,))

        f1a = make_day_frame(d1_sig, date(2026, 10, 26), "SPY261026C00650000")
        f1b = make_day_frame(d1_entry, date(2026, 10, 26), "SPY261026C00650000")
        f2 = make_day_frame(d2, date(2026, 10, 27), "SPY261027C00650000")
        f3 = make_day_frame(d3, date(2026, 10, 28), "SPY261028C00650000")
        f4 = make_day_frame(d4, date(2026, 10, 29), "SPY261029C00650000")

        orig_on_frame = StrategyEngine.on_frame
        def seeded_on_frame(eng: StrategyEngine, fr: Frame) -> None:
            orig_on_frame(eng, fr)
            if fr is f1a:
                eng.pending["SPY"] = Signal(underlying="SPY", right="C", regime="C:standard", volume_ratio=2.5, strength=1.0, observed_at=d1_sig)
                eng.pending_bars_remaining["SPY"] = 1

        frames = [f1a, f1b, f2, f3, f4]
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("zerodte.validation.read_frames", side_effect=lambda *a, **kw: iter(frames)), \
             patch("zerodte.rolling.read_frames", side_effect=lambda *a, **kw: iter(frames)), \
             patch.object(StrategyEngine, "on_frame", seeded_on_frame):
            with self.assertRaisesRegex(ValueError, "Training tape is incomplete"):
                run_holdout("unused.csv", Settings(), date(2026, 10, 27), date(2026, 10, 28), tmpdir)
            with self.assertRaisesRegex(ValueError, "Training tape is incomplete"):
                run_rolling("unused.csv", Settings(), 2, 1, 1, 1, tmpdir, embargo_sessions=0)


class LearningTests(unittest.TestCase):
    def test_only_prior_dates_count(self):
        exit_day = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)
        trade = Trade("O", "SPY", "C", "C:standard", exit_day - timedelta(minutes=5),
                      exit_day, 2, 1, 1, -101.3, "stop", .8, 2.1)
        trades = [trade] * 30
        self.assertTrue(regime_permitted("C:standard", trades, date(2026, 10, 26), 30, 0))
        self.assertFalse(regime_permitted("C:standard", trades, date(2026, 10, 27), 30, 0))


class TrendTests(unittest.TestCase):
    def test_no_signal_before_lookback(self):
        trend = TrendSignal(Settings())
        for n in range(18):
            b = Bar(T + timedelta(minutes=n), "SPY", 650 + n / 10,
                    650 + n / 10 + .05, 650 + n / 10 - .05, 1000)
            self.assertIsNone(trend.on_bar(b))


if __name__ == "__main__":
    unittest.main()
