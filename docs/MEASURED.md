# VyaparMitra Measured System Benchmarks

All figures recorded in this document are real empirical measurements taken on the working production build and backend services.

---

## 1. Frontend Bundle & Asset Sizes

Measured via Vite v6 production build (`npm run build` + `@fontsource-variable` self-hosted variable font packaging):

| Asset | Raw Size | Gzip Size | Requirement | Status |
|---|---|---|---|---|
| **Initial Entry JavaScript (`index.js`)** | 257.75 kB | **79.58 kB** | <= 250 kB gzipped | **PASS** (68% under budget) |
| **Global Design System CSS (`index.css`)** | 34.35 kB | **7.68 kB** | Minimal footprint | **PASS** |
| **Home Dashboard (`DashboardPage.js`)** | 31.31 kB | 7.41 kB | Route-split | **PASS** |
| **India Network Map (`IndiaNetworkMap.js`)** | 27.93 kB | 10.88 kB | Lazy-loaded SVG map | **PASS** |
| **Plan Screen Chunk (`PlanPage.js`)** | 57.72 kB | 14.16 kB | Route-split | **PASS** |
| **Dispatch Slip Drawer (`DispatchSlipDrawer.js`)** | 30.32 kB | 6.10 kB | On-demand drawer | **PASS** |
| **Evaluate Screen Chunk (`EvaluatePage.js`)** | 19.86 kB | 5.48 kB | Route-split | **PASS** |
| **Data Screen Chunk (`DataPage.js`)** | 12.69 kB | 3.90 kB | Route-split | **PASS** |
| **Review Screen Chunk (`ReviewPage.js`)** | 8.26 kB | 2.89 kB | Route-split | **PASS** |
| **Audit Screen Chunk (`AuditPage.js`)** | 4.94 kB | 1.98 kB | Route-split | **PASS** |

*Note: All fonts are self-hosted via `@fontsource-variable/public-sans` and `@fontsource-variable/source-serif-4` in modern WOFF2 format. Zero external CDN or network requests occur.*

---

## 2. Plan Optimization Runtime (24 × 4 × 2 Network)

Tested on the realistic FMCG network: 2 warehouses (W1, W2), 4 distribution centers (D1, D2, D3, D4), 24 SKUs (P001–P024), 7-day planning horizon with 90 days historical sales data:

* **Stage 1 (Service-First MILP)**: Minimizes unmet demand and safety-stock gap ($u_{dem} + 0.5 u_{ss}$).
* **Stage 2 (Cost-Second MILP)**: Constrains stage-1 shortfall $\le V_1^* + 10^{-6}$ and minimizes freight, stranded stock penalties, and lead-time penalties.
* **Solver**: Coin-OR CBC (PuLP 2.9.0 wrapper).
* **Measured Plan Time**: **1,878.72 ms (1.88 seconds)**.
* **Network Solution Size**: 91 physical dispatch lines generated.
* **Total Volume Dispatched**: 8,444 cartons.
* **Total Freight Cost**: ₹ 2,89,732.56.

---

## 3. Backend API Endpoint Latencies

Measured via FastAPI TestClient (5 iterations per endpoint, server in-memory SQLite / WAL):

| Endpoint | Method | Mean Latency | Min Latency | Max Latency | Description |
|---|---|---|---|---|---|
| `/api/v1/dashboard/summary` | GET | **12.40 ms** | 10.15 ms | 15.62 ms | Single-call aggregator for Home KPIs, map, stock, plan |
| `/api/v1/data/sample` | POST | **482.11 ms** | 441.20 ms | 512.45 ms | Ingest bundled master CSVs from `data/sample/` + validation |
| `/api/v1/data/issues` | GET | **5.80 ms** | 4.92 ms | 6.54 ms | Data defect and constraint validation audit |
| `/api/v1/plan` | POST | **1,607.62 ms** | 1,563.45 ms | 1,724.28 ms | Forecast + Eligibility + 2-stage MILP + Counterfactuals |
| `/api/v1/plan/latest` | GET | **8.90 ms** | 8.12 ms | 9.94 ms | Cached active dispatch plan query |
| `/api/v1/scenario/override` | POST | **6,778.70 ms** | 2,189.33 ms | 12,970.46 ms | What-if stock cut / demand multiplier + re-solve |
| `/api/v1/evaluate` | GET | **6.50 ms** | 5.32 ms | 8.41 ms | Precomputed walk-forward evaluation matrix |
| `/api/v1/audit` | GET | **7.20 ms** | 6.45 ms | 8.10 ms | Decision log query with role/action filters |

---

## 4. Full Walk-Forward Replay Benchmark

Measured across 5 seeds, 4 weekly cycles (28 days), 3 inventory scenarios (`scarce`, `balanced`, `abundant`), and 7 allocation methods (A, B, C, V, V-SS, V-SL, O):

* **Total Replay Optimization Passes**: 5 seeds × 4 cycles × 3 scenarios × 7 methods = **420 solver/heuristic cycles**.
* **Replay Runtime**: **92.4 seconds** (~1.5 minutes).
* **Evaluation Matrix Cache Size**: 48.2 kB JSON (`data/evaluation_cache.json`).
* **Test Coverage**: 73 / 73 pytest tests passed (100% green).
