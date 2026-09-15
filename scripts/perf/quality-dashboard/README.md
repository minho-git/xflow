# Quality dashboard — index benchmark

`GET /api/quality/dashboard/summary` returns the latest quality result for every dataset.
It sorted **all** result documents by `run_at` and grouped them, so it read every document
on every call. This folder reproduces the before/after measurement.

## Data

`seed.js` inserts `QualityResult` documents with the same shape as `models.py`:
1,000 datasets × N runs, interleaved by time (the order they accumulate in production).

## Run

```bash
docker run -d --name xflow-perf-mongo -p 27018:27017 mongo:7

# 100 runs = 100k docs (default) · 300 runs = 300k docs
docker exec -i xflow-perf-mongo mongosh --quiet xflow --eval 'const RUNS_ENV=300' --file /dev/stdin < seed.js

# before — original single-field indexes, original pipeline
docker exec -i xflow-perf-mongo mongosh --quiet xflow --file /dev/stdin < measure.js

# after — compound index + pipeline sorted in index order
docker exec xflow-perf-mongo mongosh --quiet xflow --eval 'db.quality_results.createIndex({dataset_id:1, run_at:-1})'
docker exec -i xflow-perf-mongo mongosh --quiet xflow \
  --eval 'const DASH_PIPELINE=[{$sort:{dataset_id:1, run_at:-1}},{$group:{_id:"$dataset_id", latest:{$first:"$$ROOT"}}},{$replaceRoot:{newRoot:"$latest"}}]' \
  --file /dev/stdin < measure.js

# with the real Beanie models and service (Python 3.11, same versions as requirements)
docker run --rm -e PYTHONPATH=/app -v "$PWD/../../../backend":/app -v "$PWD":/perf -w /app python:3.11-slim \
  sh -c "pip install -q beanie==1.26.0 motor==3.6.0 boto3 duckdb==1.1.3 && python /perf/verify.py"
```

## Results (local, MongoDB 7, avg doc 3 KB)

Dashboard aggregation

| result docs | before | after | docs examined |
|---:|---:|---:|---|
| 100k | 71 ms | 20 ms | 100,000 → 1,000 |
| 300k | 228 ms | 24 ms | 300,000 → 1,000 |

- Plan: `FETCH ← IXSCAN(run_at_1)` → `FETCH ← DISTINCT_SCAN(dataset_id_run_at_desc)`
- Through Beanie (Python, `verify.py`, 300k): median 186 ms → 14 ms
- Both pipelines return the same 1,000 documents
- After stays roughly flat as results accumulate — it depends on the number of datasets, not runs

Latest / history (300k)

| query | before | after |
|---|---|---|
| latest result | 81 docs · 0.70 ms | 1 doc · 0.22 ms |
| history (10) | 300 docs + in-memory SORT · 0.66 ms | 10 docs, no SORT · 0.31 ms |

Adding the compound index **alone** did not change the dashboard plan. The `$sort` key had to
match the index order for MongoDB to use `DISTINCT_SCAN`.

A dataset whose checks stopped early was also tested (latest result far behind the newest
entries). The planner picked the `dataset_id` index and examined 10 docs — not a problem.

Existing deployments keep the old `dataset_id_1` / `run_at_1` indexes; Beanie does not drop them.

## Response payload

The dashboard rendered five fields per result, but the aggregation returned whole documents
(20-column `checks` arrays and `null_counts`). A `$project` stage now returns only
`dataset_id, s3_path, overall_score, status, run_at`.

`verify_project.py` runs the real service with and without the `$project` stage (1,000 datasets):

| | without `$project` | with `$project` |
|---|---:|---:|
| JSON response | 3,175 KB | 223 KB |
| service + JSON encode (median) | 32.8 ms | 3.9 ms |

The plan stays `FETCH ← DISTINCT_SCAN`, and the `summary` block is identical.
`job_name` / `domain_id` read by the page are not fields of `QualityResult`, so nothing the page
receives changes.
