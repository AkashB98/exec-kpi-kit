"""CLI: commands, exit codes, JSON/CSV round-trips, serve round-trips."""

import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli as cli_mod  # noqa: E402
from cli import EXIT_ERROR, EXIT_FAIL, EXIT_OK, main as cli_main, make_server  # noqa: E402
from generator import days_to_jsonl, generate_days  # noqa: E402


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli_main(argv)
    return code, out.getvalue(), err.getvalue()


class CliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kpi-test-")
        self.good = os.path.join(self.tmp, "good.jsonl")
        with open(self.good, "w", encoding="utf-8") as fh:
            fh.write(days_to_jsonl(generate_days()))
        self.calm = os.path.join(self.tmp, "calm.jsonl")
        with open(self.calm, "w", encoding="utf-8") as fh:
            fh.write(days_to_jsonl(
                [dict(r, support_tickets=20) for r in generate_days()]))


class TestGenerateAndMetrics(CliBase):
    def test_generate_to_file(self):
        out_path = os.path.join(self.tmp, "gen.jsonl")
        code, _, _ = run_cli(["generate", "--days", "10", "--seed", "3",
                              "--out", out_path])
        self.assertEqual(code, EXIT_OK)
        with open(out_path, encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().strip().splitlines()), 10)

    def test_generate_csv(self):
        out_path = os.path.join(self.tmp, "gen.csv")
        code, _, _ = run_cli(["generate", "--days", "10", "--out", out_path])
        self.assertEqual(code, EXIT_OK)
        with open(out_path, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(len(lines), 11)
        self.assertTrue(lines[0].startswith("date,visitors,orders"))

    def test_generate_deterministic_files(self):
        p1, p2 = (os.path.join(self.tmp, n) for n in ("a.jsonl", "b.jsonl"))
        run_cli(["generate", "--out", p1])
        run_cli(["generate", "--out", p2])
        with open(p1, "rb") as a, open(p2, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_metrics_lists_registry(self):
        code, out, _ = run_cli(["metrics"])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["count"], 8)
        names = [m["name"] for m in payload["metrics"]]
        self.assertIn("revenue", names)
        self.assertTrue(all("formula" not in m for m in payload["metrics"]))
        rev = payload["metrics"][names.index("revenue")]
        self.assertEqual(rev["target"], 900000.0)
        self.assertEqual(rev["owner"], "Growth")


class TestScorecardAnomaliesReport(CliBase):
    def test_scorecard_command(self):
        code, out, _ = run_cli(["scorecard", "--input", self.good])
        self.assertEqual(code, EXIT_OK)
        sc = json.loads(out)
        self.assertEqual(sc["status_counts"],
                         {"green": 6, "yellow": 1, "red": 1})
        self.assertEqual(len(sc["metrics"]), 8)

    def test_scorecard_csv_input_matches_jsonl(self):
        csv_path = os.path.join(self.tmp, "in.csv")
        run_cli(["generate", "--out", csv_path])
        code_csv, out_csv, _ = run_cli(["scorecard", "--input", csv_path])
        code_j, out_j, _ = run_cli(["scorecard", "--input", self.good])
        self.assertEqual((code_csv, code_j), (EXIT_OK, EXIT_OK))
        self.assertEqual(json.loads(out_csv), json.loads(out_j))

    def test_scorecard_missing_file(self):
        code, _, err = run_cli(["scorecard", "--input", "/tmp/nope-kpi.jsonl"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("not found", err)

    def test_scorecard_too_few_rows_is_error(self):
        short = os.path.join(self.tmp, "short.jsonl")
        with open(short, "w", encoding="utf-8") as fh:
            fh.write(days_to_jsonl(generate_days(10)))
        code, _, _ = run_cli(["scorecard", "--input", short])
        self.assertEqual(code, EXIT_ERROR)

    def test_anomalies_command(self):
        code, out, _ = run_cli(["anomalies", "--input", self.good])
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["count"], 12)
        self.assertEqual(len(payload["anomalies"]), 12)

    def test_report_command(self):
        code, out, _ = run_cli(["report", "--input", self.good])
        self.assertEqual(code, EXIT_OK)
        report = json.loads(out)
        self.assertEqual(report["anomaly_count"], 12)
        self.assertIn("Executive summary", report["narrative"])
        self.assertEqual(report["scorecard"]["status_counts"]["red"], 1)

    def test_json_array_input(self):
        arr = os.path.join(self.tmp, "arr.json")
        with open(arr, "w", encoding="utf-8") as fh:
            json.dump(generate_days(), fh)
        code, out, _ = run_cli(["scorecard", "--input", arr])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["status_counts"]["red"], 1)


class TestCheckGate(CliBase):
    def test_check_calm_passes(self):
        code, out, _ = run_cli(["check", "--input", self.calm])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("check PASS", out)

    def test_check_seeded_breaches_on_red_metric(self):
        code, out, _ = run_cli(["check", "--input", self.good])
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("support_tickets", out)

    def test_check_anomaly_limit_breach(self):
        code, out, _ = run_cli(["check", "--input", self.calm,
                                "--max-anomalies", "5"])
        self.assertEqual(code, EXIT_FAIL)
        self.assertIn("anomaly", out)

    def test_check_missing_file(self):
        code, _, _ = run_cli(["check", "--input", "/tmp/nope-kpi.jsonl"])
        self.assertEqual(code, EXIT_ERROR)

    def test_check_bad_data_is_error_not_breach(self):
        bad = os.path.join(self.tmp, "bad.jsonl")
        rows = generate_days()
        rows[3] = dict(rows[3], revenue=-50.0)
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(days_to_jsonl(rows))
        code, out, _ = run_cli(["check", "--input", bad])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("data quality", out)


class TestServe(CliBase):
    def setUp(self):
        super().setUp()
        cli_mod.reset_state(generate_days())
        self.server = make_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        cli_mod.reset_state()

    def _get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=10) as resp:
            return resp.status, json.loads(resp.read())

    def _post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())

    def test_health(self):
        status, body = self._get("/health")
        self.assertEqual((status, body), (200, {"status": "ok"}))

    def test_get_scorecard_matches_local(self):
        from scorecard import build_scorecard
        status, body = self._get("/scorecard")
        self.assertEqual(status, 200)
        self.assertEqual(body, build_scorecard(generate_days()))

    def test_get_report(self):
        status, body = self._get("/report")
        self.assertEqual(status, 200)
        self.assertEqual(body["anomaly_count"], 12)

    def test_post_report_with_rows(self):
        status, body = self._post("/report", {"rows": generate_days()})
        self.assertEqual(status, 200)
        self.assertIn("Executive summary", body["narrative"])

    def test_unknown_endpoint_404(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
