"""SQL 미리보기 측정 데이터 — Postgres · MySQL · S3(parquet) 에 같은 테이블 세 개를 넣고 Mongo 에 소스로 등록한다.

customers_q  이름 5개 중 하나가 O'Brien (따옴표가 들어간 흔한 값)
customers_x  이름 5개 중 하나가 SQL 조각처럼 생긴 값
orders       주문 100만 건, customer_name 은 이름 6개를 돌아가며
"""
import json, os, time, duckdb, boto3, psycopg2, pymysql
from pymongo import MongoClient

N = 1_000_000
Q = ["Kim", "O'Brien", "Lee", "Park", "Choi"]
X = ["Kim", "Lee", "') OR 1=1 -- ", "Park", "Choi"]
ORDER_NAMES = ["Kim", "O'Brien", "Lee", "Park", "Choi", "Jung"]

def wait(fn):
    for _ in range(90):
        try: return fn()
        except Exception: time.sleep(2)
    raise SystemExit("db not ready")

# --- PostgreSQL
pg = wait(lambda: psycopg2.connect("host=xflow-perf-pg dbname=shop user=postgres password=pw"))
with pg, pg.cursor() as c:
    c.execute("DROP TABLE IF EXISTS customers_q, customers_x, orders")
    for t, names in (("customers_q", Q), ("customers_x", X)):
        c.execute(f"CREATE TABLE {t} (id int, name text)")
        c.executemany(f"INSERT INTO {t} VALUES (%s, %s)", list(enumerate(names, 1)))
    c.execute("CREATE TABLE orders (order_id int, customer_name text)")
    c.execute("INSERT INTO orders SELECT g, (%s::text[])[g %% 6 + 1] FROM generate_series(1, %s) g", (ORDER_NAMES, N))
print("postgres ok")

# --- MySQL
my = wait(lambda: pymysql.connect(host="xflow-perf-mysql", user="root", password="pw", database="shop", autocommit=True))
with my.cursor() as c:
    c.execute("DROP TABLE IF EXISTS customers_q, customers_x, orders")
    for t, names in (("customers_q", Q), ("customers_x", X)):
        c.execute(f"CREATE TABLE {t} (id int, name varchar(64))")
        c.executemany(f"INSERT INTO {t} VALUES (%s, %s)", list(enumerate(names, 1)))
    c.execute("CREATE TABLE orders (order_id int, customer_name varchar(64))")
    c.execute("SET SESSION cte_max_recursion_depth = 2000000")
    c.execute("INSERT INTO orders WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM s WHERE n < %s) "
              "SELECT n, ELT(n %% 6 + 1, %s, %s, %s, %s, %s, %s) FROM s", (N, *ORDER_NAMES))
print("mysql ok")

# --- S3 parquet
s3 = boto3.client("s3", endpoint_url="http://localstack-main:4566", aws_access_key_id="test",
                  aws_secret_access_key="test", region_name="ap-northeast-2")
con = duckdb.connect()
for t, names in (("customers_q", Q), ("customers_x", X)):
    con.execute(f"COPY (SELECT * FROM (VALUES {', '.join('(?, ?)' for _ in names)}) v(id, name)) TO '/tmp/{t}.parquet' (FORMAT parquet)",
                [x for i, n in enumerate(names, 1) for x in (i, n)])
con.execute(f"COPY (SELECT g::INT AS order_id, ?[g % 6 + 1] AS customer_name FROM range(1, {N + 1}) t(g)) TO '/tmp/orders.parquet' (FORMAT parquet)", [ORDER_NAMES])
for t in ("customers_q", "customers_x", "orders"):
    s3.upload_file(f"/tmp/{t}.parquet", "xflow-lake", f"sqlprev/{t}/{t}.parquet")
print("s3 ok")

# --- Mongo: connections + source_datasets
db = MongoClient("mongodb://xflow-perf-mongo:27017")["xflow_sqlprev"]
db.connections.drop(); db.source_datasets.drop()
conns = {
    "postgres": {"type": "postgres", "config": {"host": "xflow-perf-pg", "port": 5432, "database_name": "shop", "user_name": "postgres", "password": "pw"}},
    "mysql": {"type": "mysql", "config": {"host": "xflow-perf-mysql", "port": 3306, "database_name": "shop", "user_name": "root", "password": "pw"}},
    "s3": {"type": "s3", "config": {"endpoint": "http://localstack-main:4566", "access_key": "test", "secret_key": "test", "region": "ap-northeast-2"}},
}
ids = {}
for kind, doc in conns.items():
    cid = str(db.connections.insert_one(doc).inserted_id)
    for t in ("customers_q", "customers_x", "orders"):
        ds = {"name": t, "source_type": kind, "connection_id": cid}
        if kind == "s3":
            ds.update(bucket="xflow-lake", path=f"sqlprev/{t}/", format="parquet")
        else:
            ds["table"] = t
        ids[f"{kind}.{t}"] = str(db.source_datasets.insert_one(ds).inserted_id)
json.dump(ids, open("/perf/ids.json", "w"), indent=1)
print(ids)
