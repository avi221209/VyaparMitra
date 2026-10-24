import time
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8000", headers={"X-Role": "planner"}, timeout=10.0)

print("=================================================================")
print("MEASURING 3-MINUTE DEMO PATH LATENCIES")
print("=================================================================")

# Step 1: 0:00 - Screen /data: Load sample data
t0 = time.perf_counter()
r = client.post("/api/data/seed?variant=normal&seed=1&scenario=balanced")
t_seed_normal = time.perf_counter() - t0
print(f"1. POST /api/data/seed (Normal) -> {r.status_code} in {t_seed_normal*1000:.1f}ms")

# Step 2: 0:20 - Screen /data: Load file with errors
t0 = time.perf_counter()
r = client.post("/api/data/seed?variant=defects&seed=1&scenario=balanced")
t_seed_defects = time.perf_counter() - t0
print(f"2. POST /api/data/seed (Defects) -> {r.status_code} in {t_seed_defects*1000:.1f}ms")

# Re-seed clean data before planning
client.post("/api/data/seed?variant=normal&seed=1&scenario=balanced")

# Step 3: 0:50 - Screen /plan: Generate plan (Horizon: 7 days)
t0 = time.perf_counter()
r = client.post("/api/plan", json={"horizon": 7})
t_plan = time.perf_counter() - t0
plan_data = r.json()
print(f"3. POST /api/plan (7-day MILP) -> {r.status_code} ({len(plan_data['lines'])} lines) in {t_plan*1000:.1f}ms")

# Step 4: 1:20 - Screen /plan: Fetch dispatch slip explanation card for first line
first_line_id = plan_data["lines"][0]["id"]
t0 = time.perf_counter()
r = client.get(f"/api/plan/lines/{first_line_id}")
t_card = time.perf_counter() - t0
print(f"4. GET /api/plan/lines/{{id}} (Explanation Card) -> {r.status_code} in {t_card*1000:.1f}ms")

# Step 5: 1:45 - Screen /plan: Fetch unmet demand & counterfactual fixes
t0 = time.perf_counter()
r = client.get(f"/api/plan/{plan_data['run_id']}")
t_unmet = time.perf_counter() - t0
print(f"5. GET /api/plan/{{run_id}} (Plan with Counterfactuals) -> {r.status_code} in {t_unmet*1000:.1f}ms")

# Step 6: 2:10 - Screen /plan: What-If Scenario (W1 stock -20%)
t0 = time.perf_counter()
r = client.post("/api/scenario/override", json={"source_id": "W1", "stock_percent": -20.0})
t_whatif = time.perf_counter() - t0
print(f"6. POST /api/scenario/override (Quick-edit -20% W1) -> {r.status_code} in {t_whatif*1000:.1f}ms")

# Step 7: 2:30 - Screen /plan: Carton stepper rule refusal
t0 = time.perf_counter()
r = client.post(f"/api/plan/lines/{first_line_id}/approve", json={"edited_cartons": 999999})
t_refusal = time.perf_counter() - t0
print(f"7. POST /api/plan/lines/{{id}}/approve (Rule Refusal 409) -> {r.status_code} in {t_refusal*1000:.1f}ms")

# Step 8: 2:45 - Screen /evaluate: Fetch evaluation walk-forward cache
t0 = time.perf_counter()
r = client.get("/api/evaluate")
t_eval = time.perf_counter() - t0
print(f"8. GET /api/evaluate (Cached Benchmark Replay) -> {r.status_code} in {t_eval*1000:.1f}ms")

# Step 9: 2:55 - Screen /audit: Fetch immutable decision log
t0 = time.perf_counter()
r = client.get("/api/audit")
t_audit = time.perf_counter() - t0
print(f"9. GET /api/audit (Decision Log) -> {r.status_code} in {t_audit*1000:.1f}ms")

# Step 10: Backup Demo State Loader
t0 = time.perf_counter()
r = client.post("/api/demo/backup")
t_backup = time.perf_counter() - t0
print(f"10. POST /api/demo/backup (Instant Precomputed Plan) -> {r.status_code} in {t_backup*1000:.1f}ms")

print("=================================================================")
print("ALL DEMO PATH STEPS UNDER 2000ms:")
max_time = max(t_seed_normal, t_seed_defects, t_plan, t_card, t_unmet, t_whatif, t_refusal, t_eval, t_audit, t_backup)
print(f"Slowest step took: {max_time*1000:.1f}ms (Target: < 2000ms)")
print("=================================================================")
