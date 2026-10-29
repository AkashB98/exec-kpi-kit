"""Narrative: determinism, content sourced from the scorecard, formatting."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_days  # noqa: E402
from helpers import days_block  # noqa: E402
from narrative import build_narrative, build_report  # noqa: E402
from scorecard import build_scorecard  # noqa: E402


class TestNarrative(unittest.TestCase):
    def setUp(self):
        self.rows = generate_days()
        self.report = build_report(self.rows)

    def test_deterministic(self):
        self.assertEqual(build_report(self.rows), self.report)
        sc = build_scorecard(self.rows)
        from anomalies import detect_anomalies
        self.assertEqual(build_narrative(sc, detect_anomalies(self.rows)),
                         build_narrative(sc, detect_anomalies(self.rows)))

    def test_report_structure(self):
        self.assertEqual(set(self.report),
                         {"scorecard", "anomalies", "anomaly_count",
                          "narrative"})
        self.assertEqual(self.report["anomaly_count"],
                         len(self.report["anomalies"]))
        self.assertEqual(self.report["anomaly_count"], 12)

    def test_headline_counts_match_scorecard(self):
        text = self.report["narrative"]
        self.assertIn("6 metric(s) on target, 1 on watch, 1 at risk", text)
        self.assertIn("2026-03-02 to 2026-03-31", text)

    def test_at_risk_metrics_named_with_owners(self):
        text = self.report["narrative"]
        self.assertIn("Support tickets", text)
        self.assertIn("Customer Care", text)
        self.assertIn("Conversion rate", text)

    def test_anomaly_callout_names_worst(self):
        text = self.report["narrative"]
        self.assertIn("12 anomalous day(s)", text)
        self.assertIn("refund_rate", text)
        self.assertIn("2026-02-15", text)

    def test_top_mover_is_biggest_delta(self):
        # Seeded book: refund rate has the largest |delta_pct| (-16.48%).
        text = self.report["narrative"]
        self.assertIn("Biggest mover: Refund rate", text)
        self.assertIn("down 16.5%", text)

    def test_all_green_narrative(self):
        calm = [dict(r, support_tickets=20) for r in generate_days()]
        # Force conversion green too: lift orders/visitors ratio is not
        # needed — calm book still has conversion yellow, so instead use
        # a flat synthetic book where every metric sits on target side.
        rows = days_block(60, visitors=11000, orders=360,
                          conversion_rate=360 / 11000, revenue=32000.0,
                          avg_order_value=32000.0 / 360, refund_rate=0.02,
                          support_tickets=25, fulfillment_hours=24.0)
        report = build_report(rows)
        self.assertIn("Needs attention: none", report["narrative"])
        self.assertIn("Anomalies: none flagged", report["narrative"])
        _ = calm  # (seeded-calm variant exercised in CLI/demo tests)

    def test_flat_book_mover_wording(self):
        rows = days_block(60)
        text = build_report(rows)["narrative"]
        self.assertIn("flat vs the prior period", text)


if __name__ == "__main__":
    unittest.main()
