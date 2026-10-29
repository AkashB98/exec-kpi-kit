"""Generator determinism, identities, and planted patterns."""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import (DAY_FIELDS, DEFAULT_DAYS, DIP_DAYS,  # noqa: E402
                       FULFILLMENT_BLOWOUT_DAY, REFUND_SPIKE_DAYS,
                       days_to_csv, days_to_jsonl, generate_days)


class TestGenerator(unittest.TestCase):
    def test_default_shape_and_dates(self):
        rows = generate_days()
        self.assertEqual(len(rows), DEFAULT_DAYS)
        self.assertEqual(rows[0]["date"], "2026-01-01")
        self.assertEqual(rows[-1]["date"], "2026-03-31")
        for r in rows:
            self.assertEqual(list(r.keys()), DAY_FIELDS)

    def test_determinism(self):
        self.assertEqual(generate_days(), generate_days())
        self.assertEqual(days_to_jsonl(generate_days(10, seed=7)),
                         days_to_jsonl(generate_days(10, seed=7)))

    def test_seed_changes_output(self):
        self.assertNotEqual(generate_days(10, seed=1), generate_days(10, seed=2))

    def test_count_zero_and_negative(self):
        self.assertEqual(generate_days(0), [])
        with self.assertRaises(ValueError):
            generate_days(-1)

    def test_dates_are_consecutive(self):
        from datetime import date, timedelta
        rows = generate_days()
        prev = None
        for r in rows:
            d = date.fromisoformat(r["date"])
            if prev is not None:
                self.assertEqual(d - prev, timedelta(days=1))
            prev = d

    def test_identities_hold(self):
        for r in generate_days():
            self.assertAlmostEqual(r["orders"] / r["visitors"],
                                   r["conversion_rate"], places=5)
            self.assertAlmostEqual(r["orders"] * r["avg_order_value"],
                                   r["revenue"], places=2)

    def test_value_ranges(self):
        for r in generate_days():
            self.assertGreater(r["visitors"], 0)
            self.assertGreaterEqual(r["orders"], 0)
            self.assertTrue(0.0 <= r["refund_rate"] <= 0.5)
            self.assertTrue(0.0 < r["conversion_rate"] < 0.1)
            self.assertGreater(r["fulfillment_hours"], 0)

    def test_growth_trend_last_month_beats_first(self):
        rows = generate_days()
        first = sum(r["revenue"] for r in rows[:30])
        last = sum(r["revenue"] for r in rows[-30:])
        self.assertGreater(last, first)

    def test_planted_revenue_dip(self):
        rows = generate_days()
        dip = [rows[i] for i in DIP_DAYS]
        neighbours = rows[DIP_DAYS[0] - 3:DIP_DAYS[0]] + \
            rows[DIP_DAYS[-1] + 1:DIP_DAYS[-1] + 4]
        dip_avg = sum(r["revenue"] for r in dip) / len(dip)
        nb_avg = sum(r["revenue"] for r in neighbours) / len(neighbours)
        self.assertLess(dip_avg, nb_avg * 0.65)

    def test_planted_refund_spike(self):
        rows = generate_days()
        for i in REFUND_SPIKE_DAYS:
            self.assertGreater(rows[i]["refund_rate"], 0.07)
        normal = [rows[i]["refund_rate"] for i in (40, 41, 42, 50, 51)]
        self.assertTrue(all(v < 0.04 for v in normal))

    def test_planted_fulfillment_blowout(self):
        rows = generate_days()
        self.assertGreater(rows[FULFILLMENT_BLOWOUT_DAY]["fulfillment_hours"], 40)
        others = [r["fulfillment_hours"] for j, r in enumerate(rows)
                  if j != FULFILLMENT_BLOWOUT_DAY]
        self.assertTrue(all(v < 35 for v in others))

    def test_jsonl_md5_pinned(self):
        md5 = hashlib.md5(days_to_jsonl(generate_days()).encode()).hexdigest()
        self.assertEqual(md5, "9803f5f967d1b8f74ce370e3ec331d98")

    def test_csv_shape(self):
        text = days_to_csv(generate_days(5))
        lines = text.strip().splitlines()
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("date,visitors,orders"))


if __name__ == "__main__":
    unittest.main()
