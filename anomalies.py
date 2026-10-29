"""Anomaly detection: rolling-baseline z-scores over daily series.

For each watched daily field, each day is compared with the previous
``window`` days of that same field (its rolling baseline): the baseline
mean is what the day was "expected" to look like, and the **z-score**
(how many standard deviations the actual value sits from that mean)
says how surprising the day was. Days with |z| >= ``threshold`` are
flagged, with the evidence attached: date, value, expected (baseline
mean), and z. The first ``min_history`` days are never flagged — there
is not enough baseline to judge them.

Edge case: a baseline with zero variance (a perfectly flat series).
Any deviation from it is flagged — it is the most surprising case of
all — with the z-score reported as +/-999.9, a sentinel meaning "the
true z is unbounded", since a literal infinity is not JSON-safe.

Pure stdlib statistics, fully deterministic: same rows, same flags.
"""

from __future__ import annotations

import math
from typing import Dict, List

from metrics import DAILY_FIELDS

ZERO_VARIANCE_Z = 999.9
DEFAULT_WINDOW = 14
DEFAULT_THRESHOLD = 3.5
DEFAULT_MIN_HISTORY = 7


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs)


def _pstdev(xs: List[float], mean: float) -> float:
    return math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))


def detect_anomalies(rows: List[Dict], window: int = DEFAULT_WINDOW,
                     threshold: float = DEFAULT_THRESHOLD,
                     min_history: int = DEFAULT_MIN_HISTORY,
                     fields: List[str] = None) -> List[Dict]:
    """Flag anomalous days per field, ordered by (date, field)."""
    fields = fields if fields is not None else DAILY_FIELDS
    findings: List[Dict] = []
    for field in fields:
        series = [float(r[field]) for r in rows]
        for i, value in enumerate(series):
            history = series[max(0, i - window):i]
            if len(history) < min_history:
                continue
            mean = _mean(history)
            std = _pstdev(history, mean)
            if std == 0.0:
                if value == mean:
                    continue
                z = ZERO_VARIANCE_Z if value > mean else -ZERO_VARIANCE_Z
            else:
                z = (value - mean) / std
            if abs(z) >= threshold:
                findings.append({
                    "date": rows[i]["date"],
                    "metric": field,
                    "value": round(value, 6),
                    "expected": round(mean, 6),
                    "z_score": round(z, 4),
                    "direction": "high" if z > 0 else "low",
                })
    findings.sort(key=lambda f: (f["date"], f["metric"]))
    return findings


def anomaly_summary(findings: List[Dict]) -> Dict:
    """Count + worst offender, for reports and the check gate."""
    if not findings:
        return {"count": 0, "worst": None}
    worst = max(findings, key=lambda f: (abs(f["z_score"]), f["date"],
                                         f["metric"]))
    return {"count": len(findings), "worst": worst}
