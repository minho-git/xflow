"""품질 검사 1건을 돌리는 동안 다른 API(최신 결과 조회)가 얼마나 기다리는지 잰다.

조회는 50ms 마다 정해진 시각에 쏜다 — 앞 요청이 안 끝나도 다음 요청을 보낸다.
서버가 멈추면 그 사이 요청들이 전부 늦게 끝나는 게 그대로 보인다."""
import asyncio, json, time, statistics, sys, httpx

BASE = "http://xflow-perf-app:8000/api/quality"
PROBE_DS = "000000000000006700000000"          # 결과 문서가 있는 데이터셋
TARGET_DS = open("/perf/dataset_id.txt").read().strip()
INTERVAL, BASELINE, TAIL = 0.05, 3.0, 3.0

def pct(xs, p):
    s = sorted(xs); return round(s[min(len(s) - 1, int(p / 100 * len(s)))], 1) if s else None

async def main():
    probes, t0 = [], time.perf_counter()
    async with httpx.AsyncClient(timeout=120) as client:
        async def probe():
            s = time.perf_counter()
            r = await client.get(f"{BASE}/{PROBE_DS}/latest")
            probes.append((s - t0, (time.perf_counter() - s) * 1000, r.status_code))
        tasks, stop = [], asyncio.Event()
        async def ticker():
            while not stop.is_set():
                tasks.append(asyncio.create_task(probe())); await asyncio.sleep(INTERVAL)
        tick = asyncio.create_task(ticker())
        await asyncio.sleep(BASELINE)
        run_start = time.perf_counter() - t0
        r = await client.post(f"{BASE}/{TARGET_DS}/run", json={"s3_path": "s3a://xflow-lake/perfds/"})
        run_end = time.perf_counter() - t0
        await asyncio.sleep(TAIL)
        stop.set(); await tick; await asyncio.gather(*tasks)
    base = [l for s, l, _ in probes if s < run_start]
    during = [l for s, l, _ in probes if run_start <= s <= run_end]
    body = r.json()
    print(json.dumps({
        "label": sys.argv[1] if len(sys.argv) > 1 else "",
        "check": {"status": r.status_code, "result": body.get("status"), "rows": body.get("row_count"),
                  "score": body.get("overall_score"), "seconds": round(run_end - run_start, 2)},
        "baseline": {"n": len(base), "p50": pct(base, 50), "p95": pct(base, 95)},
        "during_check": {"n": len(during), "p50": pct(during, 50), "p95": pct(during, 95), "max": pct(during, 100)},
        "non_200": sum(1 for *_, c in probes if c != 200)
    }, ensure_ascii=False, indent=1))
asyncio.run(main())
