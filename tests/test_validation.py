"""Validation: defects are reported, never raised; clean data passes."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator import generate_days  # noqa: E402
from helpers import day, days_block  # noqa: E402
from validation import validate_dataset, validate_day  # noqa: E402


class TestValidation(unittest.TestCase):
    def test_generated_dataset_clean(self):
        self.assertEqual(validate_dataset(generate_days()), [])

    def test_empty_dataset(self):
        self.assertEqual(validate_dataset([]), ["dataset is empty"])

    def test_missing_field(self):
        row = day()
        del row["revenue"]
        issues = validate_day(row)
        self.assertTrue(any("missing field 'revenue'" in i for i in issues))

    def test_none_and_empty_string_count_as_missing(self):
        self.assertTrue(validate_day(day(revenue=None)))
        self.assertTrue(validate_day(day(visitors="")))

    def test_bad_date_format(self):
        self.assertTrue(validate_day(day(date_str="31/01/2026")))
        self.assertTrue(validate_day(day(date_str="2026-13-01")))
        self.assertTrue(validate_day(day(date_str=20260101)))

    def test_negative_values(self):
        self.assertTrue(validate_day(day(revenue=-1.0)))
        self.assertTrue(validate_day(day(visitors=-5)))
        self.assertTrue(validate_day(day(support_tickets=-1)))
        self.assertEqual(validate_day(day(revenue=0.0)), [])

    def test_rate_ranges(self):
        self.assertTrue(validate_day(day(refund_rate=1.5)))
        self.assertTrue(validate_day(day(conversion_rate=-0.1)))
        self.assertEqual(validate_day(day(refund_rate=1.0)), [])
        self.assertEqual(validate_day(day(refund_rate=0.0)), [])

    def test_int_fields_reject_floats_and_bools(self):
        self.assertTrue(validate_day(day(visitors=100.5)))
        self.assertTrue(validate_day(day(orders=True)))
        self.assertTrue(validate_day(day(support_tickets="26")))

    def test_bool_is_not_a_number(self):
        self.assertTrue(validate_day(day(revenue=True)))

    def test_fulfillment_must_be_positive(self):
        self.assertTrue(validate_day(day(fulfillment_hours=0.0)))
        self.assertEqual(validate_day(day(fulfillment_hours=0.5)), [])

    def test_duplicate_dates(self):
        rows = days_block(10)
        rows.append(dict(rows[3]))
        issues = validate_dataset(rows)
        self.assertTrue(any("duplicate date" in i for i in issues))

    def test_date_gap_reported(self):
        rows = days_block(5) + days_block(5, start="2026-01-10")
        issues = validate_dataset(rows)
        self.assertTrue(any("date gap" in i for i in issues), issues)

    def test_continuous_dataset_no_gap(self):
        self.assertEqual(validate_dataset(days_block(30)), [])

    def test_issues_name_the_row(self):
        issues = validate_day(day(date_str="2026-02-02", revenue=-3.0))
        self.assertTrue(all(i.startswith("2026-02-02") for i in issues))

    def test_never_raises_on_garbage(self):
        for bad in ({}, {"date": None}, day(revenue="lots"),
                    day(visitors=[1, 2])):
            try:
                validate_day(bad)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"validate_day raised {exc!r} on {bad!r}")


if __name__ == "__main__":
    unittest.main()
