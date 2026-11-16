"""Regression tests for v0.3 auditability and adverse-state experiments."""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from zerodte.adversarial import perturb
from zerodte.audit_ledger import DecisionLedger, verify_ledger
from zerodte.config import Settings
from zerodte.engine import StrategyEngine
from zerodte.models import Signal
from zerodte.source_audit import analyze_python_source
from zerodte.statistics import drawdown_profile, validate_session_pnl, from_trades
from test_core import T, frame


class LedgerTests(unittest.TestCase):
    def test_valid_chain_and_append_existing(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "trace.jsonl"
            with DecisionLedger(file) as log:
                log.append("signal", {"delta": .75, "symbol": "SPY"})
                log.append("no_trade", {"reason": "liquidity"})
            with DecisionLedger(file) as log:
                log.append("close", {"pnl_cents": -4030})
            report = verify_ledger(file)
            self.assertTrue(report["verified"])
            self.assertEqual(report["count"], 3)

    def test_tampering_detected(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "trace.jsonl"
            with DecisionLedger(file) as log:
                log.append("entry", {"qty": 1})
                log.append("exit", {"qty": 1})
            changed = file.read_text().replace('"qty":1', '"qty":9', 1)
            file.write_text(changed)
            self.assertFalse(verify_ledger(file)["verified"])
            with self.assertRaises(ValueError):
                DecisionLedger(file)

    def test_truncation_detected(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "trace.jsonl"
            with DecisionLedger(file) as log:
                log.append("one", {"reason": "ok"})
            file.write_bytes(file.read_bytes()[:-1])
            self.assertEqual(verify_ledger(file)["error"], "truncated_record")

    def test_nonfinite_values_rejected(self):
        with TemporaryDirectory() as folder:
            with DecisionLedger(Path(folder) / "log") as log:
                with self.assertRaises(ValueError):
                    log.append("bad", {"pnl": float("nan")})


class StaticAuditTests(unittest.TestCase):
    def test_detects_future_shift_and_global_fit_review(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "research.py"
            file.write_text('''def train(df, scaler):
    target = df["price"].shift(-1)
    feats = scaler.fit_transform(df)
    centered = df["price"].rolling(3, center=True).mean()
    return target, feats, centered
''')
            rules = {x["rule"] for x in analyze_python_source(file)}
            self.assertIn("future_shift_review", rules)
            self.assertIn("fit_split_scope_review", rules)
            self.assertIn("centered_rolling_future_review", rules)

    def test_flags_shadowed_definition(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "shadow.py"
            file.write_text('def v():\n    return 1\ndef v():\n    return 2\n')
            self.assertIn("duplicate_top_level_definition",
                          {f["rule"] for f in analyze_python_source(file)})


class StressTests(unittest.TestCase):
    def test_deterministic_jitter_never_creates_crossed_market(self):
        f = frame()
        a = perturb(f, mode="random_execution_degradation", rng=Random(8))
        b = perturb(f, mode="random_execution_degradation", rng=Random(8))
        self.assertEqual(a, b)
        for quote in a.quotes:
            self.assertGreater(quote.bid, 0)
            self.assertGreaterEqual(quote.ask, quote.bid)

    def test_liquidity_crisis_is_quote_shock_not_underlying_lookahead(self):
        # T is 11am NY; simulated shock affects quote but not bar or timestamp.
        f = frame()
        out = perturb(f, mode="liquidity_crisis", rng=Random(1))
        self.assertEqual(out.bar, f.bar)
        self.assertEqual(out.quotes[0].ts, f.quotes[0].ts)
        self.assertLess(out.quotes[0].bid, f.quotes[0].bid)
        self.assertEqual(out.quotes[0].volume, 0)

    def test_latency_delay_two_extra_observed_frames(self):
        c = Settings(allow_model_gate=False, greek_policy="experimental", entry_delay_bars=3)
        bot = StrategyEngine(c)
        bot.last_day["SPY"] = "2026-10-26"
        bot.pending["SPY"] = Signal("SPY", "C", "C:standard", T, 2.1, .002)
        bot.pending_bars_remaining["SPY"] = 3
        bot.on_frame(frame(T + timedelta(minutes=1)))
        self.assertIsNone(bot.position)
        bot.on_frame(frame(T + timedelta(minutes=2)))
        self.assertIsNone(bot.position)
        bot.on_frame(frame(T + timedelta(minutes=3)))
        self.assertIsNotNone(bot.position)

    def test_aged_signal_never_crosses_expiry_session(self):
        c = Settings(allow_model_gate=False, greek_policy="experimental", entry_delay_bars=10)
        bot = StrategyEngine(c)
        bot.on_frame(frame(T))
        bot.pending["SPY"] = Signal("SPY", "C", "C:standard", T, 2.1, .002)
        bot.pending_bars_remaining["SPY"] = 10
        next_day = T + timedelta(days=1)
        bot.on_frame(frame(next_day, expiry=date(2026, 10, 27)))
        self.assertIsNone(bot.position)

    def test_decimal_accounting_and_rejection_reason(self):
        bot = StrategyEngine(Settings(allow_model_gate=False, greek_policy="experimental"))
        bot.last_day["SPY"] = "2026-10-26"
        sig = Signal("SPY", "C", "C:standard", T, 2.1, .002)
        bot.pending["SPY"] = sig
        bot.on_frame(frame(T + timedelta(minutes=1)))
        bot.on_frame(frame(T + timedelta(minutes=2), option_bid=1.1, option_ask=1.2))
        self.assertIsInstance(bot.daily_realized["2026-10-26"], Decimal)
        self.assertEqual(bot.daily_realized["2026-10-26"], Decimal("-101.30"))
        bot.pending["SPY"] = sig
        bot.daily_realized["2026-10-26"] = Decimal("-200")
        bot.on_frame(frame(T + timedelta(minutes=3)))
        self.assertEqual(bot.last_entry_reject_reason, "daily_realized_loss_limit")


class StatisticalTests(unittest.TestCase):
    def test_reproducible_bootstrap(self):
        seq = [1, -1, 2, -2, 0, 3, -3, 4, -4, 0] * 3
        a = validate_session_pnl(seq, block=5, replications=200, seed=80)
        b = validate_session_pnl(seq, block=5, replications=200, seed=80)
        self.assertEqual(a, b)
        self.assertFalse(a["can_promote_to_live"])

    def test_drawdown_and_unresolved_recovery(self):
        profile = drawdown_profile([100, -50, -60, 20])
        self.assertEqual(profile["max_closed_session_drawdown_usd"], -110)
        self.assertGreater(profile["unresolved_drawdown_sessions"], 0)

    def test_invalid_nonfinite_bootstrap(self):
        with self.assertRaises(ValueError):
            validate_session_pnl([1, float("nan")], block=1, replications=100)

    def test_no_trade_dates_included(self):
        result = from_trades([], [date(2026, 10, 26), date(2026, 10, 27)], 1, 100, 3)
        self.assertEqual(result["zero_trade_sessions"], 2)
        self.assertEqual(result["mean_daily_pnl_usd"], 0)


if __name__ == "__main__":
    unittest.main()
