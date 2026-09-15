# SQL preview — filter binding and DuckDB lockdown

`POST /api/sql/test` previews a transform SQL on sample rows. Two problems:

1. **JOIN filter values were pasted into SQL.** For a JOIN, the preview reads 5 rows of the first
   table, then loads the second table with `WHERE col IN ('v1', 'v2', ...)`, built by string
   formatting. A name like `O'Brien` broke the query. A value shaped like SQL changed it — in the
   test below it commented out `LIMIT`, and the preview loaded the whole table.
   Now the values are bound as parameters (psycopg2 / pymysql `IN %s`, DuckDB `IN (?, ...)`).
2. **User SQL ran in DuckDB with full access.** It could read files and environment variables of
   the API container, write files, attach databases and load extensions. The preview only needs
   the sample tables registered from pandas, so the connection now sets
   `enable_external_access = false` and `lock_configuration = true` before running user SQL.

## Setup

Same `xflow-perf` network, MongoDB and LocalStack as `../quality-check-nonblocking`, plus
PostgreSQL 16 and MySQL 8.0. `seed.py` puts the same three tables in all three sources:

- `customers_q` — 5 names, one of them `O'Brien`
- `customers_x` — 5 names, one of them `') OR 1=1 -- `
- `orders` — 1,000,000 rows

`app.py` mounts the real `routers/sql_test.py` under `/api/sql` and wraps `_load_sample_data` to
record how many rows each source loaded. Before/after run as two containers, the "before" one with
the previous `sql_test.py` mounted over it.

```bash
docker build -t xflow-sqlprev -f Dockerfile ../../../backend
docker run -d --name xflow-perf-pg --network xflow-perf -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=shop postgres:16
docker run -d --name xflow-perf-mysql --network xflow-perf -e MYSQL_ROOT_PASSWORD=pw -e MYSQL_DATABASE=shop mysql:8.0
docker run --rm --network xflow-perf -v "$PWD":/perf xflow-sqlprev python /perf/seed.py
docker run -d --name xflow-sqlprev-after --network xflow-perf -e MONGODB_URL=mongodb://xflow-perf-mongo:27017 \
  -e MONGODB_DATABASE=xflow_sqlprev -e PYTHONPATH=/app:/perf -v "$PWD/../../../backend":/app -v "$PWD":/perf -w /app \
  xflow-sqlprev uvicorn app:app --app-dir /perf --host 0.0.0.0 --port 8000
# xflow-sqlprev-before: same, plus -v <previous sql_test.py>:/app/routers/sql_test.py:ro
docker run --rm --network xflow-perf -v "$PWD":/perf xflow-sqlprev python /perf/measure.py
```

## Results (local)

JOIN preview where a customer is named `O'Brien`:

| source | before | after |
|---|---|---|
| PostgreSQL | fails (syntax error) | 5 rows |
| MySQL | fails (syntax error) | 5 rows |
| S3 parquet | fails (HTTP 500) | 5 rows |

JOIN preview where a customer is named `') OR 1=1 -- ` (median of 3):

| source | orders rows loaded | orders load | whole request |
|---|---|---|---|
| PostgreSQL | 1,000,000 → 5 | 256 ms → 2 ms | 623 ms → 12 ms |
| MySQL | 1,000,000 → 5 | 2,003 ms → 5 ms | 2,367 ms → 18 ms |
| S3 parquet | 5 → 5 | 94 ms → 41 ms | 134 ms → 76 ms |

On S3 the query also lost its `LIMIT`, but a pandas filter after the read cut the rows back to 5,
so only the read time shows it.

User SQL against the API container:

| | before | after |
|---|---|---|
| `read_text('/etc/passwd')`, `read_text('/proc/self/environ')`, `glob('/app/*')`, `COPY ... TO`, `ATTACH`, `LOAD httpfs` | 6 / 6 run | 0 / 6 run |
| select, filter + order, `input` table, CTE, window function, backtick identifiers, group by | 7 / 7 | 7 / 7 |

A JOIN on a numeric column (`c.id = o.order_id`) returns the same 5 rows before and after on all
three sources.

`SET enable_external_access = true` inside user SQL is refused by DuckDB even before the change
(it cannot be turned on while the database is running), so it is not counted above.
