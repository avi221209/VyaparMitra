# VyaparMitra (व्यापारमित्र)
### Distribution Planning & Inventory Optimization Engine
**Production-Grade Decision Support for Regional FMCG Distribution**

---

## 1. Overview

**VyaparMitra** is a decision-support and supply-chain optimization tool engineered for regional Indian FMCG distribution networks. A distribution planner loads stock, sales, and lane data. The system validates network integrity, forecasts SKU-destination demand, computes net carton requirements, and executes a two-stage deterministic mixed-integer program (MILP) to allocate physical batches to destinations while enforcing shelf-life, lane gap, and capacity constraints.

The user interface borrows the clarity of a physical ledger: ruled rows, right-aligned tabular figures, calm color palette, and two signature touches: the "Simulated data" stamp (-1.5° rotation) and the Dispatch Slip drawer with counterfactual explanations.

> **DEMO & SIMULATION NOTICE**  
> All data within VyaparMitra is simulated and explicitly tagged with `SIMULATED` (`is_simulated=True`). No live orders are dispatched. Every number and recommendation is computed algorithmically—never hardcoded. No real-world savings are claimed.

---

## 2. Quick Start (One Command)

### Docker (Recommended)
Run the full production stack in a single container:
```bash
docker compose up --build
```
* **Web Application**: [http://localhost:8000](http://localhost:8000)
* **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Local Launchers

#### Windows
Double-click `start.bat` or run:
```cmd
start.bat
```

#### macOS / Linux
Run:
```bash
chmod +x start.sh
./start.sh
```

The launcher checks Python and Node.js, installs dependencies, verifies the SQLite database and sample data, and starts both backend (port 8000) and frontend (port 5173).

* **Frontend**: [http://localhost:5173](http://localhost:5173)
* **Backend API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 3. Fresh-Machine Installation & Test

To set up and run on a brand-new machine:

```bash
# 1. Clone repository
git clone https://github.com/avi221209/VyaparMitra.git
cd Vyaparmitra

# 2. Python backend environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. Frontend environment
npm install
npm run build

# 4. Run test suite
python -m pytest backend/tests -v
node scripts/contrast.mjs

# 5. Launch
start.bat   # Windows
# or ./start.sh on macOS/Linux
```

---

## 4. Key Workflows & UI Screens

1. **Home Dashboard (`/`)**:
   - Executive operational overview with greeting and current planning period.
   - 4 KPI cards: Transport Cost, Service Level, Expiry at Risk, and Benefit vs Baseline (computed dynamically against Forecast+Greedy).
   - Hand-built SVG India Network Map powered by offline Survey of India GeoJSON and `d3-geo`, displaying warehouses, retailer nodes, and dispatch volume arcs.
   - Stock Status table across all 24 regional SKUs with healthy, low, and critical badges.
   - Recent Plan card and 8-week Walk-Forward Demand & Dispatch forecast chart.
   - Pending Approvals card with inline approval/rejection and an 8-second undo toast.
2. **Data & Network Validation (`/data`)**:
   - One-click "Load sample data" button restoring bundled regional FMCG master data.
   - Quiet drag-and-drop CSV upload area with strict column validation and downloadable templates.
   - Data issue ledger categorizing Critical and Warning issues with a strict "Fix first" gate for critical items.
3. **Distribution Plan (`/plan`)**:
   - Two-stage integer programming optimizer (PuLP + CBC) with greedy heuristic fallback.
   - Grouped dispatch register organized by destination with subtotals, sorting, filtering, and keyboard navigation (`j`/`k`/`Enter`/`a`/`r`).
   - Unmet Demand & Binding Constraints panel diagnosing shortages, binding rules (C1 Stock, C2 Lead Time, C3 Allocation, C4 Shelf Life, C5 Lane Gap, C6 Lane Capacity), and minimal actionable relaxations.
   - Forecast Drawer illustrating historical sales, 7-day forecast vector, and uncertainty bands.
4. **Dispatch Slip Drawer**:
   - 480px drawer displaying all sources considered, eligible/excluded reasons, physical constraint evaluations, and residual risk.
   - Surplus rescue analysis with fair risk-sharing price bands and 3-way landed cost comparisons.
   - Inline carton adjustment with immediate rule validation (HTTP 409 on constraint violation).
5. **Plan Review (`/review`)**:
   - Role-gated approval register (Planner, Reviewer, Warehouse) with batch approvals and rejection audit notes.
6. **Walk-Forward Evaluation (`/evaluate`)**:
   - 28-day rolling evaluation simulating 4 weekly cycles across 5 seeds.
   - Multi-metric benchmark comparing VyaparMitra against Min/Max, Proportional Split, and Forecast+Greedy baselines.
   - Ablation studies and an honest "Where We Lose" section.
7. **Decision Log & Audit Trail (`/audit`)**:
   - Immutable chronological audit ledger with role, action, and entity filters.

---

## 5. System Settings

Configurable in the Settings Drawer (`Cmd+K` -> Open Settings) or via `GET/PUT /api/v1/settings`:

| Setting | Parameter | Default | Plain-Language Description |
|---|---|---|---|
| Horizon | $H$ | 7 days | Forward calendar days evaluated in planning run. |
| Safety Stock Factor | $z$ | 1.28 | Z-score target (~90% cycle service level). |
| Shortfall Penalty | $\alpha$ | 0.25 | Relative weight of safety-stock shortfall vs net demand. |
| Max Lane Gap | $G_{\max}$ | 1 day | Maximum allowed arrival spread among multiple supply lanes. |
| Minimum Shelf Life | $E_{\text{short}}$ | 21 days | Minimum acceptable remaining days to expiry upon destination delivery. |
| Shrinkage Factor | — | 0.5 | Weight given to category-level variance when series history is short. |
| Planner Reserve | — | 0 cartons | Buffer cartons held back per batch from automated optimization. |
| Solver Time Limit | — | 10.0 s | Maximum CBC integer program optimization time before fallback. |

---

## 6. Measured Performance Benchmarks

Detailed empirical logs available in [`docs/MEASURED.md`](file:///docs/MEASURED.md):

* **Initial Frontend Bundle**: **79.58 kB gzipped** (raw: 257.75 kB, code-split).
* **Network Map Chunk**: **10.88 kB gzipped** (`IndiaNetworkMap.tsx`, lazy-loaded).
* **Plan Solver Time (24 SKUs × 4 DCs × 2 Warehouses)**: **1,878.72 ms** (1.88 seconds).
* **Full Replay Runtime (5 seeds × 4 cycles × 3 scenarios × 7 methods = 420 passes)**: **92.4 seconds**.
* **API Latencies**:
  - `GET /api/v1/dashboard/summary`: 12.4 ms
  - `GET /api/v1/plan/latest`: 9.03 ms
  - `POST /api/v1/plan`: 1,607.62 ms
  - `GET /api/v1/evaluate`: 6.75 ms
  - `GET /api/v1/audit`: 7.76 ms
* **Test Suite**: **73 backend pytest tests passed** (100% passing).
* **WCAG 2.1 Contrast Checks**: 20 of 20 token pairs pass AA standard (`scripts/contrast.mjs`).

---

## 7. System Limitations & Honesty Boundaries

1. **Simulated Data Only**: All master data, transaction history, and network topologies are generated by `FMCGSimulator`. No real-world customer or vendor data is used.
2. **Demo Role Selector, Not Authentication**: The `X-Role` header (`planner`, `warehouse`, `reviewer`) simulates operational roles for demonstration and audit logging. It does not provide cryptographic identity verification.
3. **Myopic Single-Horizon Planning**: Optimization optimizes allocations for the specified horizon $H$ with frozen inventory positions, rather than executing multi-period stochastic dynamic programming.
4. **Linear Freight Model**: Transportation costs are modeled as constant freight cost per carton per lane ($c_{s,d}$). Vehicle routing, backhauling, and truck capacity volumetric loading are not modeled.
5. **Simulated Savings Disclaimer**: All reported fill-rate improvements, waste reductions, and cost benefits are computed on synthetic benchmark scenarios and are not guarantees of actual commercial savings.

---

## 8. Keyboard Shortcuts & Command Palette

Press `Cmd+K` or `Ctrl+K` from anywhere in the app to open the Command Palette.
Press `?` on the Plan screen to view the shortcut cheat sheet:

* `j` / `ArrowDown`: Move to next row in register
* `k` / `ArrowUp`: Move to previous row in register
* `Enter`: Open Dispatch Slip for active row
* `a`: Approve active line (planner / reviewer)
* `r`: Reject active line
* `e`: Edit cartons in active line
* `Esc`: Close any open drawer or modal
