# Quality check — S3 size lookup benchmark

Before choosing between a full scan and TABLESAMPLE, the check needs the total size of the
dataset. It listed the files with `list_objects_v2`, dropped the sizes that listing already
returns, then called `head_object` once per file to get them back — 1,000 files meant 1,000 extra
S3 requests on every check.

The loop was also wrapped in `except Exception: pass`. If any `head_object` failed, the partial
total was used as is, so a large dataset could be treated as small and fully scanned.

The fix keeps `Size` from the listing (one `head_object` only when the path is a single file) and
lets S3 errors fail the check.

## Setup

Same containers as `../quality-check-nonblocking` (MongoDB, LocalStack 3.8, `xflow-perf-app` image).

- `prepare.py` uploads 1,000 parquet files (35 KB, 2,000 rows each — a partitioned table) and
  creates the `Dataset`. Total 35 MB, under the 100 MB threshold, so the check does a full scan
- `size_step.py` times only the listing + size step (median of 5) and counts boto3 S3 calls
- `run_check.py` runs `QualityService.run_quality_check` 4 times, drops the first, and reports
  `duration_ms` and boto3 S3 calls per check (DuckDB reads S3 on its own and is not counted)

```bash
B="$PWD/../../../backend"
docker run --rm --network xflow-perf -e PYTHONPATH=/app -v "$B":/app -v "$PWD":/perf -w /app xflow-perf-app python /perf/prepare.py
docker run --rm --network xflow-perf -e PYTHONPATH=/app -v "$B":/app -v "$PWD":/perf -w /app xflow-perf-app python /perf/size_step.py after
docker run --rm --network xflow-perf -e PYTHONPATH=/app -v "$B":/app -v "$PWD":/perf -w /app xflow-perf-app python /perf/run_check.py after
```

For "before", mount the previous `services/quality_service.py` over `/app/services/quality_service.py`.

## Results (local LocalStack, 1,000 files)

| | before | after |
|---|---|---|
| boto3 S3 calls per check | 1,001 (1 list + 1,000 head) | 1 (list) |
| listing + size step | 826 ms | 51 ms |
| whole check, median of 3 (2 rounds) | 6,369 / 6,397 ms | 5,594 / 5,565 ms |

Both versions report the same total size (35,358,000 bytes) and row count (2,000,000). Scores
match to five decimals; the last digits move between runs because freshness is measured against
the current time.

LocalStack runs on the same machine, so each request here costs well under a millisecond of
network time. Against real S3 the per-file requests cost more, but that was not measured.
