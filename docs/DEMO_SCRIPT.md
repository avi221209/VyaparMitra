# VyaparMitra 3-Minute Live Evaluation Script

**Triwizathon 2026 | Team Stark**  
*Problem Statement 2: Distribution Intelligence and Inventory Optimization Engine*

This script outlines the exact 3-minute judge evaluation path. All steps are deterministic, verifiable via automated tests, and execute in under 5 clicks.

---

## Timeline & Step-by-Step Flow

### 0:00 — Screen: `/data` (Data & Integrity Validation)
- **Action**: Click **"Load sample data"**.
- **Result**: Ingests clean 24-SKU, 6-node network (Gurgaon W1, Bhiwandi W2, D1, D2, S1, S2) with 120 days of historical sales. Validation report displays `No data defects found. Data is ready for planning.`

### 0:20 — Screen: `/data` (Defect Ingestion & "Fix First" Gate)
- **Action**: Click **"Load file with errors"**.
- **Result**: Ingests ~20 injected Indian FMCG data anomalies (duplicate SKUs, negative inventory, mixed case packs, invalid expiry dates, missing sales gaps).
- **Verification**: Defective rows are blocked with `Fix first` badges in madder. The user cannot generate a plan until critical defects are either corrected (`Correct` modal) or explicitly excluded (`Exclude` action), ensuring zero contaminated data enters optimization.

### 0:50 — Screen: `/plan` (Two-Stage Deterministic Optimization)
- **Action**: Click **"Generate plan"** (Horizon: 7 days).
- **Result**: The two-stage PuLP MILP solver executes in ~0.4s.
- **Visuals**:
  1. **The Orchestrated Moment**: Hand-built SVG network lines draw in smoothly (600ms `stroke-dashoffset`) while dispatch rows settle with a 30ms stagger.
  2. **Single Summary Band**: Three figures separated by vertical rules:
     - Transport cost (e.g. ₹ 3,550)
     - Unmet demand (e.g. 45 cartons)
     - Safety-stock gap (e.g. 35 cartons)
  3. **Dispatch Register**: Grouped by destination with subtotal rows for cartons and freight.
  4. **Fallback Solver Notice**: If solver time limit is exceeded, heuristic plan is loaded and clearly badged.

### 1:20 — Screen: `/plan` (Dispatch Slip Inspection)
- **Action**: Click the **W1 to D2** row in the dispatch register.
- **Result**: Right-hand 480px **Dispatch Slip Drawer** slides in (180ms).
- **Explanation Card Data**:
  - `Sources considered`: Shows W1 (selected, cheapest eligible) and W2 (excluded: lane lead time gap 2d > Gmax 1d).
  - `Constraints checked`: Stock availability, lead time gap, lane capacity load, and acceptance shelf life.
  - `Residual risk`: Remaining unmet demand and safety-stock gap.

### 1:45 — Screen: `/plan` (Unmet Demand & Binding Constraints Panel)
- **Action**: Scroll down to the **Unmet Demand Panel** (demarcated by a solid madder left rule).
- **Result**: Inspect SKU shortages:
  - Destination & Product name
  - Unmet cartons & Safety-stock gap
  - Binding constraint (Stock, Lead time, Shelf life, or Lane capacity)
  - Smallest single fix with extra transport cost (e.g. `Add 10 cartons at W1 (+₹ 200 transport)`).

### 2:10 — Screen: `/plan` (What-If Scenario Simulation)
- **Action**: In the **What-If Bar** above the register:
  - Select `W1 Gurgaon Godown`, set percentage to `-20%`, click **"Regenerate"**.
- **Result**: Change summary band renders before/after columns with differences written in plain words (`"5 more cartons unmet"`, `"₹ 170 extra transport cost"`), never relying on color alone.

### 2:30 — Screen: `/plan` (Rule Enforcement & Refusal Logging)
- **Action**: Re-open dispatch slip drawer for W1. Use the carton stepper to increase cartons past available warehouse inventory (e.g. request 95 when stock is 90). Click **"Save cartons"**.
- **Result**:
  - Backend refuses the edit with **HTTP 409 Conflict**.
  - UI displays an InlineMessage stating the exact numbers: `"Warehouse W1 holds 90 cartons. This edit requests 95 cartons. Enter 90 or fewer."`
  - Input field retains focus with the user's typed value preserved.
  - The refusal is permanently recorded in the immutable audit log (`EDIT_REFUSED`).

### 2:45 — Screen: `/evaluate` (Walk-Forward Replay Benchmark)
- **Action**: Click **Evaluate** in the left rail.
- **Result**:
  - Dynamically generated opening sentence: `"VyaparMitra beat the min/max rule on fill rate in 5 of 5 seeds in the balanced scenario."`
  - Hand-built SVG Dot Plots: 5 dots per method with mean tick mark; VyaparMitra in brand color, baselines in ink-2, oracle hollow; directly labeled at track ends.
  - Benchmark Targets table with pass/fail indicators.
  - Ablations table (`V`, `V-SS`, `V-SL`).
  - **"Where We Lose"** section: Lists any metric or scenario where VyaparMitra does not beat a baseline with its diagnosed operational cause, displayed with equal visual weight.
