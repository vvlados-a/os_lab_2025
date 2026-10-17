# Готовые официальные образы MinIO недоступны: собираем точный исходный релиз.
FROM golang:1.24.6-bookworm AS minio-build
ENV CGO_ENABLED=0 GOBIN=/out GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org
RUN go install github.com/minio/minio@RELEASE.2025-09-07T16-13-09Z

FROM debian:bookworm-slim AS minio
COPY --from=minio-build /out/minio /usr/local/bin/minio
ENTRYPOINT ["/usr/local/bin/minio"]

FROM python:3.12.12-slim-bookworm AS tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl fuse libfuse2 s3fs && rm -rf /var/lib/apt/lists/*
# Официальный релиз goofys 0.24.0 содержит Linux amd64 binary.
RUN test "$(uname -m)" = x86_64 && \
    curl -fL --retry 3 https://github.com/kahing/goofys/releases/download/v0.24.0/goofys \
      -o /usr/local/bin/goofys && chmod 755 /usr/local/bin/goofys
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py entrypoint.sh ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["sleep", "infinity"]
