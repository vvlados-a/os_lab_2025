import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from benchmark import Storage, cleanup, measure


class BenchmarkTest(unittest.TestCase):
    def test_filesystem_content_and_ranges(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            storage = Storage(None, "run", root)
            self.assertEqual(storage.write("file", b"0123456789"), 10)
            self.assertEqual(storage.read("file", b"0123456789"), 10)
            self.assertEqual(storage.read("file", b"345", 3), 3)
            with self.assertRaises(OSError):
                storage.read("file", b"bad")

    def test_metrics_and_errors(self):
        row = measure("test", "write", 4, lambda i: 4096)
        self.assertEqual(row["bytes"], 16384)
        self.assertEqual(row["successes"], 4)
        self.assertEqual(row["errors"], 0)
        self.assertAlmostEqual(row["iops"] * row["elapsed_s"], 4)
        self.assertAlmostEqual(row["throughput_MB_s"] * row["elapsed_s"], .016384)
        self.assertGreaterEqual(row["latency_p99_ms"], row["latency_avg_ms"])
        failed = measure("test", "read", 2, lambda i: 1 / 0)
        self.assertEqual(failed["errors"], 2)
        self.assertEqual(failed["throughput_MB_s"], 0)
        self.assertIsNone(failed["latency_avg_ms"])
        self.assertIn("ZeroDivisionError", failed["samples"][0]["error"])

    def test_s3_range_and_body_close(self):
        client = Mock()
        body = Mock()
        client.get_object.return_value = {"Body": body}
        body.__enter__ = Mock(return_value=body)
        body.__exit__ = Mock(return_value=False)
        body.read.return_value = b"abc"
        storage = Storage(client, "run")
        self.assertEqual(storage.read("file", b"abc", 4), 3)
        client.get_object.assert_called_once_with(
            Bucket="lab8-benchmark", Key="run/file", Range="bytes=4-6")
        body.__exit__.assert_called_once()

    def test_cleanup_rejects_foreign_prefix(self):
        with self.assertRaises(ValueError):
            cleanup(Mock(), "somebody-else/")


if __name__ == "__main__":
    unittest.main()
