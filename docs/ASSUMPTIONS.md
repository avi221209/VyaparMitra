# VyaparMitra - Engineering Assumptions & Design Choices
**Team Stark | Triwizathon 2026 | PS2: Distribution Intelligence and Inventory Optimization Engine**

As mandated by Rule 7 ("Where the spec is ambiguous, choose the simplest interpretation, write it in docs/ASSUMPTIONS.md, and keep going"), this document records all architectural, modeling, and operational assumptions for VyaparMitra.

---

## 1. Unit & Carton Accounting (Rule 5)
- **Primary Optimization Unit**: All physical shipments, warehouse inventory, batch quantities, and lane capacities are measured in **whole cartons** (integers).
- **Case Pack Conversion**: Each SKU defines a `case_pack` (units per carton, default `1`). If sales or demand data is ingested in individual units, destination requirement is calculated as:
  $$\text{Cartons Required} = \left\lceil \frac{\text{Units Required}}{\text{case\_pack}} \right\rceil$$
- **Rounding**: Any partial carton required is rounded up to the nearest whole carton to prevent stockouts at retail/distributor level.

## 2. Hard Eligibility Constraints & Tolerances (Rule 3)
- **Lane Existence**: Shipments can only occur across valid, active lanes defined in the network topology.
- **Lane Gap Constraint ($G_{\max} = 1$ day)**: If multiple warehouses can supply a destination, the difference between the maximum and minimum lead times among dispatched lanes to that destination cannot exceed $G_{\max}$ days (default 1 day), avoiding staggered, chaotic arrivals.
- **Shelf-Life Cap ($E_{\text{short}} = 21$ days)**: Batches arriving with remaining shelf life strictly less than $E_{\text{short}}$ days upon destination arrival are ineligible for dispatch.
  $$\text{Remaining Shelf Life at Arrival} = \text{Expiry Date} - (\text{Run Date} + \text{Lead Time Days})$$
- **Lane Capacity**: Total cartons shipped on lane $(w, d)$ in a single planning run cannot exceed `capacity_load` (if specified; nullable implies unconstrained).
- **Stock Availability**: Shipments cannot exceed available cartons of any batch minus `planner_reserve`. Never invent or phantom-allocate inventory.

## 3. Two-Stage Deterministic Integer Program (Rules 1 & 2)
- **Stage 1 (Fulfillment Maximization)**: Minimize unmet net requirements across all destination-product pairs:
  $$\min \sum_{d, p} U_{d, p}$$
- **Stage 2 (Cost & Efficiency Optimization)**: Subject to keeping total unmet cartons equal to Stage 1's optimum ($U^*$), minimize total distribution cost (transit cost + secondary penalty) with deterministic tie-breaking:
  - Tie-breaking order: (1) Lane transit cost ascending, (2) Lane lead time ascending, (3) Source warehouse and batch identifier lexicographical order.
- **Fixed Solver Parameters**: Solver is PuLP with CBC (`PULP_CBC_CMD(msg=False, timeLimit=solver_time_limit)`). Time limit defaults to 10.0 seconds.

## 4. Counterfactual Relaxations (Rule 4)
- **Requirement Invariance**: Requirements ($N_{\text{dem}}, N_{\text{tot}}$) are calculated once per run and frozen.
- **What-If Explanations**: When unmet demand exists ($U_{d, p} > 0$), the engine evaluates relaxations (e.g. relaxing lane capacity, relaxing shelf-life threshold $E_{\text{short}}$, allowing alternate warehouses, or identifying required additional factory stock) without modifying the underlying demand requirement.

## 5. Security & Demo Roles (Rule 6)
- **Role Header**: The application checks the `X-Role` HTTP header (`planner`, `warehouse`, `reviewer`).
- **Demo Scope**: This is an illustrative role-based access pattern for the hackathon demonstration, not production cryptographic authentication.

## 6. Simulation & Data Honesty (Rule 1)
- **Labeling**: All synthetic Indian FMCG datasets, database records, API payloads, and frontend views carry the `SIMULATED` badge and attribute.
- **No Hardcoding**: All numbers, metrics, costs, and plan lines originate purely from algorithmic execution (forecasting, requirements arithmetic, and PuLP MILP solver).

## 7. Data Validation & "Fix First" Gate
- **6 Defect Classes**:
  1. *Duplicate SKUs*: Exact duplicate IDs or normalized token similarity $\ge 0.85$ with matching category/unit. Severity: `critical`.
  2. *Mixed Units*: Unrecognized unit names (Severity: `warning`), non-positive case pack $\le 0$ (Severity: `critical`), or extreme $\ge 10\times$ demand jumps (Severity: `warning`).
  3. *Negative Inventory/Sales*: $on\_hand < 0$, $batch\_qty < 0$, $sales < 0$. Severity: `critical`.
  4. *Invalid/Impossible Dates*: Expiry date $\le$ run date. Severity: `critical`.
  5. *Contradictory Stock*: $on\_hand < reserved$. Severity: `critical`.
  6. *Missing Sales Days*: Sales gaps $> 2$ consecutive days in a series. **Missing sales are NEVER silently treated as zero demand**; the series is explicitly marked as *'insufficient data'*. Severity: `warning`.
- **"Fix First" Gate**:
  - Any entity with a `critical` and `open` validation issue is blocked from optimization runs. Planning refuses to process blocked rows.
  - An issue can be transitioned via `/api/data/issues/{id}/resolve` (corrected) or `/acknowledge` (explicitly excluded from planning), both logged to `DecisionLog`.

## 8. Demand Forecasting & Uncertainty Estimation (services/forecast.py)
- **Candidate Models**:
  1. *Seasonal-Naive*: Same weekday from previous week ($d - 7$ days).
  2. *7-Day Moving Average*: Unweighted arithmetic mean of the 7 calendar days directly preceding `as_of`.
  3. *Exponential Smoothing with Day-of-Week Factors*: Level smoothing with $\alpha = 0.25$ over de-seasonalized series using multiplicative weekday factors.
- **Model Selection via Rolling-Origin Cross-Validation**:
  - 3 folds of 7 days covering the last 21 days before `as_of`:
    - Fold 1: Origin $as\_of - 21\text{d}$, test $[as\_of - 21\text{d}, as\_of - 15\text{d}]$, train $< as\_of - 21\text{d}$.
    - Fold 2: Origin $as\_of - 14\text{d}$, test $[as\_of - 14\text{d}, as\_of - 8\text{d}]$, train $< as\_of - 14\text{d}$.
    - Fold 3: Origin $as\_of - 7\text{d}$, test $[as\_of - 7\text{d}, as\_of - 1\text{d}]$, train $< as\_of - 7\text{d}$.
  - Scoring Metric: $\text{WAPE} = \frac{\sum |y - \hat{y}|}{\sum y}$ (avoiding division by zero on zero-demand days).
  - Tie-breaking: Simpler model wins (`seasonal_naive` > `moving_average_7` > `exp_smoothing_dow`).
- **Strict No-Leakage Guarantee**:
  - Every forecast function takes `as_of: date` and filters $date < as\_of$.
  - The exact same evaluation logic is used in cross-validation and live forecasting.
- **Uncertainty Sigma & Group Shrinkage**:
  - Standard deviation of pooled fold errors $\sigma_{\text{series}}$ shrunk toward group sigma $\sigma_{\text{group}}$ (grouped by `product.category` and `location.type`):
    $$\sigma = (1 - \text{shrinkage}) \times \sigma_{\text{series}} + \text{shrinkage} \times \sigma_{\text{group}} \quad (\text{default shrinkage } 0.5)$$
- **Zero-Heavy Fallback**:
  - Series with $> 50\%$ zero days in the 28-day window use a flat 28-day mean with Poisson spread: $\sigma = \sqrt{\text{mean}}$.
- **Operational Warnings**:
  - Warning attached if historical observations $< 60$ days or marked as `insufficient data` in data validation.

## 9. Net Requirement & Batch Eligibility Pure Services (services/requirement.py & services/eligibility.py)
- **Zero Database Side-Effects**: Both services are implemented strictly as pure functions accepting plain data structures and returning deterministic results.
- **Requirement Mechanics (per destination $d$, product $k$)**:
  - Effective stock position: $pos = on\_hand - reserved + confirmed\_in\_transit$.
  - Inventory cover: $cover = pos / f$ (days; $\infty$ if $f = 0$).
  - Inbound eligible lanes: Lanes where $G = \max(0, L[s, d] - cover) \le Gmax$.
  - Governing lead time $Ld$: Longest lead time among eligible lanes (or fastest if configured).
  - Horizon $P = H + Ld$.
  - Cumulative forecast: $F = \sum_{t=1}^P f_t$ (or $P \times f$).
  - Safety stock: $SS = z \times \sigma \times \sqrt{P}$.
  - Net demand: $Ndem = \lceil \max(0, F - pos) / case\_pack \rceil$.
  - Total requirement: $Ntot = \lceil \max(0, F + SS - pos) / case\_pack \rceil$.
  - Computed once per run and frozen.
- **Eligibility Mechanics (per batch $b$, source $s$, destination $d$, product $k$)**:
  - *Lane Gap*: $G = \max(0, L[s, d] - cover)$. Allowed if $G \le Gmax$. If $G > 0$, flagged with unavoidable lost sales $f \times G$ before arrival.
  - *Acceptance Life*: Days to expiry at arrival $e = \text{days\_to\_expiry} - L[s, d] \ge min\_remaining\_shelf\_days$. Batches arriving below threshold are excluded.
  - *Cumulative FEFO Sell-Through Cap*: For each distinct $e$, total cartons from all batches with days-to-expiry $\le e$ cannot exceed $\max(0, f \times e - pos)$.
  - *Lane Capacity & Carton Load*: Exposed for the downstream PuLP optimizer.

## 10. Frontend Architecture & Design System (Phases 1-6)
- **Design Metaphor**: Physical FMCG distribution desk ledger: quiet ruled tabular rows, right-aligned numbers with Indian numbering formatting (`₹ 1,05,000`), and a single signature element (the "Simulated data" stamp at -1.5° rotation and the Dispatch Slip drawer).
- **Self-Hosted Assets**: Self-hosted variable fonts (`@fontsource-variable/public-sans` and `@fontsource-variable/source-serif-4`) bundled as WOFF2 in Vite build. Zero third-party CDN or network tracking calls.
- **Accessible Border Contrast**: Adjusted `line-strong` token to `#7E8E9E` (3.36:1 on surface, 3.10:1 on paper) to rigorously satisfy WCAG 2.1 SC 1.4.11 Non-text Contrast (3:1 minimum).
- **URL & Storage Synchronization**: Filters, sorting, horizon, line selection, and density preferences synchronize to URL query parameters and localStorage for deterministic bookmarking and shareable ledger states.
- **Safe Actions & Undo**: Human approvals and rejections trigger an 8-second toast with an inline `Undo` action that calls the counter-endpoint and logs to `DecisionLog`.

## 11. Canonical Data Manifests & Backward-Compatible Aliases
- **Canonical Files in `data/`**:
  - `locations.csv`: Combined warehouse and destination entities with `type` column (`warehouse`, `distributor`, `store`).
  - `products.csv`: 24 SKUs across 5 FMCG categories with packaging, carton dimensions, and cost structures.
  - `lanes.csv`: Transportation lane definitions connecting warehouses to destinations with lead times, costs, and capacities.
  - `batches.csv`: Physical stock batches stored across warehouses.
  - `inventory_snapshots.csv`: On-hand, reserved, and in-transit stock positions at destinations.
  - `sales_daily.csv`: Daily historical demand series.
  - `manifest.json`: Simulation generator parameters, record counts, and tight lane declarations.
  - `defect_manifest.json`: Ground-truth injected defects used for validation benchmark recall audits.
  - `evaluation_cache.json`: Precomputed 28-day walk-forward replay benchmark results across 5 seeds and 3 scenarios.
  - `backup_demo_plan.json`: Instant zero-solver backup plan for unbreakable offline demonstration.
- **Backward-Compatible Alias Resolution**:
  - In `GET /api/data/template/{name}` and `POST /api/data/upload`, the backend maintains `ENTITY_ALIASES` mapping singular, legacy, or prototype entity names (`inventory_batches` -> `batches`, `warehouses` / `destinations` -> `locations`, `sales_history` -> `sales`) directly to their canonical schema.
  - Redundant prototype CSV files (`warehouses.csv`, `destinations.csv`, `inventory_batches.csv`, `sales_history.csv`) are retired from git to eliminate schema ambiguity.
- **Bi-directional URL Synchronization**:
  - The planning workspace (`/plan?line=...`) supports bi-directional sync: state changes update URL parameters via replace, and direct navigation/deep-linking/back-forward updates component selection without reload.
