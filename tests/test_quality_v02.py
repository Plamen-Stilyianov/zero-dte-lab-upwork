"""Adversarial provenance / leakage and rolling fold tests for v0.2."""
import csv
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from zerodte.config import Settings
from zerodte.data import read_frames
from zerodte.greeks_quality import delta_quality_reason
from zerodte.rolling import make_folds
from zerodte.tape_audit import audit_tape
from zerodte.vendor_merge import merge_vendor_csv
from test_core import T, frame


class GreekSourceTests(unittest.TestCase):
    def setUp(self):
        self.c = Settings()
        self.q = frame().quotes[0]

    def test_default_rejects_synthetic_greeks(self):
        self.assertEqual(delta_quality_reason(self.q, T, self.c), "untrusted_greek_source")

    def test_trusted_provider_only_after_asof_check(self):
        vendor = replace(self.q, greek_provider="thetadata", delta_ts=T)
        self.assertIsNone(delta_quality_reason(vendor, T, self.c))

    def test_no_auto_source_or_time_fabrication(self):
        self.assertEqual(delta_quality_reason(replace(self.q, greek_provider=None), T, self.c),
                         "unknown_provenance_or_timestamp")
        self.assertEqual(delta_quality_reason(replace(self.q, delta_ts=None), T, self.c),
                         "unknown_provenance_or_timestamp")

    def test_future_delta_rejected(self):
        q = replace(self.q, greek_provider="orats", delta_ts=T + timedelta(seconds=1))
        self.assertEqual(delta_quality_reason(q, T, self.c), "future_or_stale_delta")

    def test_stale_delta_rejected_even_when_quote_fresh(self):
        q = replace(self.q, greek_provider="orats", delta_ts=T - timedelta(seconds=31))
        self.assertEqual(delta_quality_reason(q, T, self.c), "future_or_stale_delta")

    def test_odd_timestamp_skew_rejected(self):
        c = replace(self.c, max_greek_age_seconds=120)
        q = replace(self.q, greek_provider="cboe", delta_ts=T - timedelta(seconds=61))
        self.assertEqual(delta_quality_reason(q, T, c), "misaligned_greek_and_quote")

    def test_independent_disagreement_rejected(self):
        q = replace(self.q, greek_provider="thetadata", delta_ts=T,
                    reference_delta=.63, reference_delta_ts=T, reference_provider="nautilus_local")
        self.assertEqual(delta_quality_reason(q, T, self.c), "conflicting_delta_sources")

    def test_reference_provider_must_be_distinct(self):
        q = replace(self.q, greek_provider="thetadata", delta_ts=T,
                    reference_delta=.80, reference_delta_ts=T,
                    reference_provider="thetadata")
        self.assertEqual(delta_quality_reason(q, T, self.c), "reference_not_independent")

    def test_independent_reference_must_be_asof(self):
        q = replace(self.q, greek_provider="thetadata", delta_ts=T,
                    reference_delta=.79, reference_delta_ts=T + timedelta(seconds=3), reference_provider="nautilus_local")
        self.assertEqual(delta_quality_reason(q, T, self.c), "future_or_stale_reference_delta")

    def test_experimental_does_not_mean_untimed(self):
        q = replace(self.q, delta_ts=None)
        self.assertEqual(delta_quality_reason(q, T, replace(self.c, greek_policy="experimental")),
                         "unknown_provenance_or_timestamp")


class StreamingDataTests(unittest.TestCase):
    def _create(self, folder, greek_ts=None, quote_ts=None, omit_provenance=False):
        filename = Path(folder) / "tape.csv"
        fields = ["ts", "underlying", "close", "high", "low", "volume",
                  "option_symbol", "expiry", "right", "strike", "bid", "ask",
                  "option_volume", "quote_ts", "delta"]
        if not omit_provenance:
            fields += ["greek_provider", "delta_ts"]
        row = dict(ts=T.isoformat(), underlying="SPY", close=650, high=651, low=649,
                   volume=2000, option_symbol="SPY261026C00649000",
                   expiry="2026-10-26", right="C", strike=649, bid=2,
                   ask=2.05, option_volume=250, quote_ts=(quote_ts or T).isoformat(),
                   delta=.8, greek_provider="thetadata", delta_ts=(greek_ts or T).isoformat())
        with filename.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerow(row)
        return filename

    def test_requires_provenance_columns(self):
        with TemporaryDirectory() as tmp:
            path = self._create(tmp, omit_provenance=True)
            with self.assertRaisesRegex(ValueError, "greek_provider and delta_ts"):
                list(read_frames(str(path)))

    def test_never_accept_future_quote(self):
        with TemporaryDirectory() as tmp:
            path = self._create(tmp, quote_ts=T + timedelta(seconds=1))
            with self.assertRaisesRegex(ValueError, "Future option quote"):
                list(read_frames(str(path)))

    def test_tape_audit_counts_vendor(self):
        with TemporaryDirectory() as tmp:
            path = self._create(tmp)
            report = audit_tape(str(path), Settings())
            self.assertEqual(report["timing_and_provenance"]["pass_provenance_and_time"], 1)
            self.assertEqual(report["greek_providers"]["thetadata"], 1)

    def test_vendor_merge_preserves_asof(self):
        with TemporaryDirectory() as tmp:
            path = self._create(tmp)
            bars = Path(tmp) / "bars.csv"
            with bars.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=("ts", "underlying", "close", "high", "low", "volume"))
                w.writeheader()
                w.writerow({"ts":T.isoformat(), "underlying":"SPY", "close":650,
                            "high":651, "low":649, "volume":2000})
            result = merge_vendor_csv(str(bars), str(path), str(Path(tmp)/"merged.csv"), "thetadata")
            self.assertEqual(result["option_rows"], 1)
            self.assertEqual(len(list(read_frames(result["output"]))), 1)

    def test_vendor_merge_rejects_future_greek(self):
        with TemporaryDirectory() as tmp:
            path = self._create(tmp, greek_ts=T + timedelta(seconds=1))
            bars = Path(tmp) / "bars.csv"
            bars.write_text('ts,underlying,close,high,low,volume\n'+T.isoformat()+',SPY,650,651,649,2000\n')
            with self.assertRaisesRegex(ValueError, "Future quote or delta"):
                merge_vendor_csv(str(bars), str(path), str(Path(tmp)/"merged.csv"), "thetadata")


class RollingTests(unittest.TestCase):
    def test_embargo_separates_training_from_validation_and_test(self):
        dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(15)]
        folds = make_folds(dates, 5, 2, 2, 2, 1)
        self.assertEqual(folds[0].train_end, dates[4])
        self.assertEqual(folds[0].val_start, dates[6])
        self.assertEqual(folds[0].test_start, dates[9])
        self.assertEqual(folds[1].train_end, dates[6])

    def test_rejects_unsorted_session_dates(self):
        with self.assertRaisesRegex(ValueError, "distinct and chronological"):
            make_folds([date(2025, 1, 2), date(2025, 1, 1)], 1, 1, 1, 1)

if __name__ == "__main__":
    unittest.main()
