"""Deterministic synthetic daily business generator — Helios Home (fictional).

SYNTHETIC DATA ONLY. No real company, customer, or revenue data is ever
used. Every day is fabricated from a seeded PRNG so the same seed always
yields the same dataset, byte-for-byte.

One row per day, 90 days by default starting 2026-01-01:

  date, visitors, orders, conversion_rate, avg_order_value, revenue,
  refund_rate, support_tickets, fulfillment_hours

Identities hold by construction (up to the documented rounding):
  orders          = round(visitors * conversion)
  conversion_rate = orders / visitors
  revenue         = orders * avg_order_value

Planted patterns (pinned by tests and golden evals, seed 42):
  * steady growth — a +0.3%/day trend lifts visitors and order value;
  * revenue dip incident — days 60-62 (2026-03-02..2026-03-04): traffic
    falls to ~55% and conversion softens, so revenue drops hard;
  * refund-rate spike — days 45-46 (2026-02-15..2026-02-16): the refund
    rate jumps from ~2% to ~8.5%;
  * fulfilment blowout — day 30 (2026-01-31): fulfilment time doubles.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Dict, List

START_DATE = date(2026, 1, 1)
DEFAULT_SEED = 42
DEFAULT_DAYS = 90

DAY_FIELDS = ["date", "visitors", "orders", "conversion_rate",
              "avg_order_value", "revenue", "refund_rate",
              "support_tickets", "fulfillment_hours"]

# Planted incident windows (0-based day indexes into the dataset).
DIP_DAYS = (60, 61, 62)
REFUND_SPIKE_DAYS = (45, 46)
FULFILLMENT_BLOWOUT_DAY = 30


def _weekday_factor(d: date) -> float:
    wd = d.weekday()  # Mon=0 .. Sun=6
    if wd in (5, 6):
        return 1.15
    if wd == 4:
        return 1.05
    return 1.0


def generate_days(days: int = DEFAULT_DAYS, seed: int = DEFAULT_SEED,
                  start: date = START_DATE) -> List[Dict]:
    """Return ``days`` synthetic daily rows, deterministic for ``seed``."""
    if days < 0:
        raise ValueError("days must be >= 0")
    rng = random.Random(seed)
    rows: List[Dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        trend = 1.0 + 0.003 * i
        wf = _weekday_factor(d)

        visitors_noise = rng.gauss(1.0, 0.04)
        conv_noise = rng.gauss(1.0, 0.03)
        aov_noise = rng.gauss(1.0, 0.03)
        refund_noise = rng.gauss(1.0, 0.10)
        ticket_noise = rng.gauss(1.0, 0.08)
        fulfill_noise = rng.gauss(1.0, 0.06)

        visitors_f = 10000.0 * trend * wf * visitors_noise
        conversion_f = 0.032 * conv_noise
        aov_f = 85.0 * (trend ** 0.5) * aov_noise
        refund_f = 0.02 * refund_noise
        fulfill_f = 24.0 * fulfill_noise

        if i in DIP_DAYS:
            visitors_f *= 0.55
            conversion_f *= 0.85
        if i in REFUND_SPIKE_DAYS:
            refund_f = 0.085 * rng.gauss(1.0, 0.03)
        if i == FULFILLMENT_BLOWOUT_DAY:
            fulfill_f = 48.0 * fulfill_noise

        visitors = max(1, int(round(visitors_f)))
        orders = max(0, int(round(visitors * conversion_f)))
        conversion_rate = round(orders / visitors, 6) if visitors else 0.0
        avg_order_value = round(max(1.0, aov_f), 2)
        revenue = round(orders * avg_order_value, 2)
        refund_rate = round(min(0.50, max(0.0, refund_f)), 6)
        support_tickets = max(0, int(round(orders * 0.08 * ticket_noise)))
        fulfillment_hours = round(min(96.0, max(1.0, fulfill_f)), 2)

        rows.append({
            "date": d.isoformat(),
            "visitors": visitors,
            "orders": orders,
            "conversion_rate": conversion_rate,
            "avg_order_value": avg_order_value,
            "revenue": revenue,
            "refund_rate": refund_rate,
            "support_tickets": support_tickets,
            "fulfillment_hours": fulfillment_hours,
        })
    return rows


def days_to_csv(rows: List[Dict]) -> str:
    import csv
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=DAY_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in DAY_FIELDS})
    return buf.getvalue()


def days_to_jsonl(rows: List[Dict]) -> str:
    import json
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
