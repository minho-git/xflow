"""S3 에 parquet 올리기 + 품질 검사 대상 Dataset 문서 만들기"""
import asyncio, os, duckdb, boto3
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import Dataset, QualityResult

s3 = boto3.client("s3", endpoint_url="http://localstack-main:4566", aws_access_key_id="test",
                  aws_secret_access_key="test", region_name="ap-northeast-2")
try:
    s3.create_bucket(Bucket="xflow-lake", CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"})
except s3.exceptions.BucketAlreadyOwnedByYou:
    pass

con = duckdb.connect()
os.makedirs("/tmp/parts", exist_ok=True)
total = 0
for i in range(6):
    path = f"/tmp/parts/part-{i}.parquet"
    con.execute(f"""
      COPY (
        SELECT i AS id,
               TIMESTAMP '2026-01-01' + INTERVAL (i % 100000) MINUTE AS created_at,
               random() * 100000 AS price, (random() * 50)::INT AS quantity,
               'cat_' || (i % 37) AS category,
               {", ".join(f"CASE WHEN random() < 0.05 THEN NULL ELSE random() END AS m{c}" for c in range(15))}
        FROM range({i * 330000}, {(i + 1) * 330000}) t(i)
      ) TO '{path}' (FORMAT parquet)""")
    s3.upload_file(path, "xflow-lake", f"perfds/part-{i}.parquet")
    total += os.path.getsize(path)
print(f"S3 업로드: 파일 6개 · {total / 1048576:.0f}MB")

async def main():
    db = AsyncIOMotorClient("mongodb://xflow-perf-mongo:27017")["xflow"]
    await init_beanie(database=db, document_models=[Dataset, QualityResult])
    await Dataset.find(Dataset.name == "perfds").delete()
    ds = Dataset(name="perfds")
    await ds.insert()
    open("/perf/dataset_id.txt", "w").write(str(ds.id))
    print("Dataset id:", ds.id)
asyncio.run(main())
