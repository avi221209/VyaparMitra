# VyaparMitra Walk-Forward Benchmark Evaluation Results

**Pre-Registered Benchmark Protocol**:
- 5 independent random seeds (`[1, 2, 3, 4, 5]`)
- 4 weekly planning cycles (28 calendar days walk-forward)
- 3 inventory availability scenarios (`scarce` 0.8x, `balanced` 1.0x, `abundant` 1.3x)
- 7 allocation methods:
  - **A** (Min/Max Nearest Source Heuristic)
  - **B** (Proportional Sales Split)
  - **C** (Forecast + Greedy Urgency-First Dispatch)
  - **V** (VyaparMitra Two-Stage Lexicographic MILP)
  - **V-SS** (VyaparMitra Ablation: Safety Stock = 0)
  - **V-SL** (VyaparMitra Ablation: No Shelf-Life Feasibility Rules)
  - **O** (Oracle Bound: Perfect Future Information, no safety stock)

---

## 1. Evaluation Summary by Scenario

### Scenario 1: Scarce Supply (Stock Multiplier: 0.8×)
* **Headroom Gap (Oracle Fill Rate − Baseline A Fill Rate)**: **+7.83 percentage points** (Sufficient Headroom)
* **Seeds Won vs Baseline A**: **5 of 5 seeds** (100% win rate)
* **Overall Target Status**: **FAIL** (Missed fill rate target margin vs Method C; passed all other 6 targets)

#### Performance Metrics Table (Mean ± Std across 5 seeds)

| Method | Fill Rate (%) | Unmet Units | Expiry Waste (%) | Cost-to-Serve (₹) | Freight / Unit (₹) |
|---|---|---|---|---|---|
| **A (Min/Max)** | 88.73% ± 0.59 | 1,08,106 | 6.90% | ₹ 1,17,00,450 | ₹ 1.49 |
| **B (Prop Split)** | 87.80% ± 0.54 | 1,16,866 | 10.69% | ₹ 1,69,12,697 | ₹ 2.39 |
| **C (Greedy)** | 91.75% ± 0.93 | 78,879 | 1.43% | ₹ 49,78,529 | ₹ 1.59 |
| **V (VyaparMitra)** | **92.37% ± 0.89** | **72,800** | **1.43%** | **₹ 47,19,911** | **₹ 1.46** |
| **V-SS (No SS)** | 85.69% ± 1.86 | 1,37,367 | 2.27% | ₹ 69,79,939 | ₹ 1.23 |
| **V-SL (No Shelf-Life)** | 88.65% ± 1.33 | 1,08,532 | 5.16% | ₹ 97,96,798 | ₹ 1.54 |
| **O (Oracle Bound)** | 96.56% ± 0.42 | 32,591 | 2.30% | ₹ 47,18,414 | ₹ 1.44 |

#### Pre-Registered Target Checks

| Target Metric | Registered Condition | Measured Result | Status | Diagnosed Cause |
|---|---|---|---|---|
| **Fill Rate** | $\ge +3.0\text{ pts vs A}$ and $\ge +1.0\text{ pt vs C}$ | +3.64 pts vs A, +0.62 pts vs C | **FAIL** | Headroom constrained by tight warehouse stock; greedy dispatch C already achieves strong local prioritization. |
| **Unmet Units** | $< \text{A, B, and C}$ | 72,800 vs 78,879 (C) | **PASS** | Two-stage MILP optimal multi-commodity network flow minimizes total demand shortage. |
| **Freight / Unit** | $\le 105\%\text{ of Baseline A}$ | ₹ 1.46 vs ₹ 1.49 (98.0%) | **PASS** | Stage 2 cost optimization finds cheapest eligible lanes within optimal service envelope. |
| **Expiry Waste** | $\le 80\%\text{ of A and } \le \text{C}$ | 1.43% vs 6.90% (A) and 1.43% (C) | **PASS** | Cumulative FEFO sell-through caps prevent over-allocating short-dated batches. |
| **Cost-to-Serve** | $< \text{A, B, and C}$ | ₹ 47.20L vs ₹ 49.79L (C) | **PASS** | Integrated reduction in penalty, freight, and stranded inventory costs. |
| **Forecast WAPE** | $\ge 10\%\text{ below seasonal-naive}$ | 8.4% vs 14.2% | **PASS** | Rolling cross-validation model selection with de-seasonalized level smoothing. |
| **Forecast Bias** | $\|\text{Bias}\| \le 0.05\text{ (5\%)}$ | +1.2% | **PASS** | Unbiased rolling estimation across demand horizons. |

---

### Scenario 2: Balanced Supply (Stock Multiplier: 1.0×)
* **Headroom Gap (Oracle Fill Rate − Baseline A Fill Rate)**: **+9.66 percentage points** (Sufficient Headroom)
* **Seeds Won vs Baseline A**: **5 of 5 seeds** (100% win rate)
* **Overall Target Status**: **FAIL** (Missed fill rate target margin vs Method C; passed all other 6 targets)

#### Performance Metrics Table (Mean ± Std across 5 seeds)

| Method | Fill Rate (%) | Unmet Units | Expiry Waste (%) | Cost-to-Serve (₹) | Freight / Unit (₹) |
|---|---|---|---|---|---|
| **A (Min/Max)** | 88.37% ± 0.61 | 1,11,640 | 7.25% | ₹ 1,35,76,604 | ₹ 1.56 |
| **B (Prop Split)** | 92.83% ± 0.43 | 68,793 | 11.48% | ₹ 1,92,06,018 | ₹ 2.83 |
| **C (Greedy)** | 92.97% ± 1.02 | 67,023 | 1.71% | ₹ 53,85,634 | ₹ 1.66 |
| **V (VyaparMitra)** | **93.02% ± 1.00** | **66,510** | **1.71%** | **₹ 52,28,428** | **₹ 1.50** |
| **V-SS (No SS)** | 85.89% ± 1.85 | 1,35,449 | 2.46% | ₹ 75,74,858 | ₹ 1.20 |
| **V-SL (No Shelf-Life)** | 86.56% ± 1.29 | 1,28,403 | 6.07% | ₹ 1,23,77,496 | ₹ 1.51 |
| **O (Oracle Bound)** | 98.03% ± 0.48 | 18,473 | 2.50% | ₹ 51,27,155 | ₹ 1.51 |

#### Pre-Registered Target Checks

| Target Metric | Registered Condition | Measured Result | Status | Diagnosed Cause |
|---|---|---|---|---|
| **Fill Rate** | $\ge +3.0\text{ pts vs A}$ and $\ge +1.0\text{ pt vs C}$ | +4.65 pts vs A, +0.05 pts vs C | **FAIL** | In balanced inventory, greedy heuristic C captures most available demand; V wins on cost-to-serve and freight rather than pure fill rate volume. |
| **Unmet Units** | $< \text{A, B, and C}$ | 66,510 vs 67,023 (C) | **PASS** | Two-stage optimization finds globally optimal fulfillment. |
| **Freight / Unit** | $\le 105\%\text{ of Baseline A}$ | ₹ 1.50 vs ₹ 1.56 (96.2%) | **PASS** | Multi-lane cost balancing. |
| **Expiry Waste** | $\le 80\%\text{ of A and } \le \text{C}$ | 1.71% vs 7.25% (A) | **PASS** | Strict FEFO dispatch caps prevent over-allocation of short-dated batches. |
| **Cost-to-Serve** | $< \text{A, B, and C}$ | ₹ 52.28L vs ₹ 53.86L (C) | **PASS** | Lower unit freight and penalty costs. |
| **Forecast WAPE** | $\ge 10\%\text{ below seasonal-naive}$ | 8.4% vs 14.2% | **PASS** | Maintained across balanced cycles. |
| **Forecast Bias** | $\|\text{Bias}\| \le 0.05\text{ (5\%)}$ | +1.2% | **PASS** | Stable error balance. |

---

### Scenario 3: Abundant Supply (Stock Multiplier: 1.3×)
* **Headroom Gap (Oracle Fill Rate − Baseline A Fill Rate)**: **+11.67 percentage points** (Sufficient Headroom)
* **Seeds Won vs Baseline A**: **5 of 5 seeds** (100% win rate)
* **Status**: **REPORTED_ONLY** (Pre-registered rule: under abundance, proportional split B matches demand; engine reported for complete transparency)

#### Performance Metrics Table (Mean ± Std across 5 seeds)

| Method | Fill Rate (%) | Unmet Units | Expiry Waste (%) | Cost-to-Serve (₹) | Freight / Unit (₹) |
|---|---|---|---|---|---|
| **A (Min/Max)** | 86.38% ± 0.77 | 1,30,708 | 7.53% | ₹ 1,64,97,527 | ₹ 1.62 |
| **B (Prop Split)** | 97.52% ± 0.18 | 23,791 | 12.33% | ₹ 2,33,20,794 | ₹ 3.50 |
| **C (Greedy)** | 92.95% ± 1.02 | 67,191 | 2.03% | ₹ 63,67,398 | ₹ 1.67 |
| **V (VyaparMitra)** | **93.02% ± 1.01** | **66,510** | **2.03%** | **₹ 61,92,164** | **₹ 1.49** |
| **V-SS (No SS)** | 85.82% ± 1.86 | 1,36,120 | 2.67% | ₹ 86,03,237 | ₹ 1.21 |
| **V-SL (No Shelf-Life)** | 86.24% ± 0.52 | 1,31,500 | 5.65% | ₹ 1,34,72,461 | ₹ 1.50 |
| **O (Oracle Bound)** | 98.05% ± 0.49 | 18,331 | 2.71% | ₹ 61,31,164 | ₹ 1.50 |

*Note: While Baseline B achieves 97.52% fill rate in Abundant supply by flooding inventory, it incurs massive waste (12.33% vs V's 2.03%) and exorbitant freight (₹ 3.50/unit vs V's ₹ 1.49/unit), driving cost-to-serve to ₹ 2.33 Cr (nearly 4x VyaparMitra's ₹ 61.9 Lakhs).*

---

## 2. Key Ablation Findings

1. **Safety Stock Buffering (`V` vs `V-SS`)**:
   - Removing safety stock ($SS = 0$) drops fill rate by **7.13 percentage points** (93.02% $\rightarrow$ 85.89% in balanced).
   - Unmet units double from 66,510 to 1,35,449 cartons.
   - Proves that dynamic safety stock ($z \sigma \sqrt{P}$) is critical to absorb intraday variance and transport lead-time volatility.

2. **Shelf-Life Feasibility & FEFO Caps (`V` vs `V-SL`)**:
   - Disabling shelf-life acceptance rules causes expiry waste to spike by **355%** (from 1.71% to 6.07% in balanced).
   - Cost-to-serve more than doubles from ₹ 52.28 Lakhs to ₹ 1.24 Crores due to expired carton penalties at retail.
   - Proves that cumulative FEFO sell-through caps prevent costly channel dumping.
