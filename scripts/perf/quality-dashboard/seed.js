// XFlow QualityResult 대량 데이터 — models.py 의 필드 모양 그대로
// 데이터셋 1,000 × 검사 100회. 시간순으로 섞어 넣는다(실제로 쌓이는 순서)
const DATASETS = 1000, RUNS = (typeof RUNS_ENV !== "undefined" ? RUNS_ENV : 100), COLS = 20;
let seed = 42; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const hex = n => n.toString(16).padStart(24, "0");
const dsIds = Array.from({ length: DATASETS }, (_, i) => hex(0x6700000000 + i));
const cols = Array.from({ length: COLS }, (_, i) => `col_${i}`);
db.quality_results.drop();
// 지금 코드의 인덱스 그대로 — Beanie indexes = ["dataset_id", "run_at"]
db.quality_results.createIndex({ dataset_id: 1 });
db.quality_results.createIndex({ run_at: 1 });
const start = new Date("2026-01-01T00:00:00Z").getTime();
let batch = [];
for (let r = 0; r < RUNS; r++) {
  for (let d = 0; d < DATASETS; d++) {
    const runAt = new Date(start + r * 86400000 + d * 1000);
    const nullCounts = {}; const checks = [];
    for (const c of cols) {
      const n = Math.floor(rnd() * 50); nullCounts[c] = n;
      checks.push({ name: "null_check", column: c, passed: n < 40, value: n / 10, threshold: 20.0, message: n ? `${(n/10).toFixed(2)}% nulls` : null });
    }
    checks.push({ name: "duplicate_check", column: null, passed: true, value: rnd() * 5, threshold: 10.0, message: null });
    checks.push({ name: "freshness_check", column: "updated_at", passed: true, value: rnd() * 30, threshold: 500.0, message: null });
    batch.push({
      dataset_id: dsIds[d], s3_path: `s3a://xflow-lake/${dsIds[d]}/`,
      row_count: 10000 + Math.floor(rnd() * 1e6), column_count: COLS, null_counts: nullCounts,
      duplicate_count: Math.floor(rnd() * 100), overall_score: 60 + rnd() * 40, checks,
      status: "completed", error_message: null, run_at: runAt,
      completed_at: new Date(runAt.getTime() + 4000), duration_ms: 3000 + Math.floor(rnd() * 2000)
    });
    if (batch.length === 2000) { db.quality_results.insertMany(batch, { ordered: false }); batch = []; }
  }
}
if (batch.length) db.quality_results.insertMany(batch);
const s = db.quality_results.stats();
printjson({ docs: db.quality_results.countDocuments(), avgDocBytes: s.avgObjSize, dataMB: Math.round(s.size / 1048576), indexes: db.quality_results.getIndexes().map(i => i.key) });
