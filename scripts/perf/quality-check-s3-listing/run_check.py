"""검사 1건 전체 — 서비스의 run_quality_check 를 그대로 부른다. S3 호출 수는 boto3 이벤트로 센다."""
import asyncio, json, sys, statistics
from collections import Counter
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import Dataset, QualityResult
from services.quality_service import QualityService

async def main():
    db = AsyncIOMotorClient("mongodb://xflow-perf-mongo:27017")["xflow"]
    await init_beanie(database=db, document_models=[Dataset, QualityResult])
    ds = open("/perf/dataset_id.txt").read().strip()
    svc = QualityService(); calls = Counter()
    svc.s3_client.meta.events.register("before-call.s3.*", lambda event_name, **kw: calls.update([event_name.split(".")[-1]]))
    durs = []
    for i in range(4):
        calls.clear()
        r = await svc.run_quality_check(dataset_id=ds, s3_path="s3a://xflow-lake/perf1k/")
        if i: durs.append(r.duration_ms)
        last = (dict(calls), r.status, r.row_count, r.overall_score, r.error_message)
    print(json.dumps({"label": sys.argv[1], "boto3_calls": last[0], "status": last[1], "rows": last[2],
                      "score": last[3], "err": last[4], "durations_ms": durs, "median_ms": statistics.median(durs)}, ensure_ascii=False))
asyncio.run(main())
