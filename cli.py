"""CLI: generate | metrics | scorecard | anomalies | report | check | demo | serve.

SYNTHETIC DATA ONLY — Helios Home is a fictional company and every
dataset handled here is fabricated sample data.

Exit codes:
  check : 0 = pass, 1 = metric breach (any red metric, or anomaly
          count above --max-anomalies), 2 = usage / IO / data-quality
          error
  others: 0 = success, 2 = usage / IO error
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anomalies import detect_anomalies  # noqa: E402
from generator import generate_days, days_to_csv, days_to_jsonl  # noqa: E402
from metrics import METRICS, public_definition  # noqa: E402
from narrative import build_report  # noqa: E402
from scorecard import DEFAULT_PERIOD_DAYS, build_scorecard  # noqa: E402
from validation import validate_dataset  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_ERROR = 0, 1, 2
DEFAULT_MAX_ANOMALIES = 15


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


_FLOAT_FIELDS = ("conversion_rate", "avg_order_value", "revenue",
                 "refund_rate", "fulfillment_hours")
_INT_FIELDS = ("visitors", "orders", "support_tickets")


def _coerce_numbers(row: Dict) -> Dict:
    out = dict(row)
    for field in _FLOAT_FIELDS:
        if isinstance(out.get(field), str):
            try:
                out[field] = float(out[field])
            except ValueError:
                pass
    for field in _INT_FIELDS:
        if isinstance(out.get(field), str):
            try:
                out[field] = int(float(out[field]))
            except ValueError:
                pass
        if isinstance(out.get(field), float) and out[field].is_integer():
            out[field] = int(out[field])
    return out


def load_days(path: str) -> List[Dict]:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    stripped = text.strip()
    if not stripped:
        return []
    if path.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        return [_coerce_numbers(dict(row)) for row in reader]
    if stripped.startswith("["):
        return [_coerce_numbers(dict(x)) for x in json.loads(stripped)]
    rows = []
    for line in stripped.splitlines():
        if line.strip():
            rows.append(_coerce_numbers(json.loads(line)))
    return rows


def _load_or_error(path: str) -> Optional[List[Dict]]:
    try:
        return load_days(path)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
    except (ValueError, OSError) as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
    return None


def _write_out(args, text: str, summary: str) -> int:
    if getattr(args, "out", None):
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            print(f"error: cannot write {args.out}: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(summary)
    else:
        print(text, end="")
    return EXIT_OK


def cmd_generate(args) -> int:
    rows = generate_days(days=args.days, seed=args.seed)
    fmt = args.format
    if fmt is None:
        fmt = "csv" if (args.out and args.out.endswith(".csv")) else "jsonl"
    text = days_to_csv(rows) if fmt == "csv" else days_to_jsonl(rows)
    return _write_out(args, text,
                      f"generated {len(rows)} synthetic days "
                      f"(seed={args.seed}) -> {args.out}")


def cmd_metrics(args) -> int:
    payload = {"count": len(METRICS),
               "metrics": [public_definition(m) for m in METRICS]}
    return _write_out(args, canonical(payload) + "\n",
                      f"{len(METRICS)} metric definitions -> {args.out}")


def _scorecard_or_error(args):
    rows = _load_or_error(args.input)
    if rows is None:
        return None, EXIT_ERROR
    issues = validate_dataset(rows)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}", file=sys.stderr)
        return None, EXIT_ERROR
    try:
        return build_scorecard(rows, period_days=args.period_days), EXIT_OK
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None, EXIT_ERROR


def cmd_scorecard(args) -> int:
    scorecard, code = _scorecard_or_error(args)
    if scorecard is None:
        return code
    return _write_out(args, canonical(scorecard) + "\n",
                      f"scorecard -> {args.out}")


def cmd_anomalies(args) -> int:
    rows = _load_or_error(args.input)
    if rows is None:
        return EXIT_ERROR
    findings = detect_anomalies(rows, threshold=args.threshold)
    payload = {"count": len(findings), "anomalies": findings}
    return _write_out(args, canonical(payload) + "\n",
                      f"{len(findings)} anomalies -> {args.out}")


def cmd_report(args) -> int:
    rows = _load_or_error(args.input)
    if rows is None:
        return EXIT_ERROR
    issues = validate_dataset(rows)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}", file=sys.stderr)
        return EXIT_ERROR
    try:
        report = build_report(rows, period_days=args.period_days)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return _write_out(args, canonical(report) + "\n",
                      f"report -> {args.out}")


def cmd_check(args) -> int:
    rows = _load_or_error(args.input)
    if rows is None:
        return EXIT_ERROR
    issues = validate_dataset(rows)
    if issues:
        for issue in issues[:20]:
            print(f"data-quality: {issue}")
        print(f"check FAIL (data quality): {len(issues)} issue(s)")
        return EXIT_ERROR
    try:
        scorecard = build_scorecard(rows, period_days=args.period_days)
    except ValueError as exc:
        print(f"error: {exc}")
        return EXIT_ERROR
    findings = detect_anomalies(rows)
    reds = [e["metric"] for e in scorecard["metrics"]
            if e["status"] == "red"]
    print(f"days={len(rows)} statuses={scorecard['status_counts']} "
          f"red={reds} anomalies={len(findings)} "
          f"max_anomalies={args.max_anomalies}")
    if reds:
        print(f"check FAIL: red metric(s): {', '.join(reds)}")
        return EXIT_FAIL
    if len(findings) > args.max_anomalies:
        print("check FAIL: anomaly count above limit")
        return EXIT_FAIL
    print("check PASS")
    return EXIT_OK


def cmd_demo(args) -> int:
    import demo as demo_mod
    try:
        demo_mod.main()
    except AssertionError as exc:
        print(f"demo FAILED: {exc}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


# ------------------------------------------------------------------- serve

class _State:
    """Mutable dataset held by the serve process."""
    def __init__(self):
        self.rows: List[Dict] = generate_days()


_STATE = _State()


def get_state() -> _State:
    return _STATE


def reset_state(rows: Optional[List[Dict]] = None) -> None:
    _STATE.rows = list(rows) if rows is not None else generate_days()


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Any) -> None:
        self._send(code, (canonical(payload) + "\n").encode(),
                   "application/json")

    def _rows_from_body(self, body):
        if isinstance(body, dict) and "rows" in body:
            return [_coerce_numbers(dict(x)) for x in body["rows"]]
        if isinstance(body, list):
            return [_coerce_numbers(dict(x)) for x in body]
        return list(_STATE.rows)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if self.path == "/scorecard":
            try:
                return self._send_json(
                    200, build_scorecard(_STATE.rows))
            except ValueError as exc:
                return self._send_json(400, {"error": str(exc)})
        if self.path == "/report":
            try:
                return self._send_json(200, build_report(_STATE.rows))
            except ValueError as exc:
                return self._send_json(400, {"error": str(exc)})
        return self._send_json(404, {"error": "unknown endpoint"})

    def do_POST(self):  # noqa: N802
        if self.path not in ("/scorecard", "/report"):
            return self._send_json(404, {"error": "unknown endpoint"})
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            raw = self.rfile.read(length) if length else b""
            body = json.loads(raw) if raw.strip() else {}
            rows = self._rows_from_body(body)
            if isinstance(body, dict) and "rows" in body:
                _STATE.rows = rows
            period = int(body.get("period_days", DEFAULT_PERIOD_DAYS)) \
                if isinstance(body, dict) else DEFAULT_PERIOD_DAYS
            payload = build_scorecard(rows, period_days=period) \
                if self.path == "/scorecard" else \
                build_report(rows, period_days=period)
            return self._send_json(200, payload)
        except (ValueError, TypeError, KeyError) as exc:
            return self._send_json(400, {"error": f"bad request: {exc}"})

    def log_message(self, *a: Any) -> None:
        pass


def make_server(port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), _Handler)


def cmd_serve(args) -> int:
    if args.input:
        rows = _load_or_error(args.input)
        if rows is None:
            return EXIT_ERROR
        reset_state(rows)
    server = make_server(args.port)
    print(f"serving on http://127.0.0.1:{args.port}  "
          f"(GET /report, GET /scorecard, GET /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="exec-kpi-kit",
        description="Executive KPI scorecard automation "
                    "(Helios Home sample data).")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="generate a synthetic daily dataset")
    g.add_argument("--days", type=int, default=90)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", default=None)
    g.add_argument("--format", choices=["csv", "jsonl"], default=None)
    g.set_defaults(func=cmd_generate)

    m = sub.add_parser("metrics", help="list the metric definitions (registry)")
    m.add_argument("--out", default=None)
    m.set_defaults(func=cmd_metrics)

    s = sub.add_parser("scorecard", help="current vs prior vs target scorecard")
    s.add_argument("--input", required=True)
    s.add_argument("--period-days", type=int, default=DEFAULT_PERIOD_DAYS)
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_scorecard)

    a = sub.add_parser("anomalies", help="rolling-baseline anomaly flags")
    a.add_argument("--input", required=True)
    a.add_argument("--threshold", type=float, default=3.5)
    a.add_argument("--out", default=None)
    a.set_defaults(func=cmd_anomalies)

    r = sub.add_parser("report", help="scorecard + anomalies + narrative")
    r.add_argument("--input", required=True)
    r.add_argument("--period-days", type=int, default=DEFAULT_PERIOD_DAYS)
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_report)

    c = sub.add_parser("check", help="CI gate: exit 0 pass / 1 breach / 2 error")
    c.add_argument("--input", required=True)
    c.add_argument("--period-days", type=int, default=DEFAULT_PERIOD_DAYS)
    c.add_argument("--max-anomalies", type=int, default=DEFAULT_MAX_ANOMALIES)
    c.set_defaults(func=cmd_check)

    sub.add_parser("demo", help="run the end-to-end demo").set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="localhost JSON API")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--input", default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
