# VyaparMitra (व्यापारमित्र)
### Distribution Intelligence & Inventory Optimization Engine
**Production-Grade Decision Support for Regional FMCG Distribution**

---

## 1. Overview
**VyaparMitra** is a decision-support and supply-chain optimization tool engineered for regional Indian FMCG distribution networks. A distribution planner loads stock, sales, and lane data. The system validates network integrity, forecasts SKU-destination demand, computes net carton requirements, and executes a two-stage deterministic mixed-integer program (MILP) to allocate physical batches to destinations while enforcing shelf-life, lane gap, and capacity constraints.

The user interface borrows the clarity of a physical ledger: ruled rows, right-aligned tabular figures, calm color palette, and two signature touches: the "Simulated data" stamp (-1.5° rotation) and the Dispatch Slip drawer with counterfactual explanations.

> **DEMO & SIMULATION NOTICE**  
> All data within VyaparMitra is simulated and explicitly tagged with `SIMULATED` (`is_simulated=True`). No live orders are dispatched. Every number and recommendation is computed algorithmically—never hardcoded. No real-world savings are claimed.

---

## 2. Quick Start (One Command)

### Windows
Double-click `start.bat` or run:
```cmd
start.bat
```

### macOS / Linux
Run:
```bash
chmod +x start.sh
./start.sh
```

The startup script verifies Python and Node.js, installs dependencies, verifies the evaluation cache, auto-seeds the sample FMCG network if the database is empty, and starts both backend (port 8000) and frontend (port 5173).

* **Frontend Ledger**: [http://localhost:5173](http://localhost:5173)
* **Backend API Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Design System Reference**: [http://localhost:5173/design](http://localhost:5173/design)

---

## 3. Fresh-Machine Installation & Test

To set up and run on a brand-new machine:

```bash
# 1. Clone repository
git clone <repo-url>
cd Vyaparmitra

# 2. Python backend environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

# 3. Frontend environment
npm install
npm run build

# 4. Run test suite
python -m pytest backend/tests -v
npm run test:contrast

# 5. Launch
start.bat   # Windows
# or ./start.sh on macOS/Linux
```

---

## 4. Key Workflows & UI Screens

1. **Data Screen (`/data`)**:
   - One row of 3 deterministic loading buttons: "Load sample data", "Load file with errors" (~20 defects), "Load low W1 stock".
   - Quiet drag-and-drop area for CSV master files with downloadable templates.
   - Validation report table with "Fix first" gate for critical defects with Correct and Exclude actions.
   - First-run guidance checklist for new operators.
2. **Distribution Plan Screen (`/plan`)**:
   - Single summary band with 3 core metrics: Transport Cost, Unmet Demand, and Safety-Stock Gap, each with an interactive "How this was calculated" popover.
   - Hand-built SVG Network Strip with bezier flow lines proportional to carton volumes and hollow alert rings on destinations with shortages.
   - Grouped Dispatch Register with destination subtotals, sorting on all columns, search, active filter chips, row density toggle, and "Show details" toggle.
   - Madder-ruled Unmet Demand & Binding Constraints panel with smallest actionable fixes and extra freight cost.
   - Forecast Drawer with 28-day historical sales, 7-day forecast line, and P90 uncertainty band.
   - 600 ms orchestrated entrance animation on generation (respected by `prefers-reduced-motion`).
   - "Download plan as CSV" and print stylesheet.
3. **Dispatch Slip Drawer**:
   - 480px right-hand drawer showing sources considered with clear physical reasons, constraint checks (stock, lead time gap, lane capacity, acceptance life), and residual risk.
   - Carton stepper with HTTP 409 rule violation inline alert.
   - Approve / Reject buttons with 8-second Undo toast.
4. **Plan Review Screen (`/review`)**:
   - Role-gated review interface with pending approval metrics, filterable status views, and batch approval.
5. **Walk-Forward Evaluation Screen (`/evaluate`)**:
   - Hand-built SVG dot plots across 5 metrics (fill rate, unmet units, cost per unit served, expiry waste, cost-to-serve) over 5 seeds with mean ticks and direct track labels.
   - Benchmark targets table with headroom status check.
   - Ablation studies (V vs V-SS vs V-SL).
   - "Where We Lose" panel highlighting limits with equal visual weight.
   - Progress bar during simulation re-runs.
6. **Decision Log & Audit Trail (`/audit`)**:
   - Chronological audit ledger with actor role filters, action filters, search, and human-readable changes ("from 20 to 18 cartons").

---

## 5. System Settings

Editable in the Settings Drawer (`Cmd+K` -> Open Settings) or via `GET/PUT /api/settings`:

| Setting | Parameter | Default | Plain-Language Description |
|---|---|---|---|
| Horizon | $H$ | 7 days | Number of forward calendar days evaluated in planning run. |
| Safety Stock Factor | $z$ | 1.28 | Z-score target (~90% cycle service level). |
| Shortfall Penalty | $\alpha$ | 0.25 | Relative weight of safety-stock shortfall vs net demand. |
| Max Lane Gap | $G_{\max}$ | 1 day | Maximum allowed arrival spread among multiple supply lanes. |
| Minimum Shelf Life | $E_{\text{short}}$ | 21 days | Minimum acceptable remaining days to expiry upon destination delivery. |
| Shrinkage Factor | — | 0.5 | Weight given to category-level variance when series history is short. |
| Planner Reserve | — | 0 cartons | Buffer cartons held back per batch from automated optimization. |
| Solver Time Limit | — | 10.0 s | Maximum CBC integer program optimization time before fallback. |

---

## 6. Measured Performance Benchmarks

Detailed empirical logs available in [`docs/MEASURED.md`](file:///docs/MEASURED.md) and [`docs/UX_TESTS.md`](file:///docs/UX_TESTS.md):

* **Initial Frontend Bundle**: **76.87 kB gzipped** (raw: 247.59 kB, requirement: $\le 250\text{ kB}$).
* **Plan Solver Time (24 SKUs × 4 DCs × 2 Warehouses)**: **1,878.72 ms** (1.88 seconds).
* **Full Replay Runtime (5 seeds × 4 cycles × 3 scenarios × 7 methods = 420 passes)**: **92.4 seconds**.
* **API Latencies**:
  - `GET /api/plan/latest`: 9.03 ms
  - `POST /api/plan`: 1,607.62 ms
  - `GET /api/evaluate`: 6.75 ms
  - `GET /api/audit`: 7.76 ms
* **Lighthouse Scores (Desktop)**: Performance: 98, Accessibility: 100, Best Practices: 100, SEO: 100.
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
