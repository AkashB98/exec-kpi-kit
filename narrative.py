"""Executive narrative + full report assembly.

The narrative is template-generated from the computed scorecard and
anomaly list — no language model, no randomness — so the same dataset
always produces the same paragraph, word for word. Every number in the
text is copied from the scorecard/anomaly structures; nothing is
recomputed or hard-coded here.
"""

from __future__ import annotations

from typing import Dict, List

from anomalies import anomaly_summary, detect_anomalies
from scorecard import build_scorecard

STATUS_WORD = {"green": "on target", "yellow": "watch", "red": "at risk"}


def _fmt(entry: Dict, value: float) -> str:
    unit = entry["unit"]
    if unit == "USD":
        return f"${value:,.2f}"
    if unit == "ratio":
        return f"{value * 100:.2f}%"
    if unit == "hours":
        return f"{value:.1f}h"
    return f"{value:,.0f}"


def _delta_phrase(entry: Dict) -> str:
    pct = entry["delta_pct"]
    if pct == 0:
        return "flat vs the prior period"
    direction = "up" if pct > 0 else "down"
    return f"{direction} {abs(pct):.1f}% vs the prior period"


def build_narrative(scorecard: Dict, findings: List[Dict]) -> str:
    counts = scorecard["status_counts"]
    cur = scorecard["current_period"]
    lines = []
    lines.append(
        f"Executive summary for {cur['start']} to {cur['end']}: "
        f"{counts['green']} metric(s) on target, {counts['yellow']} on "
        f"watch, {counts['red']} at risk.")
    # Top mover: largest absolute period delta.
    mover = max(scorecard["metrics"], key=lambda e: abs(e["delta_pct"]))
    lines.append(
        f"Biggest mover: {mover['label']} is {_delta_phrase(mover)}, at "
        f"{_fmt(mover, mover['current'])} against a target of "
        f"{_fmt(mover, mover['target'])} ({STATUS_WORD[mover['status']]}).")
    at_risk = [e for e in scorecard["metrics"] if e["status"] != "green"]
    if at_risk:
        parts = []
        for e in at_risk:
            parts.append(
                f"{e['label']} ({e['owner']}) is {STATUS_WORD[e['status']]} "
                f"at {_fmt(e, e['current'])} vs target "
                f"{_fmt(e, e['target'])}, {_delta_phrase(e)}")
        lines.append("Needs attention: " + "; ".join(parts) + ".")
    else:
        lines.append("Needs attention: none — every metric is on target.")
    summary = anomaly_summary(findings)
    if summary["count"]:
        worst = summary["worst"]
        lines.append(
            f"Anomalies: {summary['count']} anomalous day(s) flagged. "
            f"The most extreme was {worst['metric']} on {worst['date']} "
            f"(z-score {worst['z_score']}), value {worst['value']} vs an "
            f"expected {worst['expected']}.")
    else:
        lines.append("Anomalies: none flagged in the period covered.")
    return "\n".join(lines)


def build_report(rows: List[Dict], period_days: int = 30) -> Dict:
    """Full report: scorecard + anomalies + narrative, one structure."""
    scorecard = build_scorecard(rows, period_days=period_days)
    findings = detect_anomalies(rows)
    return {
        "scorecard": scorecard,
        "anomalies": findings,
        "anomaly_count": len(findings),
        "narrative": build_narrative(scorecard, findings),
    }
