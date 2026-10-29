"""Shared row builders for the test suite (not a test module)."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def day(date_str="2026-01-01", **overrides):
    base = {
        "date": date_str,
        "visitors": 10000,
        "orders": 320,
        "conversion_rate": 0.032,
        "avg_order_value": 85.0,
        "revenue": 27200.0,
        "refund_rate": 0.02,
        "support_tickets": 26,
        "fulfillment_hours": 24.0,
    }
    base.update(overrides)
    return base


def days_block(n, start="2026-01-01", **overrides):
    """``n`` consecutive valid days starting at ``start``."""
    y, m, d = (int(x) for x in start.split("-"))
    base = date(y, m, d)
    return [day((base + timedelta(days=i)).isoformat(), **overrides)
            for i in range(n)]
