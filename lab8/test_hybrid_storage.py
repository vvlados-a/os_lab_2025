import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from hybrid_storage import DAY, HybridStorageManager, monitor


class HybridTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        warm_root = os.getenv("LAB8_WARM_TEST_ROOT")
        if warm_root and not os.path.ismount(warm_root):
            self.temp.cleanup()
            raise RuntimeError("LAB8_WARM_TEST_ROOT must be a real FUSE mount")
        self.warm_temp = tempfile.TemporaryDirectory(dir=warm_root or self.root)
        self.warm = Path(self.warm_temp.name)
        self.manager = self.reopen()

    def reopen(self):
        return HybridStorageManager(self.root / "hot", self.warm,
                                    self.root / "cold", self.root / "metadata.json")

    def tearDown(self):
        self.warm_temp.cleanup()
        self.temp.cleanup()

    def age(self, days):
        # Только тест меняет atime; пользовательского debug API нет.
        self.manager.metadata["demo.txt"]["last_accessed"] -= days * DAY
        self.manager._save()

    def test_three_tiers_promote_and_restart(self):
        print("\nput demo.txt -> HOT", flush=True)
        self.manager.put("demo.txt", b"Hello, Hybrid Storage!")
        self.age(8)
        self.assertEqual(self.manager.migrate(), [("demo.txt", "warm")])
        print("migrate (8 days) -> WARM; status:", self.manager.status(), flush=True)
        self.assertFalse((self.root / "hot/demo.txt").exists())
        self.manager = self.reopen()
        self.assertEqual(self.manager.get("demo.txt"), b"Hello, Hybrid Storage!")
        self.assertEqual(self.manager.status()["demo.txt"]["tier"], "hot")
        print("get from WARM -> HOT", flush=True)
        self.age(8)
        self.manager.migrate()
        self.age(23)
        self.assertEqual(self.manager.migrate(), [("demo.txt", "cold")])
        self.assertFalse((self.warm / "demo.txt").exists())
        print("migrate (31 days) -> COLD", flush=True)
        self.manager = self.reopen()
        self.assertEqual(self.manager.get("demo.txt"), b"Hello, Hybrid Storage!")
        self.assertEqual(self.manager.status()["demo.txt"]["tier"], "hot")
        self.assertFalse((self.root / "cold/demo.txt").exists())
        print("get from COLD -> HOT; bytes verified", flush=True)

    def test_policy_boundaries(self):
        with patch("hybrid_storage.time.time", return_value=40 * DAY):
            self.manager.put("demo.txt", b"data")
            self.age(7)
            self.assertEqual(self.manager.migrate(), [])
            self.age(1 / DAY)
            self.manager.migrate()
            self.assertEqual(self.manager.status()["demo.txt"]["tier"], "warm")
            self.age(23 - 1 / DAY)
            self.assertEqual(self.manager.migrate(), [])
            self.age(1 / DAY)
            self.manager.migrate()
            self.assertEqual(self.manager.status()["demo.txt"]["tier"], "cold")

    def test_failed_copy_preserves_source_and_metadata(self):
        self.manager.put("demo.txt", b"valuable")
        self.age(8)
        with patch("hybrid_storage.shutil.copyfile", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.manager.migrate()
        self.assertEqual(self.reopen().status()["demo.txt"]["tier"], "hot")
        self.assertEqual((self.root / "hot/demo.txt").read_bytes(), b"valuable")

    def test_corrupt_copy_preserves_source(self):
        self.manager.put("demo.txt", b"valuable")
        self.age(8)
        with patch("hybrid_storage.shutil.copyfile", side_effect=lambda src, dst: dst.write_bytes(b"bad")):
            with self.assertRaises(OSError):
                self.manager.migrate()
        self.assertEqual(self.reopen().get("demo.txt"), b"valuable")

    def test_metadata_failure_preserves_source(self):
        self.manager.put("demo.txt", b"valuable")
        self.age(8)
        with patch.object(self.manager, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.manager.migrate()
        self.assertEqual(self.reopen().status()["demo.txt"]["tier"], "hot")
        self.assertEqual((self.root / "hot/demo.txt").read_bytes(), b"valuable")

    def test_periodic_policy_check(self):
        self.manager.put("demo.txt", b"data")
        self.age(8)
        stop, migrated = threading.Event(), threading.Event()
        original = self.manager.migrate

        def checked():
            result = original()
            migrated.set()
            return result

        with patch.object(self.manager, "migrate", side_effect=checked):
            thread = threading.Thread(target=monitor, args=(self.manager, stop, .01))
            thread.start()
            try:
                self.assertTrue(migrated.wait(3), "Periodic migration did not run")
            finally:
                stop.set()
                thread.join()
        self.assertEqual(self.manager.status()["demo.txt"]["tier"], "warm")

    def test_invalid_names_duplicates_and_missing_files(self):
        for name in ("../escape", "/absolute", "a/b", "a\\b", ".."):
            with self.assertRaises(ValueError):
                self.manager.put(name, b"data")
        self.manager.put("demo.txt", b"data")
        with self.assertRaises(FileExistsError):
            self.manager.put("demo.txt", b"overwrite")
        with self.assertRaises(KeyError):
            self.manager.get("absent")


if __name__ == "__main__":
    unittest.main()
