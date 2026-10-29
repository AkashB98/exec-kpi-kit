"""Golden evals for exec-kpi-kit.

SYNTHETIC DATA ONLY (fictional Helios Home dataset). Every eval is
deterministic: run_evals.py writes eval_report.json and the file must
be byte-identical across runs. No timestamps, ports, or temp paths
enter the report — only names, booleans, pinned counts and hashes.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomalies import detect_anomalies  # noqa: E402
from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, load_days, main as cli_main, make_server, reset_state  # noqa: E402
from generator import days_to_jsonl, generate_days  # noqa: E402
from metrics import METRICS, compute_value, get_metric  # noqa: E402
from narrative import build_report  # noqa: E402
from scorecard import build_scorecard, entry_for, status_for  # noqa: E402
from validation import validate_dataset, validate_day  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURE = os.path.join(ROOT, "fixtures", "sample_90d.jsonl")
RESULTS = []


def check(name, passed, detail=""):
    RESULTS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def _run_cli(argv):
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return cli_main(argv)


def main():
    print("== golden evals: exec-kpi-kit ==")
    rows = generate_days()

    # E1: generator determinism (bytes pinned)
    text1 = days_to_jsonl(generate_days())
    text2 = days_to_jsonl(generate_days())
    md5 = hashlib.md5(text1.encode()).hexdigest()
    check("E1 generator determinism (seed=42, 90 days)",
          text1 == text2 and len(rows) == 90
          and md5 == "9803f5f967d1b8f74ce370e3ec331d98",
          f"jsonl_md5={md5}")

    # E2: scorecard pinned (statuses, headline values, the orders tie)
    sc = build_scorecard(rows)
    check("E2 scorecard pinned (6 green / 1 yellow / 1 red, orders tie)",
          sc["status_counts"] == {"green": 6, "yellow": 1, "red": 1}
          and entry_for(sc, "revenue")["current"] == 1092371.1
          and entry_for(sc, "orders")["delta"] == 0.0
          and entry_for(sc, "support_tickets")["status"] == "red"
          and entry_for(sc, "conversion_rate")["status"] == "yellow",
          f"{sc['status_counts']}")

    # E3: registry integrity (8 metrics, threshold ordering, owners)
    ordering = all(
        (m["target"] > m["warn"] > m["critical"]) if m["direction"] == "higher"
        else (m["target"] < m["warn"] < m["critical"]) for m in METRICS)
    check("E3 registry integrity (8 metrics, thresholds ordered by direction)",
          len(METRICS) == 8 and ordering
          and all(m["owner"] for m in METRICS))

    # E4: formulas are ratio-of-totals, not mean-of-ratios (hand-computed)
    hand = [
        {"date": "2026-01-01", "visitors": 1000, "orders": 40,
         "conversion_rate": 0.04, "avg_order_value": 50.0, "revenue": 2000.0,
         "refund_rate": 0.02, "support_tickets": 10,
         "fulfillment_hours": 20.0},
        {"date": "2026-01-02", "visitors": 3000, "orders": 60,
         "conversion_rate": 0.02, "avg_order_value": 100.0, "revenue": 6000.0,
         "refund_rate": 0.04, "support_tickets": 30,
         "fulfillment_hours": 28.0},
    ]
    check("E4 period formulas hand-computed (conversion 0.025, AOV 80)",
          compute_value(get_metric("conversion_rate"), hand) == 0.025
          and compute_value(get_metric("avg_order_value"), hand) == 80.0
          and compute_value(get_metric("revenue"), hand) == 8000.0)

    # E5: status boundaries pinned in both directions
    rev, ref = get_metric("revenue"), get_metric("refund_rate")
    bounds = (status_for(rev, 900000.0) == "green"
              and status_for(rev, 899999.0) == "yellow"
              and status_for(rev, 819999.0) == "red"
              and status_for(ref, 0.022) == "green"
              and status_for(ref, 0.030) == "yellow"
              and status_for(ref, 0.031) == "red")
    check("E5 status boundaries at target / warn pinned (both directions)",
          bounds)

    # E6: anomalies pinned (12 total, all three planted incidents)
    findings = detect_anomalies(rows)
    keys = {(f["date"], f["metric"]) for f in findings}
    check("E6 anomalies pinned (12; dip, refund spike, fulfilment blowout)",
          len(findings) == 12
          and ("2026-03-02", "revenue") in keys
          and ("2026-02-15", "refund_rate") in keys
          and ("2026-01-31", "fulfillment_hours") in keys,
          f"count={len(findings)}")

    # E7: zero-variance baseline flags any deviation (sentinel z)
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from helpers import day, days_block  # noqa: E402
    flat = days_block(30)
    flat[20] = day(flat[20]["date"], revenue=200000.0)
    hits = [f for f in detect_anomalies(flat) if f["metric"] == "revenue"]
    check("E7 zero-variance baseline flags spike with sentinel z=999.9",
          len(hits) == 1 and hits[0]["z_score"] == 999.9
          and detect_anomalies(days_block(30)) == [])

    # E8: validation flags planted defects, generated book clean
    bad = dict(rows[0], revenue=-5.0, refund_rate=1.7)
    planted = validate_day(bad)
    gap = validate_dataset(rows[:10] + rows[12:])
    check("E8 validation flags planted defects, generated book clean",
          len(planted) == 2 and any("date gap" in i for i in gap)
          and validate_dataset(rows) == [], f"planted={planted}")

    # E9: narrative deterministic and sourced from the scorecard
    r1, r2 = build_report(rows), build_report(rows)
    check("E9 narrative deterministic, headline + worst anomaly pinned",
          r1 == r2
          and "6 metric(s) on target, 1 on watch, 1 at risk"
          in r1["narrative"]
          and "refund_rate on 2026-02-15" in r1["narrative"]
          and "Biggest mover: Refund rate is down 16.5%"
          in r1["narrative"])

    # E10: CLI check exit codes 0 / 1 / 2
    import tempfile
    tmp = tempfile.mkdtemp(prefix="kpi-evals-")
    calm_path = os.path.join(tmp, "calm.jsonl")
    with open(calm_path, "w", encoding="utf-8") as fh:
        fh.write(days_to_jsonl(
            [dict(r, support_tickets=20) for r in rows]))
    seeded_path = os.path.join(tmp, "seeded.jsonl")
    with open(seeded_path, "w", encoding="utf-8") as fh:
        fh.write(days_to_jsonl(rows))
    codes = (_run_cli(["check", "--input", calm_path]),
             _run_cli(["check", "--input", seeded_path]),
             _run_cli(["check", "--input", "/tmp/no-such-kpi-xyz.jsonl"]))
    check("E10 CLI check exit codes 0/1/2",
          codes == (EXIT_OK, EXIT_FAIL, EXIT_ERROR), f"codes={codes}")

    # E11: serve round-trip matches local computation
    reset_state(rows)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/scorecard",
                                    timeout=10) as resp:
            served_sc = json.loads(resp.read())
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/report", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            served_report = json.loads(resp.read())
        serve_ok = served_sc == build_scorecard(rows) \
            and served_report == build_report(rows)
    finally:
        server.shutdown()
        server.server_close()
        reset_state()
    check("E11 serve round-trip matches local scorecard + report", serve_ok)

    # E12: bundled fixture pinned (90 days, clean, totals pinned)
    fixture = load_days(FIXTURE)
    total_rev = round(sum(r["revenue"] for r in fixture), 2)
    check("E12 fixture pinned (90 days, revenue $3,068,233.69, clean)",
          len(fixture) == 90 and total_rev == 3068233.69
          and validate_dataset(fixture) == []
          and build_scorecard(fixture) == sc,
          f"total_revenue={total_rev}")

    passed = sum(1 for r in RESULTS if r["passed"])
    total = len(RESULTS)
    summary_doc = {"passed": passed, "total": total,
                   "all_passed": passed == total, "evals": RESULTS}
    with open(os.path.join(HERE, "eval_report.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary_doc, sort_keys=True) + "\n")
    print(f"\n{passed}/{total} evals passed -> evals/eval_report.json")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
