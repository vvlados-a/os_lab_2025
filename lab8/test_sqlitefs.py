import errno
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlitefs import BLOCK, UTIME_NOW, UTIME_OMIT, SQLiteFS


class SQLiteFSTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.database = str(Path(self.temp.name) / "test.db")
        self.fs = SQLiteFS(self.database)

    def tearDown(self):
        self.fs.destroy()
        self.temp.cleanup()

    def error(self, code, operation, *args):
        with self.assertRaises(OSError) as caught:
            operation(*args)
        self.assertEqual(caught.exception.errno, code)

    def test_create_read_write_offsets_and_truncate(self):
        self.assertTrue(stat.S_ISDIR(self.fs.getattr("/")["st_mode"]))
        self.fs.create("/a", 0o640)
        self.assertTrue(stat.S_ISREG(self.fs.getattr("/a")["st_mode"]))
        self.assertEqual(self.fs.getattr("/a")["st_mode"] & 0o777, 0o640)
        self.assertEqual(self.fs.open("/a", os.O_RDWR), 0)
        self.assertEqual(self.fs.write("/a", b"abcdef", 0), 6)
        self.fs.write("/a", b"XY", 2)
        self.assertEqual(self.fs.read("/a", 3, 1), b"bXY")
        self.fs.write("/a", b"Z", 8)
        self.assertEqual(self.fs.read("/a", 100, 0), b"abXYef\0\0Z")
        self.fs.write("/a", b"", 100)
        self.assertEqual(self.fs.getattr("/a")["st_size"], 9)
        self.fs.truncate("/a", 2)
        self.fs.truncate("/a", 4)
        self.assertEqual(self.fs.read("/a", 100, 0), b"ab\0\0")
        self.assertEqual(self.fs.read("/a", 4, 100), b"")
        self.fs.truncate("/a", 0)
        self.assertEqual(self.fs.read("/a", 1, 0), b"")

    def test_directories_listing_and_delete(self):
        self.fs.mkdir("/dir", 0o755)
        self.fs.mkdir("/dir/sub", 0o700)
        self.fs.create("/dir/sub/file", 0o644)
        self.fs.create("/dir_2", 0o644)
        self.assertEqual(self.fs.readdir("/dir/"), [".", "..", "sub"])
        self.assertEqual(self.fs.getattr("/")["st_nlink"], 3)
        self.error(errno.ENOTEMPTY, self.fs.rmdir, "/dir/sub")
        self.fs.unlink("/dir/sub/file")
        self.fs.rmdir("/dir/sub")
        self.fs.rmdir("/dir")
        self.fs.unlink("/dir_2")
        self.assertEqual(self.fs.readdir("/"), [".", ".."])
        self.assertEqual(self.fs.getattr("/")["st_nlink"], 2)

    def test_errors(self):
        self.error(errno.ENOENT, self.fs.read, "/missing", 1, 0)
        self.error(errno.ENOENT, self.fs.create, "/missing/file", 0o644)
        self.fs.create("/file", 0o644)
        self.error(errno.EEXIST, self.fs.create, "/file", 0o644)
        self.error(errno.EEXIST, self.fs.mkdir, "/", 0o755)
        self.error(errno.ENOTDIR, self.fs.create, "/file/child", 0o644)
        self.error(errno.ENOTDIR, self.fs.readdir, "/file")
        self.error(errno.ENOTDIR, self.fs.rmdir, "/file")
        self.error(errno.EISDIR, self.fs.unlink, "/")
        self.error(errno.EISDIR, self.fs.open, "/", os.O_RDONLY)
        self.error(errno.EISDIR, self.fs.read, "/", 1, 0)
        self.error(errno.EBUSY, self.fs.rmdir, "/")
        self.error(errno.EINVAL, self.fs.write, "/file", b"a", -1)
        self.error(errno.EINVAL, self.fs.truncate, "/file", -1)
        self.error(errno.EINVAL, self.fs.read, "/file", -1, 0)
        self.error(errno.EINVAL, self.fs.read, "/file", 1, -1)
        self.error(errno.EISDIR, self.fs.write, "/", b"a", 0)
        self.error(errno.EISDIR, self.fs.truncate, "/", 0)
        self.error(errno.EINVAL, self.fs.getattr, "relative")
        self.error(errno.EINVAL, self.fs.getattr, "/bad\0name")
        for operation, arguments in ((self.fs.chmod, (0o600,)),
                                     (self.fs.chown, (1, 2)), (self.fs.utimens, ())):
            self.error(errno.ENOENT, operation, "/missing", *arguments)
        self.error(errno.EINVAL, self.fs.chown, "/file", -2, 0)

    def test_chmod_chown_and_restart(self):
        self.fs.create("/file", 0o644)
        self.fs.mkdir("/dir", 0o755)
        for name, kind in (("/file", stat.S_IFREG), ("/dir", stat.S_IFDIR)):
            before = self.fs.getattr(name)
            with patch("sqlitefs.time.time", return_value=before["st_ctime"] + 10):
                self.fs.chmod(name, 0o6750)
            changed = self.fs.getattr(name)
            self.assertEqual(changed["st_mode"], kind | 0o6750)
            self.assertEqual(changed["st_ctime"], before["st_ctime"] + 10)
            self.assertEqual(changed["st_mtime"], before["st_mtime"])
            with patch("sqlitefs.time.time", return_value=before["st_ctime"] + 20):
                self.fs.chown(name, 123, 456)
            self.assertEqual(self.fs.getattr(name)["st_ctime"], before["st_ctime"] + 20)
            self.fs.chown(name, -1, 789)
            self.assertEqual(self.fs.getattr(name)["st_uid"], 123)
            self.fs.chown(name, 321, -1)
            self.assertEqual(self.fs.getattr(name)["st_gid"], 789)
            self.fs.chown(name, -1, -1)
        saved = {name: self.fs.getattr(name) for name in ("/file", "/dir")}
        self.fs.destroy()
        self.fs = SQLiteFS(self.database)
        for name, attributes in saved.items():
            self.assertEqual(self.fs.getattr(name), attributes)
            self.assertEqual(attributes["st_uid"], 321)
            self.assertEqual(attributes["st_gid"], 789)

    def test_utimens_and_restart(self):
        self.fs.create("/file", 0o644)
        self.fs.mkdir("/dir", 0o755)
        with patch("sqlitefs.time.time", return_value=300.0):
            self.fs.utimens("/file", (100.5, 200.5))
            self.fs.utimens("/dir")
        saved = {name: self.fs.getattr(name) for name in ("/file", "/dir")}
        self.assertEqual(saved["/file"]["st_atime"], 100.5)
        self.assertEqual(saved["/file"]["st_mtime"], 200.5)
        self.assertEqual(saved["/file"]["st_ctime"], 300.0)
        self.assertEqual(saved["/dir"]["st_atime"], 300.0)
        self.assertEqual(saved["/dir"]["st_mtime"], 300.0)
        self.fs.destroy()
        self.fs = SQLiteFS(self.database)
        for name, attributes in saved.items():
            self.assertEqual(self.fs.getattr(name), attributes)

    def test_file_rename_move_and_replace(self):
        self.fs.mkdir("/dir", 0o755)
        self.fs.create("/source", 0o640)
        payload = b"source" * BLOCK
        self.fs.write("/source", payload, 0)
        before = self.fs.getattr("/source")
        file_id = self.fs._node("/source")["id"]
        self.fs.rename("/source", "/renamed")
        self.error(errno.ENOENT, self.fs.getattr, "/source")
        self.fs.rename("/renamed", "/dir/destination")
        after = self.fs.getattr("/dir/destination")
        for key in before:
            if key != "st_ctime":
                self.assertEqual(after[key], before[key])
        self.fs.create("/replace", 0o600)
        self.fs.write("/replace", b"old target", 0)
        removed_id = self.fs._node("/replace")["id"]
        self.fs.rename("/dir/destination", "/replace")
        self.assertEqual(self.fs._node("/replace")["id"], file_id)
        self.assertEqual(self.fs.read("/replace", len(payload), 0), payload)
        self.assertEqual(self.fs.db.execute(
            "SELECT count(*) FROM file_data WHERE file_id=?", (removed_id,)).fetchone()[0], 0)
        before = self.fs.getattr("/replace")
        self.assertEqual(self.fs.rename("/replace", "/replace"), 0)
        self.assertEqual(self.fs.getattr("/replace"), before)

    def test_touch_preserves_omitted_timestamp(self):
        self.fs.create("/file", 0o644)
        self.fs.utimens("/file", (100, 200))
        with patch("sqlitefs.time.time", return_value=300):
            self.fs.utimens("/file", (UTIME_NOW, UTIME_OMIT))
        self.assertEqual(self.fs.getattr("/file")["st_atime"], 300)
        self.assertEqual(self.fs.getattr("/file")["st_mtime"], 200)
        with patch("sqlitefs.time.time", return_value=400):
            self.fs.utimens("/file", (UTIME_OMIT, UTIME_NOW))
        self.assertEqual(self.fs.getattr("/file")["st_atime"], 300)
        self.assertEqual(self.fs.getattr("/file")["st_mtime"], 400)
        self.assertEqual(self.fs.getattr("/file")["st_ctime"], 400)

    def test_directory_rename_subtree_and_restart(self):
        for path in ("/left", "/right", "/left/tree_%", "/left/tree_%/sub", "/left/tree_%other"):
            self.fs.mkdir(path, 0o750)
        self.fs.create("/left/tree_%/sub/file", 0o600)
        payload = bytes(range(256)) * 40
        self.fs.write("/left/tree_%/sub/file", payload, 0)
        before = self.fs.getattr("/left/tree_%/sub/file")
        self.fs.rename("/left/tree_%", "/right/moved")
        self.assertEqual(self.fs.getattr("/left")["st_nlink"], 3)
        self.assertEqual(self.fs.getattr("/right")["st_nlink"], 3)
        self.assertEqual(self.fs.getattr("/right/moved/sub/file"), before)
        self.assertEqual(self.fs.readdir("/left"), [".", "..", "tree_%other"])
        self.fs.rename("/right/moved", "/right/renamed")
        self.fs.mkdir("/right/empty", 0o755)
        self.fs.rename("/right/renamed", "/right/empty")
        self.assertEqual(self.fs.getattr("/right")["st_nlink"], 3)
        self.fs.destroy()
        self.fs = SQLiteFS(self.database)
        self.assertEqual(self.fs.readdir("/right/empty"), [".", "..", "sub"])
        self.assertEqual(self.fs.read("/right/empty/sub/file", len(payload) + 10, 0), payload)
        self.error(errno.ENOENT, self.fs.getattr, "/left/tree_%")
        self.fs.unlink("/right/empty/sub/file")
        self.fs.rmdir("/right/empty/sub")
        self.fs.rmdir("/right/empty")
        self.assertEqual(self.fs.getattr("/right")["st_nlink"], 2)

    def test_rename_errors(self):
        for path in ("/a", "/a/sub", "/b"):
            self.fs.mkdir(path, 0o755)
        self.fs.create("/file", 0o644)
        self.fs.create("/b/occupied", 0o644)
        for code, old, new in ((errno.ENOENT, "/missing", "/new"),
                               (errno.ENOENT, "/file", "/missing/new"),
                               (errno.ENOTDIR, "/a", "/file/new"),
                               (errno.EINVAL, "/a", "/a/sub/new"),
                               (errno.EISDIR, "/file", "/a"),
                               (errno.ENOTDIR, "/a", "/file"),
                               (errno.ENOTEMPTY, "/a", "/b"),
                               (errno.EBUSY, "/", "/new"),
                               (errno.EBUSY, "/file", "/")):
            self.error(code, self.fs.rename, old, new)
        self.assertEqual(self.fs.readdir("/a"), [".", "..", "sub"])

    def test_rename_transaction_rolls_back(self):
        self.fs.mkdir("/src", 0o755)
        self.fs.mkdir("/src/sub", 0o755)
        self.fs.mkdir("/dst", 0o755)
        self.fs.create("/src/sub/file", 0o644)
        self.fs.write("/src/sub/file", b"data", 0)
        before = self.fs.db.execute("SELECT * FROM files ORDER BY id").fetchall()
        self.fs.db.execute("""CREATE TRIGGER fail_rename BEFORE UPDATE OF path ON files
            WHEN OLD.path='/src/sub' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.fs.rename("/src", "/dst")
        self.assertEqual(self.fs.db.execute("SELECT * FROM files ORDER BY id").fetchall(), before)
        self.assertEqual(self.fs.read("/src/sub/file", 10, 0), b"data")

    def test_chunk_boundaries_and_small_update(self):
        self.fs.create("/file", 0o644)
        expected = bytearray(bytes(range(256)) * 49)
        self.fs.write("/file", bytes(expected), 0)
        self.fs.write("/file", b"cross-boundary", BLOCK - 2)
        expected[BLOCK - 2:BLOCK - 2 + 14] = b"cross-boundary"
        self.assertEqual(self.fs.read("/file", 30, BLOCK - 8), expected[BLOCK - 8:BLOCK + 22])
        self.assertEqual(self.fs.read("/file", BLOCK + 4, BLOCK - 2),
                         expected[BLOCK - 2:2 * BLOCK + 2])
        # Небольшая запись должна менять только чанк 1, а не переписывать весь файл.
        for operation, reference in (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD")):
            self.fs.db.execute(f"""CREATE TRIGGER guard_{operation} BEFORE {operation} ON file_data
                WHEN {reference}.chunk_index != 1
                BEGIN SELECT RAISE(ABORT, 'unrelated chunk changed'); END""")
        self.fs.write("/file", b"PATCH", BLOCK + 7)
        expected[BLOCK + 7:BLOCK + 12] = b"PATCH"
        self.assertEqual(self.fs.read("/file", len(expected) + 1, 0), expected)
        self.assertEqual(self.fs.read("/file", 0, BLOCK), b"")
        self.assertTrue(all(row[0] <= BLOCK for row in
                            self.fs.db.execute("SELECT length(data) FROM file_data")))

    def test_sparse_chunks_truncate_delete_and_restart(self):
        self.fs.create("/file", 0o644)
        file_id = self.fs._node("/file")["id"]
        self.fs.write("/file", b"tail", 5 * BLOCK + 3)
        self.assertEqual(self.fs.db.execute("SELECT count(*) FROM file_data").fetchone()[0], 1)
        self.assertEqual(self.fs.read("/file", 20, 5 * BLOCK - 2), b"\0" * 5 + b"tail")
        self.assertEqual(self.fs.read("/file", BLOCK, BLOCK), b"\0" * BLOCK)
        self.fs.destroy()
        self.fs = SQLiteFS(self.database)
        self.assertEqual(self.fs.read("/file", 6 * BLOCK, 0), b"\0" * (5 * BLOCK + 3) + b"tail")
        self.fs.truncate("/file", BLOCK)
        self.fs.truncate("/file", 6 * BLOCK)
        self.assertEqual(self.fs.read("/file", 6 * BLOCK, 0), b"\0" * (6 * BLOCK))
        self.fs.write("/file", b"abcdef", BLOCK - 2)
        self.fs.truncate("/file", BLOCK + 1)
        self.fs.truncate("/file", BLOCK + 10)
        self.assertEqual(self.fs.read("/file", 20, BLOCK - 2), b"abc" + b"\0" * 9)
        self.fs.truncate("/file", 0)
        self.assertEqual(self.fs.db.execute("SELECT count(*) FROM file_data").fetchone()[0], 0)
        self.fs.write("/file", b"delete me" * BLOCK, 0)
        self.assertEqual(self.fs.db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            with self.fs.db:
                self.fs.db.execute("INSERT INTO file_data VALUES (?, 0, ?)", (-1, b"orphan"))
        self.fs.unlink("/file")
        self.assertEqual(self.fs.db.execute(
            "SELECT count(*) FROM file_data WHERE file_id=?", (file_id,)).fetchone()[0], 0)

    def test_old_schema_is_rejected_without_modification(self):
        legacy = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(legacy)
        with connection:
            connection.execute("CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB)")
            connection.execute("INSERT INTO files VALUES ('/old', ?)", (b"keep me",))
        connection.close()
        before = legacy.read_bytes()
        with self.assertRaisesRegex(ValueError, "Old SQLiteFS schema"):
            SQLiteFS(legacy)
        self.assertEqual(legacy.read_bytes(), before)

    def test_restart_preserves_data_and_metadata(self):
        self.fs.mkdir("/dir", 0o750)
        self.fs.create("/dir/file", 0o600)
        self.fs.write("/dir/file", b"persistent\0bytes", 0)
        before = self.fs.getattr("/dir/file")
        self.fs.destroy()
        self.fs = SQLiteFS(self.database)
        self.assertEqual(self.fs.getattr("/dir/file"), before)
        self.assertEqual(self.fs.read("/dir/file", 100, 0), b"persistent\0bytes")
        self.assertEqual(self.fs.readdir("/dir"), [".", "..", "file"])


if __name__ == "__main__":
    unittest.main()
