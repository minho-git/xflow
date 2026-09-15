"""POST /api/sql/test 를 수정 전·후 앱에 같은 요청으로 보낸다."""
import json, statistics, time, httpx

IDS = json.load(open("/perf/ids.json"))
APPS = {"before": "http://xflow-sqlprev-before:8000", "after": "http://xflow-sqlprev-after:8000"}
KINDS = ["postgres", "mysql", "s3"]
client = httpx.Client(timeout=300)

def call(app, kind, tables, sql):
    body = {"sql": sql, "limit": 5, "sources": [
        {"source_dataset_id": IDS[f"{kind}.{t}"], "columns": cols} for t, cols in tables]}
    client.get(f"{APPS[app]}/debug/loaded")
    s = time.perf_counter()
    r = client.post(f"{APPS[app]}/api/sql/test", json=body)
    ms = round((time.perf_counter() - s) * 1000)
    loaded = client.get(f"{APPS[app]}/debug/loaded").json()
    data = r.json()
    ok = r.status_code == 200 and data.get("valid") is True
    err = None if ok else (data.get("error") or data.get("detail") or "")[:90]
    return {"http": r.status_code, "valid": ok, "rows": len(data.get("sample_rows") or []), "ms": ms, "loaded": loaded, "err": err}

CUST, ORD = ["id", "name"], ["order_id", "customer_name"]

print("== 1. JOIN 미리보기, 고객 이름에 O'Brien 이 있다")
for kind in KINDS:
    for app in APPS:
        r = call(app, kind, [("customers_q", CUST), ("orders", ORD)],
                 "SELECT c.name, o.order_id FROM customers_q c JOIN orders o ON c.name = o.customer_name")
        print(f"{kind:8} {app:6} valid={r['valid']!s:5} rows={r['rows']:2} http={r['http']} err={r['err']}")

print("\n== 2. JOIN 미리보기, 고객 이름에 SQL 조각 같은 값이 있다 (3회)")
for kind in KINDS:
    for app in APPS:
        runs = [call(app, kind, [("customers_x", CUST), ("orders", ORD)],
                     "SELECT c.name, o.order_id FROM customers_x c JOIN orders o ON c.name = o.customer_name") for _ in range(3)]
        orders = [next(l for l in r["loaded"] if l["source"] == "orders") for r in runs]
        print(f"{kind:8} {app:6} valid={runs[0]['valid']!s:5} rows={runs[0]['rows']:2} orders_loaded={orders[0]['rows']:>7} "
              f"orders_load_ms={statistics.median(o['ms'] for o in orders):>7} request_ms={statistics.median(r['ms'] for r in runs):>6} err={runs[0]['err']}")

ATTACKS = {
    "서버 파일 읽기": "SELECT * FROM read_text('/etc/passwd')",
    "환경변수 읽기": "SELECT * FROM read_text('/proc/self/environ')",
    "디렉터리 목록": "SELECT * FROM glob('/app/*')",
    "파일 쓰기": "COPY (SELECT * FROM customers_q LIMIT 1) TO '/tmp/leak.csv'",
    "DB 파일 붙이기": "ATTACH '/tmp/other.duckdb' AS other; SELECT * FROM customers_q LIMIT 1",
    "확장 불러오기": "LOAD httpfs; SELECT * FROM customers_q LIMIT 1",
}
NORMAL = {
    "전체 조회": "SELECT * FROM customers_q",
    "필터·정렬": "SELECT name, length(name) AS len FROM customers_q WHERE id > 1 ORDER BY id",
    "input 테이블": "SELECT count(*) AS cnt FROM input",
    "CTE": "WITH t AS (SELECT * FROM customers_q) SELECT upper(name) AS u FROM t",
    "윈도우 함수": "SELECT name, row_number() OVER (ORDER BY id) AS rn FROM customers_q",
    "Spark 백틱 변환": "SELECT `id`, `name` FROM customers_q",
    "집계": "SELECT substr(name, 1, 1) AS initial, count(*) AS n FROM customers_q GROUP BY 1 ORDER BY 1",
}
for title, cases in (("3. 사용자 SQL — 서버 자원에 닿는 쿼리", ATTACKS), ("4. 사용자 SQL — 평소 쓰는 쿼리", NORMAL)):
    print(f"\n== {title}")
    total = {a: 0 for a in APPS}
    for name, sql in cases.items():
        res = {app: call(app, "postgres", [("customers_q", CUST)], sql) for app in APPS}
        for app in APPS: total[app] += res[app]["valid"]
        print(f"{name:12} before={'통과' if res['before']['valid'] else '막힘'}({res['before']['rows']}) "
              f"after={'통과' if res['after']['valid'] else '막힘'}({res['after']['rows']})  after_err={res['after']['err']}")
    print("통과 수:", {a: f"{v}/{len(cases)}" for a, v in total.items()})

print("\n== 5. 평범한 JOIN — 숫자 컬럼, 따옴표 없는 값 (결과가 같아야 한다)")
for kind in KINDS:
    res = {app: call(app, kind, [("customers_q", CUST), ("orders", ORD)],
                     "SELECT c.id, o.order_id, o.customer_name FROM customers_q c JOIN orders o ON c.id = o.order_id") for app in APPS}
    print(f"{kind:8} before valid={res['before']['valid']} rows={res['before']['rows']}  after valid={res['after']['valid']} rows={res['after']['rows']}")
