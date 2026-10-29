"""Scorecard engine: current period vs prior period vs target.

Every value, target, and threshold comes from the registry in
``metrics.py`` — this module contains no numbers of its own. A period
is the last ``period_days`` rows; the prior period is the block of the
same length immediately before it.
"""

from __future__ import annotations

from typing import Dict, List

from metrics import METRICS, compute_value

DEFAULT_PERIOD_DAYS = 30


def status_for(metric: Dict, value: float) -> str:
    """green / yellow / red from the registry thresholds + direction."""
    if metric["direction"] == "higher":
        if value >= metric["target"]:
            return "green"
        if value >= metric["warn"]:
            return "yellow"
        return "red"
    # lower-is-better
    if value <= metric["target"]:
        return "green"
    if value <= metric["warn"]:
        return "yellow"
    return "red"


def beyond_critical(metric: Dict, value: float) -> bool:
    """True when a red value has also crossed the critical threshold."""
    if metric["direction"] == "higher":
        return value < metric["critical"]
    return value > metric["critical"]


def build_scorecard(rows: List[Dict],
                    period_days: int = DEFAULT_PERIOD_DAYS) -> Dict:
    """Scorecard for the last ``period_days`` rows vs the prior block.

    Raises ValueError when fewer than ``2 * period_days`` rows are
    given (a comparison needs both periods); validation of the rows
    themselves is validation.py's job.
    """
    if period_days <= 0:
        raise ValueError("period_days must be > 0")
    if len(rows) < 2 * period_days:
        raise ValueError(
            f"need at least {2 * period_days} rows for two periods, "
            f"got {len(rows)}")
    current = rows[-period_days:]
    prior = rows[-2 * period_days:-period_days]
    entries = []
    for metric in METRICS:
        cur = compute_value(metric, current)
        pri = compute_value(metric, prior)
        delta = round(cur - pri, 6)
        delta_pct = round(delta / pri * 100.0, 4) if pri else 0.0
        status = status_for(metric, cur)
        entries.append({
            "metric": metric["name"],
            "label": metric["label"],
            "unit": metric["unit"],
            "direction": metric["direction"],
            "owner": metric["owner"],
            "current": cur,
            "prior": pri,
            "delta": delta,
            "delta_pct": delta_pct,
            "target": metric["target"],
            "warn": metric["warn"],
            "critical": metric["critical"],
            "status": status,
            "beyond_critical": status == "red" and beyond_critical(metric, cur),
        })
    counts = {"green": 0, "yellow": 0, "red": 0}
    for e in entries:
        counts[e["status"]] += 1
    return {
        "period_days": period_days,
        "current_period": {"start": current[0]["date"],
                           "end": current[-1]["date"]},
        "prior_period": {"start": prior[0]["date"],
                         "end": prior[-1]["date"]},
        "status_counts": counts,
        "metrics": entries,
    }


def entry_for(scorecard: Dict, name: str) -> Dict:
    for e in scorecard["metrics"]:
        if e["metric"] == name:
            return e
    raise KeyError(name)
