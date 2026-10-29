"""Anomaly detector: planted incidents, clean data, evidence, ordering."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomalies import anomaly_summary, detect_anomalies  # noqa: E402
from generator import generate_days  # noqa: E402
from helpers import day, days_block  # noqa: E402


class TestDetector(unittest.TestCase):
    def test_flat_data_no_anomalies(self):
        self.assertEqual(detect_anomalies(days_block(40)), [])

    def test_empty_and_short_inputs(self):
        self.assertEqual(detect_anomalies([]), [])
        self.assertEqual(detect_anomalies(days_block(5)), [])

    def test_planted_spike_flagged_with_evidence(self):
        rows = days_block(30)
        rows[20] = day(rows[20]["date"], revenue=200000.0)
        findings = detect_anomalies(rows)
        hits = [f for f in findings if f["metric"] == "revenue"]
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit["date"], rows[20]["date"])
        self.assertEqual(hit["value"], 200000.0)
        self.assertEqual(hit["expected"], 27200.0)
        self.assertGreater(hit["z_score"], 3.5)
        self.assertEqual(hit["direction"], "high")

    def test_planted_drop_flagged_low(self):
        rows = days_block(30)
        rows[25] = day(rows[25]["date"], visitors=100)
        hits = [f for f in detect_anomalies(rows) if f["metric"] == "visitors"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["direction"], "low")
        self.assertLess(hits[0]["z_score"], -3.5)

    def test_small_wiggle_not_flagged(self):
        # Baseline with realistic day-to-day variance; a mid-range day
        # inside that variance must not flag.
        cycle = [25000.0, 27000.0, 29000.0, 31000.0]
        rows = days_block(30)
        for i, r in enumerate(rows):
            r["revenue"] = cycle[i % 4]
        rows[20] = day(rows[20]["date"], revenue=28500.0)
        self.assertEqual(
            [f for f in detect_anomalies(rows) if f["metric"] == "revenue"],
            [])

    def test_zero_variance_baseline_flags_any_deviation(self):
        rows = days_block(30)
        rows[20] = day(rows[20]["date"], revenue=27201.0)  # +1.0 on flat
        hits = [f for f in detect_anomalies(rows) if f["metric"] == "revenue"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["z_score"], 999.9)

    def test_threshold_is_respected(self):
        rows = days_block(30)
        rows[20] = day(rows[20]["date"], revenue=200000.0)
        # Zero-variance baseline: z is the 999.9 sentinel, so only a
        # threshold above the sentinel suppresses the flag.
        self.assertEqual(detect_anomalies(rows, threshold=2000.0), [])
        self.assertTrue(detect_anomalies(rows, threshold=500.0))
        self.assertTrue(detect_anomalies(rows, threshold=3.5))

    def test_first_days_never_flagged(self):
        rows = days_block(30)
        rows[2] = day(rows[2]["date"], revenue=999999.0)
        hits = [f for f in detect_anomalies(rows) if f["date"] == rows[2]["date"]]
        self.assertEqual(hits, [])

    def test_findings_sorted_by_date_then_metric(self):
        findings = detect_anomalies(generate_days())
        keys = [(f["date"], f["metric"]) for f in findings]
        self.assertEqual(keys, sorted(keys))

    def test_seeded_count_and_incidents_pinned(self):
        findings = detect_anomalies(generate_days())
        self.assertEqual(len(findings), 12)
        keys = {(f["date"], f["metric"]) for f in findings}
        self.assertIn(("2026-02-15", "refund_rate"), keys)
        self.assertIn(("2026-03-02", "revenue"), keys)
        self.assertIn(("2026-03-02", "visitors"), keys)
        self.assertIn(("2026-01-31", "fulfillment_hours"), keys)

    def test_worst_is_refund_spike(self):
        summary = anomaly_summary(detect_anomalies(generate_days()))
        self.assertEqual(summary["count"], 12)
        self.assertEqual(summary["worst"]["metric"], "refund_rate")
        self.assertEqual(summary["worst"]["date"], "2026-02-15")
        self.assertGreater(summary["worst"]["z_score"], 40)

    def test_summary_empty(self):
        self.assertEqual(anomaly_summary([]), {"count": 0, "worst": None})

    def test_single_field_selection(self):
        findings = detect_anomalies(generate_days(), fields=["revenue"])
        self.assertTrue(all(f["metric"] == "revenue" for f in findings))
        self.assertEqual(len(findings), 4)


if __name__ == "__main__":
    unittest.main()
