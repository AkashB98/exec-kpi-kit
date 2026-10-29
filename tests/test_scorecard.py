"""Scorecard: status logic in both directions, deltas, period slicing."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import days_block  # noqa: E402
from metrics import get_metric  # noqa: E402
from scorecard import (beyond_critical, build_scorecard, entry_for,  # noqa: E402
                       status_for)


class TestStatusHigherBetter(unittest.TestCase):
    def setUp(self):
        self.m = get_metric("revenue")  # target 900k, warn 820k, crit 700k

    def test_at_and_above_target_green(self):
        self.assertEqual(status_for(self.m, 900000.0), "green")
        self.assertEqual(status_for(self.m, 1200000.0), "green")

    def test_between_warn_and_target_yellow(self):
        self.assertEqual(status_for(self.m, 899999.0), "yellow")
        self.assertEqual(status_for(self.m, 820000.0), "yellow")

    def test_below_warn_red(self):
        self.assertEqual(status_for(self.m, 819999.0), "red")
        self.assertEqual(status_for(self.m, 0.0), "red")

    def test_beyond_critical(self):
        self.assertTrue(beyond_critical(self.m, 699999.0))
        self.assertFalse(beyond_critical(self.m, 750000.0))


class TestStatusLowerBetter(unittest.TestCase):
    def setUp(self):
        self.m = get_metric("refund_rate")  # target .022, warn .030, crit .045

    def test_at_and_below_target_green(self):
        self.assertEqual(status_for(self.m, 0.022), "green")
        self.assertEqual(status_for(self.m, 0.010), "green")

    def test_between_target_and_warn_yellow(self):
        self.assertEqual(status_for(self.m, 0.023), "yellow")
        self.assertEqual(status_for(self.m, 0.030), "yellow")

    def test_above_warn_red(self):
        self.assertEqual(status_for(self.m, 0.031), "red")
        self.assertEqual(status_for(self.m, 0.20), "red")

    def test_beyond_critical(self):
        self.assertTrue(beyond_critical(self.m, 0.046))
        self.assertFalse(beyond_critical(self.m, 0.040))


class TestScorecardMath(unittest.TestCase):
    def test_periods_and_labels(self):
        rows = days_block(90)
        sc = build_scorecard(rows)
        self.assertEqual(sc["current_period"],
                         {"start": rows[-30]["date"], "end": rows[-1]["date"]})
        self.assertEqual(sc["prior_period"],
                         {"start": rows[-60]["date"], "end": rows[-31]["date"]})
        self.assertEqual(sc["period_days"], 30)
        self.assertEqual(len(sc["metrics"]), 8)

    def test_flat_dataset_zero_deltas(self):
        sc = build_scorecard(days_block(60))
        for e in sc["metrics"]:
            self.assertEqual(e["delta"], 0.0, e["metric"])
            self.assertEqual(e["delta_pct"], 0.0, e["metric"])

    def test_delta_pct_hand_computed(self):
        prior = days_block(30, revenue=20000.0, visitors=10000, orders=320,
                           avg_order_value=62.5)
        current = days_block(30, start="2026-01-31", revenue=25000.0,
                             visitors=10000, orders=320, avg_order_value=78.125)
        sc = build_scorecard(prior + current)
        rev = entry_for(sc, "revenue")
        self.assertEqual(rev["prior"], 600000.0)
        self.assertEqual(rev["current"], 750000.0)
        self.assertEqual(rev["delta"], 150000.0)
        self.assertEqual(rev["delta_pct"], 25.0)

    def test_custom_period_days(self):
        sc = build_scorecard(days_block(28), period_days=14)
        self.assertEqual(sc["period_days"], 14)

    def test_too_few_rows_raises(self):
        with self.assertRaises(ValueError):
            build_scorecard(days_block(59))
        with self.assertRaises(ValueError):
            build_scorecard(days_block(60), period_days=0)

    def test_seeded_statuses_pinned(self):
        from generator import generate_days
        sc = build_scorecard(generate_days())
        self.assertEqual(sc["status_counts"],
                         {"green": 6, "yellow": 1, "red": 1})
        self.assertEqual(entry_for(sc, "support_tickets")["status"], "red")
        self.assertEqual(entry_for(sc, "conversion_rate")["status"], "yellow")
        self.assertEqual(entry_for(sc, "revenue")["current"], 1092371.1)

    def test_entry_for_missing(self):
        sc = build_scorecard(days_block(60))
        with self.assertRaises(KeyError):
            entry_for(sc, "nope")


if __name__ == "__main__":
    unittest.main()
