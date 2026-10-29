"""Metric definitions as code — the single source of truth.

Every KPI the scorecard, the anomaly detector's business context, and
the executive narrative talk about is defined here, declaratively:

  name          stable identifier used everywhere else
  label         human-readable name for reports
  description   what the metric means, in plain English
  unit          "USD" | "count" | "ratio" | "percent" | "hours"
  direction     "higher" (higher is better) or "lower" (lower is better)
  aggregation   how daily rows roll up over a period: "sum" or "mean"
  fields        daily fields the value is derived from
  formula       how the period value is computed from daily rows
  target        the goal for one 30-day period
  warn          yellow threshold (between target and critical)
  critical      red threshold
  owner         team accountable for the metric

Status rule (see scorecard.status_for):
  higher-is-better: value >= target -> green; >= warn -> yellow; else red
  lower-is-better:  value <= target -> green; <= warn -> yellow; else red
For lower-is-better metrics warn > target and critical > warn.

Nothing downstream hard-codes a target or threshold: the scorecard and
the narrative both read this registry, so changing a definition here
changes every report consistently. That is the whole point of defining
metrics as code instead of re-typing them into a weekly deck.
"""

from __future__ import annotations

from typing import Callable, Dict, List


def _sum(field: str) -> Callable[[List[Dict]], float]:
    return lambda rows: round(sum(float(r[field]) for r in rows), 6)


def _mean(field: str) -> Callable[[List[Dict]], float]:
    return lambda rows: round(
        sum(float(r[field]) for r in rows) / len(rows), 6) if rows else 0.0


def _total_revenue(rows: List[Dict]) -> float:
    return round(sum(float(r["revenue"]) for r in rows), 2)


def _conversion(rows: List[Dict]) -> float:
    visitors = sum(int(r["visitors"]) for r in rows)
    orders = sum(int(r["orders"]) for r in rows)
    return round(orders / visitors, 6) if visitors else 0.0


def _aov(rows: List[Dict]) -> float:
    orders = sum(int(r["orders"]) for r in rows)
    revenue = sum(float(r["revenue"]) for r in rows)
    return round(revenue / orders, 4) if orders else 0.0


METRICS: List[Dict] = [
    {
        "name": "revenue",
        "label": "Revenue",
        "description": "Total sales revenue over the period.",
        "unit": "USD",
        "direction": "higher",
        "aggregation": "sum",
        "fields": ["revenue"],
        "formula": _total_revenue,
        "target": 900000.0,
        "warn": 820000.0,
        "critical": 700000.0,
        "owner": "Growth",
    },
    {
        "name": "orders",
        "label": "Orders",
        "description": "Total completed orders over the period.",
        "unit": "count",
        "direction": "higher",
        "aggregation": "sum",
        "fields": ["orders"],
        "formula": _sum("orders"),
        "target": 10500.0,
        "warn": 9500.0,
        "critical": 8000.0,
        "owner": "Growth",
    },
    {
        "name": "visitors",
        "label": "Visitors",
        "description": "Total store visitors (sessions) over the period.",
        "unit": "count",
        "direction": "higher",
        "aggregation": "sum",
        "fields": ["visitors"],
        "formula": _sum("visitors"),
        "target": 330000.0,
        "warn": 300000.0,
        "critical": 250000.0,
        "owner": "Marketing",
    },
    {
        "name": "conversion_rate",
        "label": "Conversion rate",
        "description": "Share of visitors who placed an order "
                       "(total orders / total visitors).",
        "unit": "ratio",
        "direction": "higher",
        "aggregation": "derived",
        "fields": ["orders", "visitors"],
        "formula": _conversion,
        "target": 0.032,
        "warn": 0.029,
        "critical": 0.025,
        "owner": "Growth",
    },
    {
        "name": "avg_order_value",
        "label": "Average order value",
        "description": "Average revenue per order "
                       "(total revenue / total orders).",
        "unit": "USD",
        "direction": "higher",
        "aggregation": "derived",
        "fields": ["revenue", "orders"],
        "formula": _aov,
        "target": 88.0,
        "warn": 84.0,
        "critical": 78.0,
        "owner": "Merchandising",
    },
    {
        "name": "refund_rate",
        "label": "Refund rate",
        "description": "Average daily share of orders refunded.",
        "unit": "ratio",
        "direction": "lower",
        "aggregation": "mean",
        "fields": ["refund_rate"],
        "formula": _mean("refund_rate"),
        "target": 0.022,
        "warn": 0.030,
        "critical": 0.045,
        "owner": "Customer Care",
    },
    {
        "name": "support_tickets",
        "label": "Support tickets",
        "description": "Total support tickets opened over the period.",
        "unit": "count",
        "direction": "lower",
        "aggregation": "sum",
        "fields": ["support_tickets"],
        "formula": _sum("support_tickets"),
        "target": 800.0,
        "warn": 900.0,
        "critical": 1100.0,
        "owner": "Customer Care",
    },
    {
        "name": "fulfillment_hours",
        "label": "Fulfilment time",
        "description": "Average hours from order to dispatch.",
        "unit": "hours",
        "direction": "lower",
        "aggregation": "mean",
        "fields": ["fulfillment_hours"],
        "formula": _mean("fulfillment_hours"),
        "target": 26.0,
        "warn": 30.0,
        "critical": 36.0,
        "owner": "Operations",
    },
]

METRIC_BY_NAME: Dict[str, Dict] = {m["name"]: m for m in METRICS}
METRIC_NAMES: List[str] = [m["name"] for m in METRICS]

# Daily fields the anomaly detector watches (one series per field).
DAILY_FIELDS: List[str] = ["revenue", "visitors", "orders",
                           "conversion_rate", "avg_order_value",
                           "refund_rate", "support_tickets",
                           "fulfillment_hours"]


def get_metric(name: str) -> Dict:
    return METRIC_BY_NAME[name]


def compute_value(metric: Dict, rows: List[Dict]) -> float:
    """Period value of ``metric`` over daily ``rows`` (registry formula)."""
    return metric["formula"](rows)


def public_definition(metric: Dict) -> Dict:
    """JSON-safe view of a definition (formula callable stripped)."""
    return {k: v for k, v in metric.items() if k != "formula"}
