"""XFlow 품질 라우터를 그대로 올린 최소 앱 — main.py 와 같은 limiter · prefix"""
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from utils.limiter import limiter
from routers import quality
from models import Dataset, QualityResult

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(quality.router, prefix="/api/quality", tags=["quality"])

@app.on_event("startup")
async def startup():
    db = AsyncIOMotorClient("mongodb://xflow-perf-mongo:27017")["xflow"]
    await init_beanie(database=db, document_models=[Dataset, QualityResult])
