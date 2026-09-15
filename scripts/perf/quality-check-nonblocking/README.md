# Quality check — event loop blocking benchmark

`POST /api/quality/{dataset_id}/run` is an `async` handler, but the service called DuckDB and
boto3 synchronously inside it. While a check scanned S3, the event loop could not serve anything
else — every other request on the server waited until the scan finished.

The fix moves the blocking work (S3 listing, size lookup, DuckDB scan) to worker threads with
`asyncio.to_thread`. Scoring logic is unchanged.

## Setup

- `app.py` mounts the real `routers/quality.py` with the same prefix and rate limiter as `main.py`
- MongoDB 7 with 300k `QualityResult` docs (see `../quality-dashboard/seed.js`)
- LocalStack 3.8 S3 (community image; the compose file uses `localstack-pro`)
- `prepare.py` uploads 6 parquet files (226 MB, 1.98M rows, 20 columns) and creates the `Dataset`
  — over 100 MB, so the check takes the TABLESAMPLE path
- `load.py` fires `GET /api/quality/{id}/latest` every 50 ms on a fixed schedule (does not wait for
  the previous response), starts one quality check after 3 s, and keeps probing 3 s after it returns

```bash
docker network create xflow-perf
docker network connect xflow-perf xflow-perf-mongo
docker run -d --name localstack-main --network xflow-perf -e SERVICES=s3 localstack/localstack:3.8
docker build -t xflow-perf-app .
docker run --rm --network xflow-perf -e PYTHONPATH=/app -v "$PWD/../../../backend":/app -v "$PWD":/perf -w /app xflow-perf-app python /perf/prepare.py
docker run -d --name xflow-perf-app --network xflow-perf -e PYTHONPATH=/app:/perf \
  -v "$PWD/../../../backend":/app -v "$PWD":/perf -w /app xflow-perf-app uvicorn app:app --app-dir /perf --host 0.0.0.0 --port 8000
docker run --rm --network xflow-perf -v "$PWD":/perf xflow-perf-app python /perf/load.py
```

## Results (local, 3 runs each)

Latency of `/latest` requests that started while one check (~0.95 s) was running:

| | before | after |
|---|---|---|
| p50 | 460 – 479 ms | 1.7 ms |
| p95 | 865 – 882 ms | 3.4 – 8.0 ms |
| baseline p95 (no check) | 6 – 8 ms | 7 – 8 ms |
| check duration | 0.92 – 0.95 s | 0.92 – 0.99 s |

Scores match (96.86); one after-run shows 96.65 because TABLESAMPLE picks a random sample.
