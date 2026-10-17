"""FUSE FS: метаданные и чанки по 4096 байт в SQLite."""

import argparse
import errno
import os
import posixpath
import sqlite3
import stat
import time
from pathlib import Path

BLOCK = 4096
# fusepy передаёт timespec в секундах, включая специальные tv_nsec libfuse2.
UTIME_NOW = ((1 << 30) - 1) / 1_000_000_000
UTIME_OMIT = ((1 << 30) - 2) / 1_000_000_000


class SQLiteFS:
    flag_utime_omit_ok = 1

    def __init__(self, database):
        self.db = sqlite3.connect(database)
        self.db.row_factory = sqlite3.Row
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(files)")}
        if columns and ("id" not in columns or "data" in columns):
            self.db.close()
            raise ValueError("Old SQLiteFS schema: use a new database, e.g. files-chunks.db; "
                             "the existing database has not been changed")
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("""CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL,
            parent TEXT, mode INTEGER NOT NULL,
            uid INTEGER NOT NULL, gid INTEGER NOT NULL, size INTEGER NOT NULL,
            atime REAL NOT NULL, mtime REAL NOT NULL, ctime REAL NOT NULL,
            nlink INTEGER NOT NULL)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS file_data (
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, data BLOB NOT NULL,
            PRIMARY KEY (file_id, chunk_index))""")
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO files VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("/", None, stat.S_IFDIR | 0o755,
                 getattr(os, "getuid", lambda: 0)(),
                 getattr(os, "getgid", lambda: 0)(), 0, now, now, now, 2))

    @staticmethod
    def _path(path):
        if not path.startswith("/") or "\0" in path:
            raise OSError(errno.EINVAL, "Invalid path")
        return "/" + posixpath.normpath(path).lstrip("/")

    def _node(self, path, directory=None):
        path = self._path(path)
        if path != "/":
            self._node(posixpath.dirname(path), directory=True)
        row = self.db.execute("SELECT * FROM files WHERE path = ?", (path,)).fetchone()
        if row is None:
            raise OSError(errno.ENOENT, path)
        is_dir = stat.S_ISDIR(row["mode"])
        if directory is True and not is_dir:
            raise OSError(errno.ENOTDIR, path)
        if directory is False and is_dir:
            raise OSError(errno.EISDIR, path)
        return row

    def getattr(self, path, fh=None):
        row = self._node(path)
        return {"st_" + key: row[key] for key in
                ("mode", "uid", "gid", "size", "atime", "mtime", "ctime", "nlink")}

    def readdir(self, path, fh=None):
        row = self._node(path, directory=True)
        children = self.db.execute(
            "SELECT path FROM files WHERE parent = ? ORDER BY path", (row["path"],))
        return [".", ".."] + [posixpath.basename(child[0]) for child in children]

    def chmod(self, path, mode):
        row = self._node(path)
        with self.db:
            self.db.execute("UPDATE files SET mode=?, ctime=? WHERE id=?",
                            (stat.S_IFMT(row["mode"]) | (mode & 0o7777), time.time(), row["id"]))
        return 0

    def chown(self, path, uid, gid):
        if uid < -1 or gid < -1:
            raise OSError(errno.EINVAL, path)
        row = self._node(path)
        with self.db:
            self.db.execute("UPDATE files SET uid=?, gid=?, ctime=? WHERE id=?",
                            (row["uid"] if uid == -1 else uid,
                             row["gid"] if gid == -1 else gid, time.time(), row["id"]))
        return 0

    def utimens(self, path, times=None):
        row = self._node(path)
        now = time.time()
        atime, mtime = (now, now) if times is None else times
        atime, mtime = (row[key] if value == UTIME_OMIT else
                        now if value == UTIME_NOW else value
                        for key, value in (("atime", atime), ("mtime", mtime)))
        with self.db:
            self.db.execute("UPDATE files SET atime=?, mtime=?, ctime=? WHERE id=?",
                            (atime, mtime, now, row["id"]))
        return 0

    def rename(self, old, new):
        source = self._node(old)
        old, new = source["path"], self._path(new)
        if old == "/" or new == "/":
            raise OSError(errno.EBUSY, old)
        if old == new:
            return 0
        directory = stat.S_ISDIR(source["mode"])
        if directory and new.startswith(old + "/"):
            raise OSError(errno.EINVAL, new)
        parent = posixpath.dirname(new)
        self._node(parent, directory=True)
        target = self.db.execute("SELECT * FROM files WHERE path=?", (new,)).fetchone()
        target_dir = target is not None and stat.S_ISDIR(target["mode"])
        if target is not None:
            if directory != target_dir:
                raise OSError(errno.ENOTDIR if directory else errno.EISDIR, new)
            if target_dir and self.db.execute(
                    "SELECT 1 FROM files WHERE parent=?", (new,)).fetchone():
                raise OSError(errno.ENOTEMPTY, new)
        prefix = old + "/"
        now = time.time()
        with self.db:
            if target is not None:
                self.db.execute("DELETE FROM files WHERE id=?", (target["id"],))
            # Постоянные id сохраняют связь с чанками. substr не трактует % и _ как шаблон.
            descendants = self.db.execute(
                "SELECT id, path, parent FROM files WHERE path=? OR substr(path, 1, ?)=?",
                (old, len(prefix), prefix)).fetchall()
            for row in descendants:
                new_parent = parent if row["path"] == old else new + row["parent"][len(old):]
                self.db.execute("UPDATE files SET path=?, parent=? WHERE id=?",
                                (new + row["path"][len(old):], new_parent, row["id"]))
            self.db.execute("UPDATE files SET ctime=? WHERE id=?", (now, source["id"]))
            self.db.execute("UPDATE files SET mtime=?, ctime=?, nlink=nlink-? WHERE path=?",
                            (now, now, int(directory), source["parent"]))
            self.db.execute("UPDATE files SET mtime=?, ctime=?, nlink=nlink+? WHERE path=?",
                            (now, now, int(directory) - int(target_dir), parent))
        return 0

    def _create(self, path, mode, directory):
        path = self._path(path)
        parent = posixpath.dirname(path)
        self._node(parent, directory=True)
        if self.db.execute("SELECT 1 FROM files WHERE path = ?", (path,)).fetchone():
            raise OSError(errno.EEXIST, path)
        now = time.time()
        with self.db:
            self.db.execute("INSERT INTO files VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (path, parent, (stat.S_IFDIR if directory else stat.S_IFREG)
                             | (mode & 0o777), getattr(os, "getuid", lambda: 0)(),
                             getattr(os, "getgid", lambda: 0)(), 0,
                             now, now, now, 2 if directory else 1))
            self.db.execute("UPDATE files SET mtime=?, ctime=?, nlink=nlink+? WHERE path=?",
                            (now, now, int(directory), parent))
        return 0

    def create(self, path, mode, fi=None):
        return self._create(path, mode, False)

    def mkdir(self, path, mode):
        return self._create(path, mode, True)

    def open(self, path, flags):
        self._node(path, directory=False)
        return 0

    def read(self, path, size, offset, fh=None):
        if size < 0 or offset < 0:
            raise OSError(errno.EINVAL, path)
        row = self._node(path, directory=False)
        with self.db:
            self.db.execute("UPDATE files SET atime=? WHERE path=?", (time.time(), row["path"]))
        end = min(row["size"], offset + size)
        if offset >= end:
            return b""
        data = bytearray(end - offset)
        chunks = self.db.execute(
            "SELECT chunk_index, data FROM file_data WHERE file_id=? AND chunk_index BETWEEN ? AND ?",
            (row["id"], offset // BLOCK, (end - 1) // BLOCK))
        for index, chunk in chunks:
            start = index * BLOCK
            left, right = max(offset, start), min(end, start + len(chunk))
            if left < right:
                data[left - offset:right - offset] = chunk[left - start:right - start]
        return bytes(data)

    def _set_size(self, row, size):
        now = time.time()
        self.db.execute("UPDATE files SET size=?, mtime=?, ctime=? WHERE id=?",
                        (size, now, now, row["id"]))

    def write(self, path, data, offset, fh=None):
        if offset < 0:
            raise OSError(errno.EINVAL, path)
        row = self._node(path, directory=False)
        if data:
            with self.db:
                written = 0
                while written < len(data):
                    index, within = divmod(offset + written, BLOCK)
                    count = min(BLOCK - within, len(data) - written)
                    stored = self.db.execute(
                        "SELECT data FROM file_data WHERE file_id=? AND chunk_index=?",
                        (row["id"], index)).fetchone()
                    chunk = bytearray((stored[0] if stored else b"").ljust(BLOCK, b"\0"))
                    chunk[within:within + count] = data[written:written + count]
                    self.db.execute("""INSERT INTO file_data VALUES (?, ?, ?)
                        ON CONFLICT(file_id, chunk_index) DO UPDATE SET data=excluded.data""",
                                    (row["id"], index, bytes(chunk)))
                    written += count
                self._set_size(row, max(row["size"], offset + len(data)))
        return len(data)

    def truncate(self, path, length, fh=None):
        if length < 0:
            raise OSError(errno.EINVAL, path)
        row = self._node(path, directory=False)
        with self.db:
            if length < row["size"]:
                self.db.execute("DELETE FROM file_data WHERE file_id=? AND chunk_index>=?",
                                (row["id"], (length + BLOCK - 1) // BLOCK))
                if length % BLOCK:
                    self.db.execute("""UPDATE file_data SET data=substr(data, 1, ?)
                        WHERE file_id=? AND chunk_index=?""",
                                    (length % BLOCK, row["id"], length // BLOCK))
            # Увеличение размера не выделяет чанки: отсутствующие блоки читаются как нули.
            self._set_size(row, length)
        return 0

    def _remove(self, path, directory):
        row = self._node(path, directory=directory)
        if row["path"] == "/":
            raise OSError(errno.EBUSY, path)
        if directory and self.db.execute(
                "SELECT 1 FROM files WHERE parent = ?", (row["path"],)).fetchone():
            raise OSError(errno.ENOTEMPTY, path)
        now = time.time()
        with self.db:
            self.db.execute("DELETE FROM files WHERE path=?", (row["path"],))
            self.db.execute("UPDATE files SET mtime=?, ctime=?, nlink=nlink-? WHERE path=?",
                            (now, now, int(directory), row["parent"]))
        return 0

    def unlink(self, path):
        return self._remove(path, False)

    def rmdir(self, path):
        return self._remove(path, True)

    def destroy(self, path=None):
        self.db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mountpoint", type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--foreground", action="store_true")
    args = parser.parse_args()
    mount = args.mountpoint.resolve()
    database = args.database.resolve()
    if not mount.is_dir() or any(mount.iterdir()):
        parser.error("mountpoint must be an empty existing directory")
    if database.is_relative_to(mount):
        parser.error("database must be outside mountpoint")
    from fuse import FUSE, FuseOSError, Operations

    class MountedSQLiteFS(SQLiteFS, Operations):
        def __call__(self, op, *arguments):
            try:
                return super().__call__(op, *arguments)
            except OSError as error:
                raise FuseOSError(error.errno) from error

    try:
        filesystem = MountedSQLiteFS(str(database))
    except ValueError as error:
        parser.error(str(error))
    FUSE(filesystem, str(mount),
         foreground=args.foreground, nothreads=True)


if __name__ == "__main__":
    main()
