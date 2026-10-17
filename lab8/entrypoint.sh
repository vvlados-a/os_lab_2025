#!/bin/sh
set -eu

mkdir -p /mnt/s3fs /mnt/goofys /mnt/warm /data/hot /data/cold
umask 077
printf '%s:%s\n' "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" > /tmp/lab8-s3fs.passwd
attempt=0
until curl -fsS "$S3_ENDPOINT/minio/health/ready" >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then echo 'MinIO not ready' >&2; exit 1; fi
    sleep 1
done
python benchmark.py --init

child=''
cleanup() {
    if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; fi
    for point in /mnt/warm /mnt/goofys /mnt/s3fs; do
        if mountpoint -q "$point"; then fusermount -u "$point" || true; fi
    done
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

s3fs lab8-benchmark /mnt/s3fs -f -o passwd_file=/tmp/lab8-s3fs.passwd \
    -o url="$S3_ENDPOINT" -o use_path_request_style > /tmp/s3fs.log 2>&1 &
s3fs_pid=$!
goofys -f --endpoint "$S3_ENDPOINT" --region us-east-1 \
    lab8-benchmark /mnt/goofys > /tmp/goofys.log 2>&1 &
goofys_pid=$!
s3fs lab8-hybrid /mnt/warm -f -o passwd_file=/tmp/lab8-s3fs.passwd \
    -o url="$S3_ENDPOINT" -o use_path_request_style > /tmp/warm.log 2>&1 &
warm_pid=$!
attempt=0
until mountpoint -q /mnt/s3fs && mountpoint -q /mnt/goofys && mountpoint -q /mnt/warm; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ] || ! kill -0 "$s3fs_pid" "$goofys_pid" "$warm_pid" 2>/dev/null; then
        cat /tmp/s3fs.log /tmp/goofys.log /tmp/warm.log >&2
        exit 1
    fi
    sleep 1
done
echo 'Ready: s3fs, goofys, hybrid WARM are real FUSE mounts'
"$@" &
child=$!
wait "$child"
