"""Одинаковые нагрузки через s3fs, goofys и boto3, сырые JSON и графики."""

import argparse
import importlib.metadata
import json
import math
import os
import platform
import random
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BLOCK = 4096
BUCKETS = ("lab8-benchmark", "lab8-hybrid")


def s3_client(endpoint):
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1",
                        config=Config(signature_version="s3v4",
                                      s3={"addressing_style": "path"},
                                      retries={"max_attempts": 0},
                                      connect_timeout=5, read_timeout=30))


def initialize(client):
    from botocore.exceptions import ClientError
    for bucket in BUCKETS:
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
            client.create_bucket(Bucket=bucket)


class Storage:
    """Один интерфейс; root=None означает нативный S3 API."""
    def __init__(self, client, prefix, root=None):
        self.client, self.prefix = client, prefix
        self.root = Path(root) if root is not None else None
        if self.root is not None:
            (self.root / prefix).mkdir(parents=True, exist_ok=False)

    def write(self, name, data):
        key = self.prefix + "/" + name
        if self.root is None:
            self.client.put_object(Bucket=BUCKETS[0], Key=key, Body=data)
        else:
            # close включён в измерение: у goofys fsync не гарантирует upload.
            with (self.root / key).open("wb") as stream:
                if stream.write(data) != len(data):
                    raise OSError("Short write")
        return len(data)

    def read(self, name, expected, offset=None):
        key = self.prefix + "/" + name
        if self.root is None:
            options = {} if offset is None else {
                "Range": f"bytes={offset}-{offset + len(expected) - 1}"}
            response = self.client.get_object(Bucket=BUCKETS[0], Key=key, **options)
            with response["Body"] as stream:
                data = stream.read()
        else:
            with (self.root / key).open("rb") as stream:
                if offset is not None:
                    stream.seek(offset)
                data = stream.read() if offset is None else stream.read(len(expected))
        if data != expected:
            raise OSError("Read content mismatch")
        return len(data)


def measure(method, workload, count, operation):
    samples = []
    start = time.perf_counter()
    for index in range(count):
        began = time.perf_counter()
        size, error = 0, None
        try:
            size = operation(index)
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
        samples.append({"index": index, "bytes": size,
                        "latency_ms": (time.perf_counter() - began) * 1000,
                        "error": error})
    elapsed = time.perf_counter() - start
    good = [sample for sample in samples if sample["error"] is None]
    latencies = sorted(sample["latency_ms"] for sample in good)
    size = sum(sample["bytes"] for sample in good)
    return {"method": method, "workload": workload, "attempts": count,
            "successes": len(good), "errors": count - len(good),
            "bytes": size, "elapsed_s": elapsed,
            "throughput_MB_s": size / 1_000_000 / elapsed,
            "iops": len(good) / elapsed,
            "latency_avg_ms": statistics.mean(latencies) if good else None,
            "latency_p95_ms": latencies[math.ceil(len(good) * .95) - 1] if good else None,
            "latency_p99_ms": latencies[math.ceil(len(good) * .99) - 1] if good else None,
            "samples": samples}


def plot(document, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = document["results"]
    workloads = list(dict.fromkeys(row["workload"] for row in rows))
    fig, axes = plt.subplots(len(workloads), 3, figsize=(14, 3.1 * len(workloads)),
                             squeeze=False)
    for index, workload in enumerate(workloads):
        subset = [row for row in rows if row["workload"] == workload]
        names = [row["method"] for row in subset]
        for column, (metric, label) in enumerate(
                (("throughput_MB_s", "MB/s"), ("iops", "IOPS"))):
            axes[index, column].bar(names, [row[metric] for row in subset])
            axes[index, column].set_title(f"{workload}: {label}")
            axes[index, column].set_ylim(bottom=0)
        axis = axes[index, 2]
        for shift, (metric, label) in enumerate((("latency_avg_ms", "avg"),
                                               ("latency_p95_ms", "p95"),
                                               ("latency_p99_ms", "p99"))):
            axis.bar([n + (shift - 1) * .25 for n in range(len(subset))],
                     [row[metric] if row[metric] is not None else float("nan")
                      for row in subset], width=.25, label=label)
        axis.set_xticks(range(len(names)), names)
        axis.set_title(f"{workload}: latency (ms), successful ops")
        axis.legend()
        for column in range(3):
            axes[index, column].set_xlabel(
                "; ".join(f"{row['method']}: {row['errors']} errors" for row in subset))
    fig.suptitle("Local MinIO; client caches retained; 1 MB/s = 1,000,000 B/s")
    fig.tight_layout(rect=(0, 0, 1, .98))
    fig.savefig(output, dpi=130)
    plt.close(fig)


def cleanup(client, prefix):
    # Только уникальный префикс одного запуска; bucket и чужие ключи не удаляем.
    parts = prefix.split("/")
    if len(parts) != 2 or parts[0] != "lab8-bench" or len(parts[1]) != 32:
        raise ValueError("Expected lab8-bench/<32 hexadecimal characters>")
    int(parts[1], 16)
    for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKETS[0], Prefix=prefix + "/"):
        objects = [{"Key": entry["Key"]} for entry in page.get("Contents", [])]
        if objects:
            response = client.delete_objects(Bucket=BUCKETS[0], Delete={"Objects": objects})
            if response.get("Errors"):
                raise OSError(response["Errors"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.getenv("S3_ENDPOINT", "http://localhost:9000"))
    parser.add_argument("--methods", nargs="+", choices=("s3fs", "goofys", "boto3"),
                        default=["s3fs", "goofys", "boto3"])
    parser.add_argument("--s3fs", type=Path, default=Path("/mnt/s3fs"))
    parser.add_argument("--goofys", type=Path, default=Path("/mnt/goofys"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--small-count", type=int, default=1000)
    parser.add_argument("--random-count", type=int, default=1000)
    parser.add_argument("--size", type=int, default=1024 * 1024)
    parser.add_argument("--output", type=Path, default=Path("results/benchmark.json"))
    parser.add_argument("--plot", type=Path, help="Replot existing JSON without storage access")
    parser.add_argument("--init", action="store_true", help="Create the two lab buckets")
    parser.add_argument("--cleanup", type=Path, help="Delete only the run prefix from this JSON")
    args = parser.parse_args()
    if args.plot:
        plot(json.loads(args.plot.read_text()), args.plot.with_suffix(".png"))
        return
    if min(args.count, args.small_count, args.random_count) < 1 or args.size < BLOCK:
        parser.error("Counts must be positive; size must be at least 4096")
    client = s3_client(args.endpoint)
    if args.init:
        initialize(client)
        return
    if args.cleanup:
        cleanup(client, json.loads(args.cleanup.read_text())["prefix"])
        return
    mounts = Path("/proc/mounts").read_text().splitlines() if Path("/proc/mounts").exists() else []
    for method in args.methods:
        if method != "boto3":
            point = str(getattr(args, method).resolve())
            if not os.path.ismount(point) or not any(
                    line.split()[1] == point and line.split()[2].startswith("fuse") for line in mounts):
                parser.error(f"{method}: real FUSE mount required at {point}")
    client.head_bucket(Bucket=BUCKETS[0])
    payload, small = os.urandom(args.size), os.urandom(BLOCK)
    rng = random.Random(8)
    offsets = [(rng.randrange(args.count), rng.randrange(args.size // BLOCK) * BLOCK)
               for _ in range(args.random_count)]
    prefix = "lab8-bench/" + uuid.uuid4().hex
    versions = {name: importlib.metadata.version(name) for name in ("boto3", "matplotlib")}
    document = {"started_utc": datetime.now(timezone.utc).isoformat(), "prefix": prefix,
                "environment": {"platform": platform.platform(), "python": platform.python_version(),
                                "cpu_count": os.cpu_count(), "packages": versions,
                                "endpoint": args.endpoint, "bucket": BUCKETS[0],
                                "mounts": [line for line in mounts if line.split()[1] in
                                           (str(args.s3fs.resolve()), str(args.goofys.resolve()))]},
                "parameters": {"count": args.count, "size_bytes": args.size,
                               "small_count": args.small_count, "small_size_bytes": BLOCK,
                               "random_count": args.random_count, "random_block_bytes": BLOCK,
                               "random_seed": 8, "methods_order": args.methods},
                "conditions": "Single client, sequential ops. close/HTTP response included. "
                              "No fsync durability equivalence; caches NOT cleared; reads follow writes. "
                              "Random FUSE seek/read vs S3 Range GET. Validation included in latency. "
                              "Percentiles: nearest rank, successes only; elapsed includes failures.",
                "results": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for method in args.methods:
        storage = Storage(client, prefix + "/" + method,
                          None if method == "boto3" else getattr(args, method))
        workloads = [
            ("sequential_write", args.count, lambda i: storage.write(f"seq-{i}", payload)),
            ("sequential_read", args.count, lambda i: storage.read(f"seq-{i}", payload)),
            ("random_read_4K", args.random_count,
             lambda i: storage.read(f"seq-{offsets[i][0]}",
                                    payload[offsets[i][1]:offsets[i][1] + BLOCK], offsets[i][1])),
            ("small_files_4K", args.small_count, lambda i: storage.write(f"small-{i}", small))]
        for name, count, operation in workloads:
            row = measure(method, name, count, operation)
            document["results"].append(row)
            args.output.write_text(json.dumps(document, indent=2), encoding="utf-8")
            print(f"{method:6} {name:18} {row['throughput_MB_s']:9.3f} MB/s "
                  f"{row['iops']:9.2f} IOPS errors={row['errors']}", flush=True)
    plot(document, args.output.with_suffix(".png"))
    print(f"Raw data: {args.output}; prefix: {prefix}")
    if any(row["errors"] for row in document["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
