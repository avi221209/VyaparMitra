# VyaparMitra 2-Minute Backup Video Recording Script

**Triwizathon 2026 | Team Stark**  
*Problem Statement 2: Regional FMCG Distribution Intelligence and Inventory Optimization Engine*

---

## Technical Recording Setup
- **Resolution**: 1920x1080 (1080p, 60fps) or 1440x900 native.
- **Audio**: Clean voiceover, neutral pace, no background music.
- **Duration**: Exactly 120 seconds (2:00).
- **Tool**: OBS Studio, ScreenFlow, or QuickTime Screen Recording.

---

## Voiceover & Visual Choreography

### 0:00 – 0:15 | Introduction & Problem Context (15s)
* **Visual**: Open on browser at `http://localhost:5173/data`. Cursor rests quietly.
* **Voiceover**:
  > *"Every morning, regional Indian FMCG distributors face a high-stakes puzzle: how to fulfill demand across hundreds of retail stores and distributors while balancing warehouse stock, transit lead times, vehicle capacities, and strict shelf-life rules. This is VyaparMitra—a deterministic distribution intelligence desk engineered for physical operations."*

### 0:15 – 0:35 | Data Ingestion & "Fix First" Quality Gate (20s)
* **Visual**: Click **"Load file with errors"**. Table populates with ~20 injected FMCG data anomalies (duplicate SKUs, negative inventory, mixed units). Hover over madder **"Fix first"** badge. Click **"Exclude"** on one critical defect.
* **Voiceover**:
  > *"Real-world distributor data is messy. Here, VyaparMitra ingests dirty master files and immediately halts contaminated records with a 'Fix First' gate. Planning is strictly locked until critical defects are either corrected or explicitly excluded, guaranteeing clean inputs for optimization."*

### 0:35 – 0:65 | Two-Stage Optimization & The Ledger Register (30s)
* **Visual**: Click **"Load sample data"** to restore clean network. Navigate to `/plan`. Set Horizon to 7 days. Click **"Generate plan"**. Watch the 600ms SVG flow lines draw in and dispatches settle. Point cursor to the three summary figures (Transport Cost, Unmet Demand, Safety-Stock Gap).
* **Voiceover**:
  > *"Clicking 'Generate plan' solves a two-stage lexicographic integer program in under 2 seconds: first maximizing customer fulfillment, then minimizing freight cost and stranded expiring stock. Our interface draws from a physical ledger: ruled rows, right-aligned tabular figures, and a single summary band with transparent calculation popovers."*

### 0:65 – 0:90 | Dispatch Slip Drawer & Prescriptive Shortage Fixes (25s)
* **Visual**: Click row `W1 to D2`. The 480px Dispatch Slip Drawer slides in. Highlight *"Sources considered"*, *"Constraints checked"*, and the carton stepper. Scroll down to the madder-ruled **Unmet Demand Panel**. Show the smallest single fix.
* **Voiceover**:
  > *"Clicking any dispatch opens the Dispatch Slip drawer. Every recommendation is explained with pure arithmetic—sources considered, lead time gaps, and shelf-life constraints. When a shortage occurs, our counterfactual engine reports the exact binding bottleneck and the smallest single fix, such as adding 10 cartons at W1."*

### 0:90 – 1:10 | What-If Scenario Simulation & Rule Refusal (20s)
* **Visual**: In the What-If Bar, select `W1 Gurgaon Godown`, set percentage to `-20%`, click **"Regenerate"**. Change summary appears with before/after numbers written in plain words. Re-open drawer, enter 95 cartons when stock is 90, click Save. Red InlineMessage appears (HTTP 409).
* **Voiceover**:
  > *"Planners can simulate supply disruptions in real time. Scaling warehouse stock down recalculates the network in seconds, detailing impact in plain words. And physical rules are inviolable: attempting to overdraw warehouse inventory triggers an HTTP 409 refusal, permanently logged to our immutable audit trail."*

### 1:10 – 1:20 | Walk-Forward Replay & Honest Evaluation (10s)
* **Visual**: Click **Evaluate** in the left rail. Hand-built SVG dot plots across 5 seeds render. Highlight the *"Where We Lose"* section.
* **Voiceover**:
  > *"Finally, we validate VyaparMitra against min/max, proportional split, and greedy baselines over a 28-day walk-forward replay. We report wins and losses with equal visual weight, proving performance with empirical evidence."*
