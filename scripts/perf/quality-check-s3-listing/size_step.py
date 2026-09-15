"""검사 대상 크기를 알아내는 단계의 S3 호출 수와 시간 — 서비스 코드를 직접 부른다"""
import time, statistics, json, sys
from collections import Counter
from services.quality_service import QualityService

svc = QualityService()
calls = Counter()
svc.s3_client.meta.events.register("before-call.s3.*", lambda event_name, **kw: calls.update([event_name.split(".")[-1]]))

def step():
    if hasattr(svc, "_list_parquet_objects"):                 # 고친 뒤
        objs = svc._list_parquet_objects("xflow-lake", "perf1k/")
        return len(objs), sum(o["size"] for o in objs)
    keys = svc._list_parquet_files("xflow-lake", "perf1k/")    # 고치기 전
    return len(keys), svc._calculate_total_size("xflow-lake", keys)

step()                                   # 워밍업
calls.clear(); files, size = step(); per_run = dict(calls)
ts = []
for _ in range(5):
    s = time.perf_counter(); step(); ts.append((time.perf_counter() - s) * 1000)
print(json.dumps({"label": sys.argv[1], "files": files, "total_bytes": size, "s3_calls": per_run,
                  "median_ms": round(statistics.median(ts), 1)}, ensure_ascii=False))
