"""파일 1,000개로 쪼개진 데이터셋 — 파티션 저장된 테이블 모양"""
import asyncio, os, duckdb, boto3
from concurrent.futures import ThreadPoolExecutor
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import Dataset, QualityResult

s3 = boto3.client("s3", endpoint_url="http://localstack-main:4566", aws_access_key_id="test",
                  aws_secret_access_key="test", region_name="ap-northeast-2")
con = duckdb.connect()
con.execute("COPY (SELECT i AS id, random() AS v, 'cat_' || (i % 7) AS c, TIMESTAMP '2026-01-01' + INTERVAL (i) MINUTE AS created_at FROM range(2000) t(i)) TO '/tmp/small.parquet' (FORMAT parquet)")
def up(i): s3.upload_file("/tmp/small.parquet", "xflow-lake", f"perf1k/part-{i:04d}.parquet")
with ThreadPoolExecutor(16) as ex: list(ex.map(up, range(1000)))
print("S3 업로드: 파일 1,000개 ·", os.path.getsize("/tmp/small.parquet"), "bytes 씩")

async def main():
    db = AsyncIOMotorClient("mongodb://xflow-perf-mongo:27017")["xflow"]
    await init_beanie(database=db, document_models=[Dataset, QualityResult])
    await Dataset.find(Dataset.name == "perf1k").delete()
    ds = Dataset(name="perf1k"); await ds.insert()
    open("/perf/dataset_id.txt", "w").write(str(ds.id)); print("Dataset id:", ds.id)
asyncio.run(main())
