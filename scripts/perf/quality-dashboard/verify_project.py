"""대시보드 응답 줄이기 전/후 — 실제 서비스 코드로. 전 = 같은 서비스에서 $project 단계만 뺀 것"""
import asyncio, json, time, statistics
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from models import QualityResult
from services.quality_service import quality_service

async def main():
    db = AsyncIOMotorClient("mongodb://host.docker.internal:27018")["xflow"]
    await init_beanie(database=db, document_models=[QualityResult])

    orig = QualityResult.aggregate
    mode = {"strip_project": False, "pipeline": None}
    def spy(pipeline, *a, **kw):
        if mode["strip_project"]:
            pipeline = [st for st in pipeline if "$project" not in st]
        mode["pipeline"] = pipeline
        return orig(pipeline, *a, **kw)
    QualityResult.aggregate = spy

    async def run(strip):
        mode["strip_project"] = strip
        body = await quality_service.get_dashboard_summary()
        return json.dumps(body, default=str).encode()   # FastAPI 가 내보내는 JSON 에 가깝게

    async def plan():
        e = await db.command("explain", {"aggregate": "quality_results", "pipeline": mode["pipeline"], "cursor": {}}, verbosity="executionStats")
        cur = e["stages"][0]["$cursor"]; n = cur["queryPlanner"]["winningPlan"]; n = n.get("queryPlan", n); out = []
        while n: out.append(n["stage"] + (f"({n['indexName']})" if "indexName" in n else "")); n = n.get("inputStage")
        return " ← ".join(out), cur["executionStats"]["totalDocsExamined"]

    async def timed(strip, n=9):
        await run(strip); ts = []
        for _ in range(n):
            s = time.perf_counter(); await run(strip); ts.append((time.perf_counter() - s) * 1000)
        return round(statistics.median(ts), 1)

    before = await run(True);  before_plan = await plan()
    after = await run(False);  after_plan = await plan()
    same_scores = json.loads(before)["summary"] == json.loads(after)["summary"]
    print("전 계획:", before_plan, "| 후 계획:", after_plan)
    print(f"응답 크기 — 전 {len(before)/1024:.0f}KB · 후 {len(after)/1024:.0f}KB")
    print(f"서비스+JSON 중앙값 — 전 {await timed(True)}ms · 후 {await timed(False)}ms")
    print("summary 값 동일:", same_scores)
    print("후 결과 한 건 키:", sorted(json.loads(after)["results"][0].keys()))

asyncio.run(main())
