# VyaparMitra Design Audit: From Generic SaaS Template to Regional FMCG Planning Desk

**Author**: Senior Product Designer & Front-End Lead  
**Context**: Comprehensive UX & visual audit of the VyaparMitra interface  
**References**: `docs/DESIGN.md`, `docs/COPY.md`

---

## Executive Summary

The functional architecture of VyaparMitra is deterministic, verified, and complete. However, the visual presentation suffered from several common "AI-generated SaaS template" tells:
1. **Containeritis / Floating Box Grid**: Almost every section was wrapped in an identical rounded card (`rounded-control p-4 border border-line bg-surface`), creating stacks of floating bubbles instead of a continuous, ruled ledger.
2. **Generic Decorative Affordances**: Numbered circle badges (`rounded-full` 1, 2, 3), middle dot separators (`•`), and shadow utilities on content (`shadow-md` on offline alerts and mobile navigation).
3. **Typography Inconsistencies**: Tracked uppercase labels on simulated data stamps, all-caps select options in audit filters, Title Case in table headers and drawer sections, and missing the 40px display serif figure on Evaluate.
4. **Subject Dissociation**: The interface felt like a generic analytics dashboard rather than a physical regional FMCG godown planning desk with dispatch registers, transit lanes, physical carton tallies, and verification challans.

---

## Catalog of Template Tells & Violations Found

### 1. Grids of Identical Rounded Cards & Excessive Enclosure
- **`src/pages/DataPage.tsx` (Lines 282, 298-337)**:
  - *Tell*: First-run guide is built as a generic 3-card card grid (`grid grid-cols-1 sm:grid-cols-3 gap-3`) with individual rounded boxes.
  - *Fix*: Replace with a quiet, single-row ruled sequence strip reminiscent of a godown inward receipt workflow with clean checkmarks.
- **`src/pages/PlanPage.tsx` (Lines 661, 757, 767, 824, 1001, 1207)**:
  - *Tell*: Vertical stack of 6 identical rounded white cards (`border border-line bg-surface rounded-control`) with arbitrary internal padding.
  - *Fix*: Transition to continuous ledger architecture. Demarcate sections via hairline horizontal rules (`border-b border-line`) and disciplined 24px/32px vertical rhythm. Remove rounded corners on the primary dispatch register and summary band.
- **`src/components/plan/DispatchSlipDrawer.tsx` (Lines 280-305, 314-346, 354-375)**:
  - *Tell*: Sources considered are rendered as floating cards with thick borders (`p-3 rounded-control bg-paper border border-line`); checks are wrapped in a generic container; residual risk is a 2-card grid.
  - *Fix*: Re-engineer as an authentic commercial dispatch slip: ruled entries, compact two-column tabular check verification with status icons, and clean ruled ledger totals.

### 2. Shadows on Content
- **`src/components/layout/AppShell.tsx` (Line 165)**:
  - *Tell*: `shadow-md` on the unreachable backend banner.
  - *Fix*: Remove `shadow-md`. `DESIGN.md` explicitly forbids shadows on content (`--shadow-overlay` is reserved strictly for drawers, modals, and popovers).
- **`src/components/layout/AppShell.tsx` (Line 314)**:
  - *Tell*: `shadow-md` on the mobile bottom bar.
  - *Fix*: Remove `shadow-md`. Rely on a crisp top rule (`border-t border-line`) and solid `bg-surface`.

### 3. All-Caps Labels and Tracked Eyebrows
- **`src/components/layout/AppShell.tsx` (Line 270)**:
  - *Tell*: `uppercase tracking-wider` on the "Simulated data" stamp.
  - *Fix*: Change to sentence case `Simulated data` without letter tracking, preserving the signature -1.5° rotated border.
- **`src/pages/EvaluatePage.tsx` (Line 202)**:
  - *Tell*: Duplicate simulated data stamp using `uppercase tracking-wider`.
  - *Fix*: Convert to sentence case `Simulated data` without tracking.
- **`src/components/layout/CommandPalette.tsx` (Line 222)**:
  - *Tell*: Group headers using `uppercase tracking-wider font-semibold`.
  - *Fix*: Convert to clean sentence case `Navigation`, `Actions`, `Display`.
- **`src/pages/AuditPage.tsx` (Lines 189-194)**:
  - *Tell*: Filter select options with all-caps values (`OPTIMIZE`, `APPROVE`, `EDIT`, `EDIT_REFUSED`, `REJECT`, `OVERRIDE`).
  - *Fix*: Format options in sentence case (`Optimize`, `Approve`, `Edit`, `Edit refused`, `Reject`, `Override`).

### 4. Icons in Decorative Circles & Random Numbered Markers
- **`src/pages/DataPage.tsx` (Lines 309, 325, 332)**:
  - *Tell*: Artificial numbered markers in circular outlines (`w-4 h-4 rounded-full border border-ink-3 flex items-center justify-center text-[10px] font-bold`).
  - *Fix*: Remove circular outlines. Represent state with quiet typographic numbering or done checkmarks.

### 5. Meta Strings Joined with Middle Dots
- **`src/pages/PlanPage.tsx` (Line 646)**:
  - *Tell*: Run ID and date separated by `<span>•</span>`.
  - *Fix*: Replace with comma or vertical line divider (`text-line`).
- **`src/pages/EvaluatePage.tsx` (Lines 207, 320)**:
  - *Tell*: Timestamp subtext joined by `• 420 cycle optimizations`; dot plot legend using `5 seeds • Mean tick mark`.
  - *Fix*: Replace with comma separation or spaced rules (`|`).
- **`src/components/plan/NetworkStrip.tsx` (Line 63)**:
  - *Tell*: Header summary `active lanes • total cartons`.
  - *Fix*: Replace with comma: `active lanes, total cartons`.
- **`src/components/plan/DispatchSlipDrawer.tsx` (Lines 142, 296)**:
  - *Tell*: Subtitle line joined with `•`; source candidate row using `carton • lead time`.
  - *Fix*: Replace with comma and ruled spacing.

### 6. Labels with "WORD - Fragment"
- **`src/pages/ReviewPage.tsx` (Lines 232-235)**:
  - *Tell*: Destination options formatted as `D1 - Kolkata`, `D2 - Ahmedabad`, etc.
  - *Fix*: Format as standard godown identifiers: `D1, Kolkata`, `D2, Ahmedabad`.
- **`src/components/plan/WhatIfBar.tsx` (Lines 80-81, 100-103)**:
  - *Tell*: Options formatted as `W1 - Gurgaon Godown`, `D1 - Kolkata Distributor`.
  - *Fix*: Format as `W1, Gurgaon Godown`, `D1, Kolkata Distributor`.

### 7. Title Case Instead of Sentence Case
- **`src/components/plan/DispatchSlipDrawer.tsx`**:
  - `Dispatched Cartons` -> `Dispatched cartons`
  - `Sources Considered` -> `Sources considered`
  - `Constraint Verifications` -> `Checks`
  - `Batch Stock Availability` -> `Batch stock availability`
  - `Lead Time Gap (Gmax)` -> `Lead time gap`
  - `Lane Load Capacity` -> `Lane load capacity`
  - `Acceptance Shelf Life` -> `Acceptance shelf life`
  - `Residual Destination Position` -> `What is still uncovered`
  - `Unmet Demand` -> `Unmet demand`
  - `Safety-Stock Gap` -> `Safety-stock gap`
- **`src/components/plan/WhatIfBar.tsx`**:
  - `Scenario What-If:` -> `Scenario what-if:`
  - `Warehouse Stock Adjustment` -> `Warehouse stock adjustment`
  - `Destination Demand Shift` -> `Destination demand shift`
  - `Unmet Demand Change` -> `Unmet demand change`
  - `Transport Cost Change` -> `Transport cost change`
- **`src/pages/EvaluatePage.tsx`**:
  - `Multi-Seed Distribution Dot Plots` -> `Multi-seed distribution dot plots`
  - `Benchmark Targets` -> `Benchmark targets`
  - `Where We Lose` -> `Where we lose`
  - `Demand Variant:` -> `Demand variant:`
  - `Standard Seasonal` -> `Standard seasonal`
  - `Heavy-Tailed Demand` -> `Heavy-tailed demand`
  - `Mid-Window Level Shift` -> `Mid-window level shift`
- **`src/pages/PlanPage.tsx`**:
  - `Unmet Demand & Binding Constraints` -> `Unmet demand and binding constraints`
  - `Unmet Cartons` -> `Unmet cartons`
  - `Safety-Stock Gap` -> `Safety-stock gap`
  - `Binding Constraint` -> `Binding constraint`
  - `Smallest Fix (Extra Transport)` -> `Smallest fix and extra transport`
- **`src/pages/ReviewPage.tsx`**:
  - `Pending Review` -> `Pending review`

### 8. Typography Scale Alignment
- **`src/pages/EvaluatePage.tsx`**:
  - *Missing Element*: Display figure (`40px` Source Serif 4). `DESIGN.md` reserves `40px` specifically for "only for one figure on Evaluate".
  - *Fix*: Add the primary fill-rate win metric in 40px Source Serif 4 at the top of the benchmark overview.

---

## Detailed Plan for Step 2 Redesign

| Screen | Core Transformation | Subject Anchoring |
|---|---|---|
| **AppShell** | Remove content shadows; change simulated stamp to sentence case; refine hairline ledger dividers. | Clean ledger margin and official synthetic data stamp. |
| **Data Screen** | Redesign first-run sequence as a ledger checklist without circular badges; refine CSV drop zone as a ruled document slot. | Inward physical goods register setup. |
| **Plan Screen** | Merge header, summary figures, and what-if controls into an integrated ledger band; eliminate rounded card wrappers around the dispatch register. | FMCG Godown Dispatch Register with subtotal ledger closing lines. |
| **Dispatch Slip** | Convert from card list to a ruled challan: crisp two-column check verification with icons, ruled sources considered, quiet carton stepper. | Official Physical Dispatch Slip / Challan. |
| **Review Screen** | Simplify metrics into a ruled ledger band; correct sentence case; godown label formats. | Dispatch approval ledger. |
| **Evaluate Screen** | Add 40px display serif figure; convert dot plots into quiet ledger gauge rules; sentence case section headings; eliminate middle dots. | Rigorous empirical benchmark audit. |
| **Audit Screen** | Sentence-case filters; tabular timestamps in Indian locale format; eliminate all-caps. | Permanent chronological decision ledger. |

---

## 9. Intentional Differences: Mockup vs. Production Dashboard

In accordance with Phase 3 instructions and the core engineering principle of **Data Honesty**, the following deliberate design decisions were implemented:

1. **No Month-Over-Month % Growth or Trend Arrows**:
   - *Mockup*: Included arbitrary "+12%", "+4%", or green percentage trend pills under KPI values.
   - *Production*: Removed entirely. There is no multi-year historical ledger to compute month-over-month delta honestly. Rule 1 strictly forbids fabricating numbers or using `Math.random()`. Real contextual captions (e.g., `"2 warehouses • 4 retailers"`, `"across all locations"`, `"category count"`) are displayed instead.
2. **Category Icon Tiles Instead of Product Photos**:
   - *Mockup*: Displayed generic pharmaceutical medicine photos and blister pack thumbnails.
   - *Production*: VyaparMitra serves Indian FMCG distribution networks (staples, beverages, packaged foods, personal care, home care). Instead of arbitrary stock photography, product cells feature crisp Lucide category icon tiles with distinct semantic colors (`Package`, `Coffee`, `ShoppingBag`, `Sparkles`, `Wheat`).
3. **WAPE Instead of MAPE**:
   - *Mockup*: Labeled accuracy as generic MAPE or simple accuracy.
   - *Production*: Uses WAPE (Weighted Absolute Percentage Error, $\frac{\sum |y - \hat{y}|}{\sum y}$) and Accuracy ($100 \times (1 - \text{WAPE})$) over the last 4 weeks. MAPE causes division-by-zero errors and distorts accuracy on zero-demand days common in regional retail FMCG.
4. **FMCG Product Names & Regional Indian Geography**:
   - *Mockup*: Displayed placeholder medicine titles (`Amoxicillin 500mg`, `Paracetamol`).
   - *Production*: Displays real FMCG products (`Chakki Fresh Atta 5kg`, `Refined Sunflower Oil 1L`, `Iodized Cooking Salt 1kg`, `Premium CTC Tea 250g`) flowing between regional distribution hubs (Gurgaon W1, Bhiwandi W2, Kolkata D1, Ahmedabad D2, Bengaluru S1, Pune S2).
5. **Survey of India Compliant GeoJSON Map**:
   - *Mockup*: World-atlas generic SVG map.
   - *Production*: Uses official Survey of India boundary GeoJSON (`src/data/india-boundary.json`) ensuring Kashmir, Ladakh, and Arunachal Pradesh are depicted in full accordance with the Government of India standard. Fully offline rendering via `d3-geo` with zero external map tile calls.

