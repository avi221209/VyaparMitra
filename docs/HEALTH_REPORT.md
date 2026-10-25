# VyaparMitra Health & Release Verification Report
**Date:** 2026-10-25 04:49:51 UTC
**Target:** http://127.0.0.1:8000
**Overall Verdict:** **GREEN** (14/15 Passed, 1 Skipped, 0 Failed)

## Automated Fast Pass Checks (Step 2)

| # | Check | Status | Latency | Details |
|---|-------|--------|---------|---------|
| 1 | GET /api/health & /api/status | **PASS** | 10.9ms | /api/health: 200 (8.2ms), /api/status: 200 (10.9ms) |
| 2 | Seed normal + GET master data (<= 500ms) | **PASS** | 6.9ms | Counts: {'locations': 6, 'products': 24, 'lanes': 8, 'batches': 96, 'snapshots': 96, 'settings': 1}; Seed: 2074.3ms; Max GET: 6.9ms |
| 3 | Defect detection recall (>=90%) | **PASS** | 2337.4ms | Detected 20/20 injected defects (100.0% recall) |
| 4 | Forecast run (<=8s) & series (<=300ms) | **PASS** | 762.1ms | Run: 200 (762.1ms); SKU-P01/D1: 200 (8.0ms) |
| 5 | Optimization plan (<=5s) & fetch (<=500ms) | **PASS** | 1153.2ms | POST /api/plan: 1153.2ms, latest: 96.2ms, run: 94.0ms, line: 17.0ms |
| 6 | Plan domain integrity checks | **PASS** | - | All domain invariants hold (batch limit, cost sum, unmet>=0, complete fields) |
| 7 | Optimization determinism (3 runs sha256 match) | **PASS** | - | SHA256: a77542326c6f3c1e... Match: True |
| 8 | Role gating & action audit trail | **PASS** | - | Warehouse 403: True; Planner approve: True; Reject w/o reason 400: True; Reject w/ reason: True; Audit logged: True |
| 9 | Rule-checked edit refusal (HTTP 409 & audit) | **PASS** | - | Status 409: True; Rule named: True; EDIT_REFUSED in audit: True |
| 10 | What-if override: W1 -20% stock | **PASS** | - | Status: 200; Before unmet: 0, After unmet: 0 (Did not decrease: True) |
| 11 | Surplus, Dead-Stock, Evaluate endpoints (<=500ms) | **PASS** | 15.3ms | All <= 500ms: True; Times: {'/api/plan/PLAN-20261024-1792903784800/dead-stock': 15.3, '/api/surplus/listings': 5.5, '/api/evaluate': 9.8, '/api/evaluate/status': 3.5} |
| 12 | CSV upload validation (4xx, no 500) & template | **PASS** | - | Malformed status: 400 (4xx: True); Template status: 200 |
| 13 | GET /api/dashboard/summary (<=500ms) | **PASS** | 107.0ms | Status: 200 (107.0ms) |
| 14 | Chat assistant endpoints | **SKIP** | - | Not present (marked not present per Rule 5) |
| 15 | POST /api/seed/reset idempotency | **PASS** | - | Reset 1: 200, Reset 2: 200, Counts match: True |

## Environment Details

- Python: 3.13.15
- Platform: win32
- Backend: FastAPI + SQLite + PuLP (CBC Solver)
- Frontend: React 18 + Vite + Tailwind CSS