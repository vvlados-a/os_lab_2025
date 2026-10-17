"""Три уровня хранения и небольшая интерактивная демонстрация."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import threading
import time
import uuid
from pathlib import Path

DAY = 86400


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class HybridStorageManager:
    """Один процесс приложения владеет metadata.json; потоки защищены RLock."""
    def __init__(self, hot_path, warm_path, cold_path, metadata_path):
        self.paths = {"hot": Path(hot_path), "warm": Path(warm_path), "cold": Path(cold_path)}
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata = json.loads(self.metadata_path.read_text()) if self.metadata_path.exists() else {}
        self.lock = threading.RLock()

    @staticmethod
    def _name(name):
        # Для минимума PoC принимает одно имя, а не произвольный путь хоста.
        if not name or name in (".", "..") or any(c in name for c in ("/", "\\", "\0", ":")):
            raise ValueError("Expected a filename without directory components")
        return name

    def _save(self):
        temporary = self.metadata_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.metadata, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.metadata_path)

    def _move(self, name, tier):
        meta = self.metadata[name]
        source = self.paths[meta["tier"]] / name
        target = self.paths[tier] / name
        temporary = target.with_name(".lab8-" + uuid.uuid4().hex)
        if checksum(source) != meta["checksum"]:
            raise OSError("Source checksum mismatch: " + name)
        try:
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != meta["size"] or checksum(temporary) != meta["checksum"]:
                raise OSError("Copy verification failed: " + name)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        previous = meta["tier"]
        meta["tier"] = tier
        try:
            self._save()
        except Exception:
            meta["tier"] = previous
            raise
        # Сначала проверенная копия и сохранённые метаданные; исходник удаляется последним.
        source.unlink()

    def put(self, filename, data):
        name = self._name(filename)
        with self.lock:
            if name in self.metadata:
                raise FileExistsError(name)
            target = self.paths["hot"] / name
            temporary = target.with_name(".lab8-" + uuid.uuid4().hex)
            expected = hashlib.sha256(data).hexdigest()
            try:
                temporary.write_bytes(data)
                if checksum(temporary) != expected:
                    raise OSError("Write verification failed")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            now = time.time()
            self.metadata[name] = {"tier": "hot", "size": len(data), "checksum": expected,
                                   "created_at": now, "last_accessed": now, "access_count": 0}
            try:
                self._save()
            except Exception:
                del self.metadata[name]
                raise
            return dict(self.metadata[name])

    def get(self, filename):
        name = self._name(filename)
        with self.lock:
            meta = self.metadata[name]
            if meta["tier"] != "hot":
                self._move(name, "hot")
            data = (self.paths["hot"] / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != meta["checksum"]:
                raise OSError("Read checksum mismatch: " + name)
            meta["last_accessed"] = time.time()
            meta["access_count"] += 1
            self._save()
            return data

    def status(self):
        with self.lock:
            return {name: dict(meta) for name, meta in self.metadata.items()}

    def migrate(self):
        moved = []
        with self.lock:
            now = time.time()
            for name, meta in self.metadata.items():
                age = now - meta["last_accessed"]
                if meta["tier"] == "hot" and age > 7 * DAY:
                    self._move(name, "warm")
                    moved.append((name, "warm"))
                elif meta["tier"] == "warm" and age > 30 * DAY:
                    self._move(name, "cold")
                    moved.append((name, "cold"))
        return moved


def monitor(manager, stop, interval):
    while not stop.wait(interval):
        try:
            moved = manager.migrate()
            if moved:
                print("automatic migrate:", moved, flush=True)
        except Exception as error:
            print("automatic migrate error:", error, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("/data"))
    parser.add_argument("--warm", type=Path, default=Path("/mnt/warm"))
    parser.add_argument("--interval", type=float, default=60)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("interval must be positive")
    if not os.path.ismount(args.warm):
        parser.error("WARM must be a real s3fs mount")
    manager = HybridStorageManager(args.data / "hot", args.warm,
                                   args.data / "cold", args.data / "metadata.json")
    stop = threading.Event()
    thread = threading.Thread(target=monitor, args=(manager, stop, args.interval), daemon=True)
    thread.start()
    print("Commands: put NAME TEXT | get NAME | status | migrate | quit", flush=True)
    try:
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            try:
                words = shlex.split(line)
                if not words:
                    continue
                if words == ["quit"]:
                    break
                if words[0] == "put" and len(words) >= 3:
                    print(manager.put(words[1], " ".join(words[2:]).encode("utf-8")))
                elif words[0] == "get" and len(words) == 2:
                    print(manager.get(words[1]).decode("utf-8", errors="replace"))
                elif words == ["status"]:
                    print(json.dumps(manager.status(), ensure_ascii=False, indent=2))
                elif words == ["migrate"]:
                    print(manager.migrate())
                else:
                    print("Unknown command or wrong arguments")
            except (OSError, ValueError, KeyError) as error:
                print(type(error).__name__ + ": " + str(error))
    except KeyboardInterrupt:
        print()
    finally:
        stop.set()
        thread.join()


if __name__ == "__main__":
    main()
