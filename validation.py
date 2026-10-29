"""Data-quality validation for daily business rows.

Returns a list of human-readable issue strings; an empty list means the
dataset is clean. Validation never raises on bad *data* — it reports —
so the CLI ``check`` gate can map issues to exit code 2.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List

from generator import DAY_FIELDS

REQUIRED_FIELDS = DAY_FIELDS
NON_NEGATIVE_FIELDS = ["visitors", "orders", "revenue", "avg_order_value",
                       "refund_rate", "support_tickets",
                       "fulfillment_hours"]
INT_FIELDS = ["visitors", "orders", "support_tickets"]
RATE_FIELDS = ["conversion_rate", "refund_rate"]


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def validate_day(row: Dict, index: int = 0) -> List[str]:
    issues: List[str] = []
    label = row.get("date", f"<row {index}>")
    for field in REQUIRED_FIELDS:
        if field not in row or row[field] is None or row[field] == "":
            issues.append(f"{label}: missing field '{field}'")
    if issues:
        return issues

    if _parse_date(row["date"]) is None:
        issues.append(f"{label}: date must be YYYY-MM-DD")
    for field in INT_FIELDS:
        v = row[field]
        if not isinstance(v, int) or isinstance(v, bool):
            issues.append(f"{label}: {field} must be an int")
    for field in NON_NEGATIVE_FIELDS:
        v = row[field]
        if not _is_number(v):
            issues.append(f"{label}: {field} must be a number")
        elif v < 0:
            issues.append(f"{label}: {field} must be >= 0")
    for field in RATE_FIELDS:
        v = row[field]
        if _is_number(v) and not (0.0 <= v <= 1.0):
            issues.append(f"{label}: {field} out of range [0, 1]")
    if _is_number(row.get("fulfillment_hours")) and row["fulfillment_hours"] <= 0:
        issues.append(f"{label}: fulfillment_hours must be > 0")
    return issues


def validate_dataset(rows: List[Dict]) -> List[str]:
    issues: List[str] = []
    if not rows:
        return ["dataset is empty"]
    for i, row in enumerate(rows):
        issues.extend(validate_day(row, index=i))
    # Duplicate dates + continuity (only over parseable dates).
    parsed = [(i, _parse_date(r.get("date"))) for i, r in enumerate(rows)]
    seen = set()
    for i, d in parsed:
        if d is None:
            continue
        if d in seen:
            issues.append(f"{rows[i].get('date')}: duplicate date")
        seen.add(d)
    dated = sorted(d for _, d in parsed if d is not None)
    for prev, cur in zip(dated, dated[1:]):
        if cur - prev > timedelta(days=1):
            issues.append(
                f"date gap: {prev.isoformat()} -> {cur.isoformat()} "
                f"({(cur - prev).days - 1} missing day(s))")
    return issues
