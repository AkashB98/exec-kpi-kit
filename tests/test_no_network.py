"""No-network enforcement: with sockets blocked, generating, scoring,
detecting anomalies, narrating and validating must all still work.
(``serve`` is the only intentional exception — it binds loopback on
demand, and is not used here.)"""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Blocker:
    def __init__(self, *a, **k):
        raise RuntimeError("network access blocked in hermetic test")


class TestNoNetwork(unittest.TestCase):
    def setUp(self):
        self._real_socket = socket.socket
        socket.socket = _Blocker
        import urllib.request as urlreq
        self._real_urlopen = urlreq.urlopen
        urlreq.urlopen = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("network access blocked in hermetic test"))

    def tearDown(self):
        socket.socket = self._real_socket
        import urllib.request as urlreq
        urlreq.urlopen = self._real_urlopen

    def test_full_pipeline_offline(self):
        from anomalies import detect_anomalies
        from generator import generate_days
        from narrative import build_report
        from validation import validate_dataset
        rows = generate_days()
        self.assertEqual(validate_dataset(rows), [])
        report = build_report(rows)
        self.assertEqual(report["anomaly_count"], len(detect_anomalies(rows)))
        self.assertIn("Executive summary", report["narrative"])

    def test_no_module_opens_sockets_at_import(self):
        for mod in ("generator", "metrics", "scorecard", "anomalies",
                    "narrative", "validation", "cli", "demo"):
            sys.modules.pop(mod, None)
        import anomalies, cli, demo, generator, metrics, narrative  # noqa: F401
        import scorecard, validation  # noqa: F401
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
