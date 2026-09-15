"""바꾼 XFlow 코드 그대로 — Beanie 인덱스 생성 · 대시보드 서비스 실행 · 실행 계획"""
import asyncio, time, statistics
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import models
from models import QualityResult
from services.quality_service import quality_service

OLD = [{"$sort": {"run_at": -1}},
       {"$group": {"_id": "$dataset_id", "latest": {"$first": "$$ROOT"}}},
       {"$replaceRoot": {"newRoot": "$latest"}}]

async def main():
    client = AsyncIOMotorClient("mongodb://host.docker.internal:27018")
    db = client["xflow"]
    await init_beanie(database=db, document_models=[QualityResult])
    idx = await db.quality_results.index_information()
    print("인덱스:", {k: v["key"] for k, v in idx.items()})

    # 서비스가 실제로 넘기는 파이프라인을 가로챈다
    captured = {}
    orig = QualityResult.aggregate
    def spy(pipeline, *a, **kw):
        captured["pipeline"] = pipeline
        return orig(pipeline, *a, **kw)
    QualityResult.aggregate = spy
    await quality_service.get_dashboard_summary()
    QualityResult.aggregate = orig
    print("서비스 파이프라인 $sort:", captured["pipeline"][0])

    async def plan(pipeline):
        e = await db.command("explain", {"aggregate": "quality_results", "pipeline": pipeline, "cursor": {}}, verbosity="executionStats")
        cur = e["stages"][0]["$cursor"]
        stages, n = [], cur["queryPlanner"]["winningPlan"]
        n = n.get("queryPlan", n)
        while n:
            stages.append(n["stage"] + (f"({n['indexName']})" if "indexName" in n else ""))
            n = n.get("inputStage")
        return " ← ".join(stages), cur["executionStats"]["totalDocsExamined"]

    print("원래 쿼리 실행 계획:", await plan(OLD))
    print("바꾼 쿼리 실행 계획:", await plan(captured["pipeline"]))

    # 파이썬(Beanie)까지 포함한 시간 — 문서를 파이썬 객체로 받는 데까지
    async def timed(fn, n=7):
        await fn()
        ts = []
        for _ in range(n):
            s = time.perf_counter(); await fn(); ts.append((time.perf_counter() - s) * 1000)
        return round(statistics.median(ts), 1)
    old_ms = await timed(lambda: QualityResult.aggregate(OLD, allowDiskUse=True).to_list())
    new_ms = await timed(lambda: quality_service.get_dashboard_summary())
    print(f"파이썬 포함 중앙값 — 원래 쿼리 {old_ms}ms · 바꾼 서비스 {new_ms}ms")

asyncio.run(main())
