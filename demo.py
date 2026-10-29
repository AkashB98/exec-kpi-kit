"""End-to-end demo: generate -> validate -> scorecard -> anomalies ->
narrative -> check -> serve.

SYNTHETIC DATA ONLY (fictional Helios Home dataset). Runs fully
offline; the serve round-trip is loopback-only on an ephemeral port.
Every stage asserts.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import EXIT_FAIL, EXIT_OK, main as cli_main, make_server, reset_state  # noqa: E402
from anomalies import detect_anomalies  # noqa: E402
from generator import generate_days  # noqa: E402
from narrative import build_report  # noqa: E402
from scorecard import build_scorecard, entry_for  # noqa: E402
from validation import validate_dataset  # noqa: E402


def _request(port: int, path: str, payload=None, method: str = "GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def main() -> None:
    print("== 1. generate synthetic Helios Home dataset (seed=42, 90 days) ==")
    rows = generate_days()
    again = generate_days()
    assert rows == again, "generator must be deterministic"
    assert len(rows) == 90 and rows[0]["date"] == "2026-01-01"
    assert rows[-1]["date"] == "2026-03-31"
    assert validate_dataset(rows) == [], validate_dataset(rows)[:3]
    total_revenue = round(sum(r["revenue"] for r in rows), 2)
    print(f"   90 days, deterministic re-generation verified, "
          f"total revenue ${total_revenue:,.2f}")

    print("\n== 2. scorecard: current vs prior vs target ==")
    scorecard = build_scorecard(rows)
    counts = scorecard["status_counts"]
    assert counts == {"green": 6, "yellow": 1, "red": 1}, counts
    assert entry_for(scorecard, "support_tickets")["status"] == "red"
    assert entry_for(scorecard, "conversion_rate")["status"] == "yellow"
    assert entry_for(scorecard, "orders")["delta"] == 0.0  # pinned tie
    print(f"   statuses={counts} "
          f"current={scorecard['current_period']['start']}.."
          f"{scorecard['current_period']['end']}")

    print("\n== 3. anomalies: planted incidents are flagged ==")
    findings = detect_anomalies(rows)
    keys = {(f["date"], f["metric"]) for f in findings}
    assert ("2026-02-15", "refund_rate") in keys
    assert ("2026-03-02", "revenue") in keys
    assert ("2026-01-31", "fulfillment_hours") in keys
    print(f"   {len(findings)} anomalies; refund spike, revenue dip and "
          f"fulfilment blowout all flagged")

    print("\n== 4. narrative: deterministic executive summary ==")
    report = build_report(rows)
    again_report = build_report(rows)
    assert report == again_report, "report must be deterministic"
    assert "support tickets" in report["narrative"].lower() or \
        "Support tickets" in report["narrative"]
    print("   " + report["narrative"].replace("\n", "\n   "))

    print("\n== 5. CLI check gate exit codes ==")
    import tempfile
    from generator import days_to_jsonl
    tmp = tempfile.mkdtemp(prefix="kpi-demo-")
    good_path = os.path.join(tmp, "good.jsonl")
    calm = [dict(r, support_tickets=20) for r in generate_days()]
    with open(good_path, "w", encoding="utf-8") as fh:
        fh.write(days_to_jsonl(calm))
    seeded_path = os.path.join(tmp, "seeded.jsonl")
    with open(seeded_path, "w", encoding="utf-8") as fh:
        fh.write(days_to_jsonl(rows))
    code_ok = cli_main(["check", "--input", good_path])
    code_breach = cli_main(["check", "--input", seeded_path])
    code_err = cli_main(["check", "--input", "/tmp/no-such-kpi-xyz.jsonl"])
    print(f"   calm={code_ok} seeded(red metric)={code_breach} "
          f"missing-file={code_err}")
    assert code_ok == EXIT_OK and code_breach == EXIT_FAIL and code_err == 2

    print("\n== 6. live localhost serve round-trip ==")
    reset_state(rows)
    server = make_server(0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = _request(port, "/health")
        assert status == 200 and health == {"status": "ok"}
        status, served_sc = _request(port, "/scorecard")
        assert status == 200 and served_sc == scorecard
        status, served_report = _request(port, "/report",
                                         payload={}, method="POST")
        assert status == 200 and served_report == report
        print("   GET /scorecard and POST /report match local computation")
    finally:
        server.shutdown()
        server.server_close()
        reset_state()

    print("\nDemo OK: generate, validate, scorecard, anomalies, narrative, "
          "check and serve verified.")


if __name__ == "__main__":
    main()
