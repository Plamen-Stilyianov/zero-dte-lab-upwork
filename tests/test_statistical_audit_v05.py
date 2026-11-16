"""v0.5 regression tests, including dangerous missing-data and dependence cases."""
import csv
from datetime import date, timedelta
import json
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest

from zerodte.statistical_audit import (load_return_panel, bootstrap_indices,
                                       adjust_pvalues, analyze_panel, audit_csv,
                                       probabilistic_sharpe, deflated_sharpe)
from zerodte.return_export import _read_trade_report


def create_panel(path, n=150, names=("alpha", "beta", "noise"), seed=404):
    rng = Random(seed)
    day = date(2025, 1, 1)
    persistent = 0.0
    with Path(path).open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["session", "strategy_id", "daily_return"])
        for _ in range(n):
            persistent = .70 * persistent + rng.gauss(0, .002)
            for index, name in enumerate(names):
                value = .001 * (index == 0) + persistent + rng.gauss(0, .001)
                writer.writerow([day.isoformat(), name, f"{value:.8f}"])
            day += timedelta(days=1)


class FWERTests(unittest.TestCase):
    def test_holm_and_bh(self):
        p = [.01, .04, .03]
        adjusted = adjust_pvalues(p)
        self.assertAlmostEqual(adjusted["holm"][0], .03)
        self.assertAlmostEqual(adjusted["holm"][1], .06)
        self.assertAlmostEqual(adjusted["holm"][2], .06)
        self.assertAlmostEqual(adjusted["benjamini_hochberg"][0], .03)
        self.assertAlmostEqual(adjusted["benjamini_hochberg"][2], .04)

    def test_declared_missing_trials_apply_conservative_family_allowance(self):
        a = adjust_pvalues([.01, .03])
        b = adjust_pvalues([.01, .03], declared_count=10)
        self.assertGreater(b["holm"][0], a["holm"][0])
        self.assertGreater(b["benjamini_hochberg"][0], a["benjamini_hochberg"][0])

    def test_invalid_p_values(self):
        for p in ([.1, float("nan")], [-.1], [1.1]):
            with self.assertRaises(ValueError):
                adjust_pvalues(p)


class BootstrapTests(unittest.TestCase):
    def test_reproducible_geometric_block_indices(self):
        a = bootstrap_indices(100, 8, Random(5), "stationary")
        b = bootstrap_indices(100, 8, Random(5), "stationary")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 100)
        self.assertGreater(sum(x == (y + 1) % 100 for x, y in zip(a[1:], a[:-1])), 40)

    def test_circular_block_contiguity(self):
        indices = bootstrap_indices(100, 7, Random(7), "circular")
        for start in range(0, 100, 7):
            piece = indices[start:start + 7]
            self.assertTrue(all(piece[i] == (piece[i-1] + 1) % 100 for i in range(1, len(piece))))

    def test_rejects_incomplete_or_duplicate_session(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"bad.csv"
            file.write_text("session,strategy_id,daily_return\n2025-01-01,x,0.01\n2025-01-02,y,0.02\n")
            with self.assertRaisesRegex(ValueError, "Incomplete aligned"):
                load_return_panel(file)
            file.write_text("session,strategy_id,daily_return\n2025-01-01,x,0.01\n2025-01-01,x,0.02\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_return_panel(file)

    def test_rejects_backwards_dates_and_invalid_returns(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"bad.csv"
            file.write_text("session,strategy_id,daily_return\n2025-01-02,x,0.01\n2025-01-01,x,0.02\n")
            with self.assertRaisesRegex(ValueError, "chronological"):
                load_return_panel(file)
            file.write_text("session,strategy_id,daily_return\n2025-01-01,x,nan\n")
            with self.assertRaisesRegex(ValueError, "Invalid daily"):
                load_return_panel(file)

    def test_report_seed_reproducible_no_go(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"panel.csv"
            create_panel(file)
            panel = load_return_panel(file)
            a = analyze_panel(panel, "alpha", iterations=200, seed=70)
            b = analyze_panel(panel, "alpha", iterations=200, seed=70)
            self.assertEqual(a, b)
            self.assertFalse(a["can_promote_to_live"])
            self.assertEqual(a["present_variants"], 3)
            self.assertEqual(len(a["variants"]), 3)
            self.assertIn("dsr_advisory", a["variants"][0])

    def test_stationary_and_circular_both_work(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"panel.csv"
            create_panel(file, n=90)
            panel = load_return_panel(file)
            stationary = analyze_panel(panel, "alpha", iterations=200, method="stationary")
            circular = analyze_panel(panel, "alpha", iterations=200, method="circular")
            self.assertNotEqual(stationary["variants"][0]["mean_daily_net_return_percentile_interval"],
                                circular["variants"][0]["mean_daily_net_return_percentile_interval"])
            self.assertTrue(stationary["variants"][0]["insufficient_session_count"])

    def test_constant_returns_are_degenerate_not_false_evidence(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"constant.csv"
            with file.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["session", "strategy_id", "daily_return"])
                for i in range(80):
                    writer.writerow([(date(2025,1,1)+timedelta(days=i)).isoformat(), "constant", "0.01"])
            report = analyze_panel(load_return_panel(file), "constant", iterations=200)
            self.assertEqual(report["variants"][0]["one_sided_centered_block_bootstrap_p"], 1.0)
            self.assertIsNone(report["variants"][0]["annualized_sharpe_naive"])
            self.assertIsNone(report["variants"][0]["dsr_advisory"]["probability"])

    def test_dsr_advisory_and_psr_bounds(self):
        vals = [.001 if i % 3 else -.0004 for i in range(150)]
        p = probabilistic_sharpe(vals, 0)
        self.assertGreater(p, .5)
        self.assertLessEqual(p, 1)
        dsr = deflated_sharpe(vals, [.10,.14,.3,.08], 20)
        self.assertIsNotNone(dsr["benchmark_sharpe_per_session"])
        self.assertTrue(0 <= dsr["probability"] <= 1)

    def test_file_report_serializes_and_retains_fingerprint(self):
        with TemporaryDirectory() as td:
            file = Path(td)/"panel.csv"
            output = Path(td)/"report.json"
            create_panel(file, n=120)
            report = audit_csv(file, "beta", output, iterations=200, declared_trials=10)
            self.assertEqual(json.loads(output.read_text())["panel_sha256"], report["panel_sha256"])
            self.assertEqual(report["declared_missing_variant_results"], 7)


class TradeExportTests(unittest.TestCase):
    def test_trade_export_includes_no_trade_days_and_reconciles_pnl(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            (root/"summary.json").write_text(json.dumps({"complete_tape":True,
                                                             "trades":1,"pnl_usd_after_costs":25.0}))
            (root/"trades.csv").write_text("entry_time,exit_time,pnl\n"
                "2025-01-02T10:00:00-05:00,2025-01-02T10:30:00-05:00,25.0\n")
            returns = _read_trade_report(root/"trades.csv", [date(2025,1,2),date(2025,1,3)],
                                         __import__('decimal').Decimal('25000'), 'America/New_York')
            self.assertEqual(returns, [__import__('decimal').Decimal('.001'), 0])

    def test_incomplete_trade_report_rejected(self):
        with TemporaryDirectory() as td:
            root=Path(td)
            (root/"summary.json").write_text(json.dumps({"complete_tape":False,"trades":0,
                                                           "pnl_usd_after_costs":0.0}))
            (root/"trades.csv").write_text("entry_time,exit_time,pnl\n")
            with self.assertRaisesRegex(ValueError, "Incomplete trading tape"):
                _read_trade_report(root/"trades.csv", [date(2025,1,2)],
                                   __import__('decimal').Decimal('25000'), 'America/New_York')


if __name__ == "__main__":
    unittest.main()
