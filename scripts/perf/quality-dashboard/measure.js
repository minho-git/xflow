// 코드가 실제로 날리는 쿼리 세 개를 explain 과 반복 실행 시간으로 잰다
const PIPELINE = typeof DASH_PIPELINE !== "undefined" ? DASH_PIPELINE : [
  { $sort: { run_at: -1 } },
  { $group: { _id: "$dataset_id", latest: { $first: "$$ROOT" } } },
  { $replaceRoot: { newRoot: "$latest" } }
];
const dsIds = db.quality_results.distinct("dataset_id");
const pick = i => dsIds[(i * 7919) % dsIds.length];
const pct = (arr, p) => { const s = [...arr].sort((a, b) => a - b); return +s[Math.min(s.length - 1, Math.floor(p / 100 * s.length))].toFixed(2); };
const stages = plan => { const out = []; const walk = n => { if (!n) return; out.push(n.stage + (n.indexName ? `(${n.indexName})` : "")); walk(n.inputStage); (n.inputStages || []).forEach(walk); }; walk(plan); return out.join(" ← "); };

function explainFind(limit) {
  const e = db.quality_results.find({ dataset_id: pick(1) }).sort({ run_at: -1 }).limit(limit).explain("executionStats");
  return { plan: stages(e.executionStats.executionStages), keys: e.executionStats.totalKeysExamined, docs: e.executionStats.totalDocsExamined, ms: e.executionStats.executionTimeMillis };
}
function timeFind(limit, n = 300) {
  for (let i = 0; i < 30; i++) db.quality_results.find({ dataset_id: pick(i) }).sort({ run_at: -1 }).limit(limit).toArray(); // 워밍업
  const t = [];
  for (let i = 0; i < n; i++) { const s = performance.now(); db.quality_results.find({ dataset_id: pick(i) }).sort({ run_at: -1 }).limit(limit).toArray(); t.push(performance.now() - s); }
  return { p50: pct(t, 50), p95: pct(t, 95) };
}
function explainAgg() {
  const e = db.quality_results.explain("executionStats").aggregate(PIPELINE);
  const first = e.stages ? e.stages[0].$cursor : e;
  const es = first.executionStats || (e.executionStats);
  const winning = (first.queryPlanner || e.queryPlanner).winningPlan;
  return { plan: stages(winning.queryPlan || winning), keys: es.totalKeysExamined, docs: es.totalDocsExamined, usedDisk: JSON.stringify(e).includes('"usedDisk":true') };
}
function timeAgg(n = 5) {
  db.quality_results.aggregate(PIPELINE, { allowDiskUse: true }).toArray();
  const t = [];
  for (let i = 0; i < n; i++) { const s = performance.now(); const r = db.quality_results.aggregate(PIPELINE, { allowDiskUse: true }).toArray(); t.push(performance.now() - s); if (r.length !== dsIds.length) throw new Error("결과 수 이상: " + r.length); }
  return { p50: pct(t, 50), max: pct(t, 100), groups: dsIds.length };
}
printjson({
  label: typeof LABEL !== "undefined" ? LABEL : "",
  latest:  { explain: explainFind(1),  time: timeFind(1) },
  history: { explain: explainFind(10), time: timeFind(10) },
  dashboard: { explain: explainAgg(), time: timeAgg() }
});
