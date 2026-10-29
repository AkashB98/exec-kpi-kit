"""Metric registry integrity + formula correctness on hand-computed cases."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import day  # noqa: E402
from metrics import (DAILY_FIELDS, METRICS, METRIC_BY_NAME, METRIC_NAMES,  # noqa: E402
                     compute_value, get_metric, public_definition)


class TestRegistryIntegrity(unittest.TestCase):
    def test_eight_metrics_unique_names(self):
        self.assertEqual(len(METRICS), 8)
        self.assertEqual(len(set(METRIC_NAMES)), 8)
        self.assertEqual(set(METRIC_BY_NAME), set(METRIC_NAMES))

    def test_required_keys_present(self):
        for m in METRICS:
            for key in ("name", "label", "description", "unit", "direction",
                        "aggregation", "fields", "formula", "target",
                        "warn", "critical", "owner"):
                self.assertIn(key, m, (m["name"], key))
            self.assertTrue(callable(m["formula"]))

    def test_direction_vocabulary(self):
        for m in METRICS:
            self.assertIn(m["direction"], ("higher", "lower"))
        self.assertEqual(sum(1 for m in METRICS if m["direction"] == "higher"), 5)
        self.assertEqual(sum(1 for m in METRICS if m["direction"] == "lower"), 3)

    def test_threshold_ordering_matches_direction(self):
        for m in METRICS:
            if m["direction"] == "higher":
                self.assertGreater(m["target"], m["warn"], m["name"])
                self.assertGreater(m["warn"], m["critical"], m["name"])
            else:
                self.assertLess(m["target"], m["warn"], m["name"])
                self.assertLess(m["warn"], m["critical"], m["name"])

    def test_fields_exist_in_daily_schema(self):
        from generator import DAY_FIELDS
        for m in METRICS:
            for f in m["fields"]:
                self.assertIn(f, DAY_FIELDS, (m["name"], f))

    def test_daily_fields_watched_are_real(self):
        from generator import DAY_FIELDS
        for f in DAILY_FIELDS:
            self.assertIn(f, DAY_FIELDS)
        self.assertEqual(len(DAILY_FIELDS), 8)

    def test_public_definition_strips_formula(self):
        pub = public_definition(METRICS[0])
        self.assertNotIn("formula", pub)
        self.assertEqual(pub["name"], METRICS[0]["name"])
        import json
        json.dumps(pub)  # must be JSON-serialisable

    def test_get_metric(self):
        self.assertEqual(get_metric("revenue")["label"], "Revenue")
        with self.assertRaises(KeyError):
            get_metric("nope")


class TestFormulasHandComputed(unittest.TestCase):
    def setUp(self):
        # Hand-computed fixture: two days, every aggregate done by hand.
        self.rows = [
            day(visitors=1000, orders=40, conversion_rate=0.04,
                avg_order_value=50.0, revenue=2000.0, refund_rate=0.02,
                support_tickets=10, fulfillment_hours=20.0),
            day(visitors=3000, orders=60, conversion_rate=0.02,
                avg_order_value=100.0, revenue=6000.0, refund_rate=0.04,
                support_tickets=30, fulfillment_hours=28.0),
        ]

    def test_revenue_sum(self):
        self.assertEqual(compute_value(get_metric("revenue"), self.rows), 8000.0)

    def test_orders_sum(self):
        self.assertEqual(compute_value(get_metric("orders"), self.rows), 100.0)

    def test_visitors_sum(self):
        self.assertEqual(compute_value(get_metric("visitors"), self.rows), 4000.0)

    def test_support_tickets_sum(self):
        self.assertEqual(
            compute_value(get_metric("support_tickets"), self.rows), 40.0)

    def test_conversion_is_ratio_of_totals_not_mean_of_rates(self):
        # Totals: 100 orders / 4000 visitors = 0.025, NOT mean(0.04, 0.02)=0.03.
        self.assertEqual(
            compute_value(get_metric("conversion_rate"), self.rows), 0.025)

    def test_aov_is_revenue_over_orders_not_mean(self):
        # 8000 / 100 = 80, NOT mean(50, 100) = 75.
        self.assertEqual(
            compute_value(get_metric("avg_order_value"), self.rows), 80.0)

    def test_refund_rate_is_daily_mean(self):
        self.assertAlmostEqual(
            compute_value(get_metric("refund_rate"), self.rows), 0.03)

    def test_fulfillment_is_daily_mean(self):
        self.assertEqual(
            compute_value(get_metric("fulfillment_hours"), self.rows), 24.0)

    def test_empty_rows(self):
        self.assertEqual(compute_value(get_metric("revenue"), []), 0.0)
        self.assertEqual(compute_value(get_metric("conversion_rate"), []), 0.0)
        self.assertEqual(compute_value(get_metric("refund_rate"), []), 0.0)


if __name__ == "__main__":
    unittest.main()
