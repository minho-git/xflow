"""SQL 미리보기 라우터를 main.py 와 같은 prefix 로 올린 최소 앱.
소스마다 몇 행을 읽었는지 보려고 _load_sample_data 를 감싼다 (라우터 코드는 그대로)."""
import os, time
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
import database
from routers import sql_test

loaded = []
_original = sql_test._load_sample_data

async def _counting(source_dataset, connection, **kwargs):
    start = time.perf_counter()
    df = await _original(source_dataset, connection, **kwargs)
    loaded.append({"source": source_dataset.get("name"), "rows": 0 if df is None else len(df),
                   "ms": round((time.perf_counter() - start) * 1000, 1)})
    return df

sql_test._load_sample_data = _counting

app = FastAPI()
app.include_router(sql_test.router, prefix="/api/sql")

@app.get("/debug/loaded")
def pop_loaded():
    out = list(loaded); loaded.clear(); return out

@app.on_event("startup")
async def startup():
    database.mongodb_client = AsyncIOMotorClient(os.environ["MONGODB_URL"])
