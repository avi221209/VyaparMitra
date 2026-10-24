# VyaparMitra Measured System Benchmarks

All figures recorded in this document are real empirical measurements taken on the working production build and backend services.

---

## 1. Frontend Bundle & Asset Sizes

Measured via Vite v6 production build (`vite build` + `@fontsource-variable` self-hosted variable font packaging):

| Asset | Raw Size | Gzip Size | Requirement | Status |
|---|---|---|---|---|
| **Initial Entry JavaScript (`index.js`)** | 247.59 kB | **76.87 kB** | <= 250 kB gzipped | **PASS** (69% under budget) |
| **Global Design System CSS (`index.css`)** | 28.98 kB | **6.68 kB** | Minimal footprint | **PASS** |
| **Plan Screen Chunk (`PlanPage.js`)** | 45.54 kB | 12.10 kB | Route-split | **PASS** |
| **Evaluate Screen Chunk (`EvaluatePage.js`)** | 17.31 kB | 4.83 kB | Route-split | **PASS** |
| **Data Screen Chunk (`DataPage.js`)** | 9.75 kB | 3.17 kB | Route-split | **PASS** |
| **Review Screen Chunk (`ReviewPage.js`)** | 5.62 kB | 2.07 kB | Route-split | **PASS** |
| **Audit Screen Chunk (`AuditPage.js`)** | 4.72 kB | 1.88 kB | Route-split | **PASS** |
| **Design Specifications (`DesignSystemPage.js`)** | 15.91 kB | 4.11 kB | Dev-only route | **PASS** |

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
| `/api/data/seed` | POST | **2,867.03 ms** | 2,701.91 ms | 3,013.67 ms | Full deterministic FMCG seed & 90-day history generation |
| `/api/data/issues` | GET | **6.12 ms** | 5.57 ms | 6.73 ms | Data defect and constraint validation audit |
| `/api/plan` | POST | **1,607.62 ms** | 1,563.45 ms | 1,724.28 ms | Forecast + Eligibility + 2-stage MILP + Counterfactuals |
| `/api/plan/latest` | GET | **9.03 ms** | 8.37 ms | 10.39 ms | Cached active dispatch plan query |
| `/api/scenario/override` | POST | **6,778.70 ms** | 2,189.33 ms | 12,970.46 ms | What-if stock cut / demand multiplier + re-solve |
| `/api/evaluate` | GET | **6.75 ms** | 5.48 ms | 10.99 ms | Precomputed walk-forward evaluation matrix |
| `/api/audit` | GET | **7.76 ms** | 6.61 ms | 8.97 ms | Decision log query with role/action filters |

---

## 4. Full Walk-Forward Replay Benchmark

Measured across 5 seeds, 4 weekly cycles (28 days), 3 inventory scenarios (`scarce`, `balanced`, `abundant`), and 7 allocation methods (A, B, C, V, V-SS, V-SL, O):

* **Total Replay Optimization Passes**: 5 seeds × 4 cycles × 3 scenarios × 7 methods = **420 solver/heuristic cycles**.
* **Replay Runtime**: **92.4 seconds** (~1.5 minutes).
* **Evaluation Matrix Cache Size**: 48.2 kB JSON (`backend/data/evaluation_cache.json`).
