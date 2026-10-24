# VyaparMitra Voice and Copy Guide

This guide establishes the copy and terminology rules for VyaparMitra. Follow these rules in all UI text, notifications, error messages, and documentation.

---

## 1. Core Principles

1. **Sentence Case Everywhere**  
   Use sentence case for page titles, headings, button labels, table columns, drawer sections, and error messages.  
   - *Correct*: `Generate plan`, `Transport cost`, `Unmet demand`, `Safety-stock gap`  
   - *Forbidden*: `GENERATE PLAN`, `Generate Plan`, `TRANSPORT COST`

2. **Plain Verbs & Active Voice**  
   Use direct, unadorned verbs that state exactly what action is performed.  
   - *Correct*: `Generate plan`, `Approve`, `Reject`, `Edit cartons`, `Clear filters`, `Download CSV`  
   - *Forbidden*: `Submit`, `Execute Optimization Run`, `Process Allocation`, `Click Here`

3. **Consistent Action Naming**  
   An action preserves its exact terminology from button to toast to audit trail:  
   - `Generate plan` -> Toast: `Plan generated` -> Audit: `Plan generated`  
   - `Approve` -> Toast: `Approved` -> Audit: `Approved`  
   - `Reject` -> Toast: `Rejected` -> Audit: `Rejected`  
   - `Edit cartons` -> Toast: `Cartons updated` (or if 409: `Edit refused`) -> Audit: `Edit cartons`

4. **Honest Errors Without Apology**  
   State what happened and the direct action to fix it. Never say "Sorry", "Oops", or "Something went wrong".  
   - *Correct*: `Warehouse W1 holds 90 cartons. This edit requests 95. Enter 90 or fewer.`  
   - *Correct*: `Cannot reach backend at 127.0.0.1:8000. Start the server and click Retry.`  
   - *Forbidden*: `Oops! An unexpected error occurred. We apologize for the inconvenience.`

5. **Empty States Invite Action**  
   Every empty state tells the user what is missing and provides the single button to create it.  
   - *Data empty*: `No data loaded. Load the sample data to start.` [Load sample data]  
   - *Plan empty*: `No plan yet. Generate one to see what moves where.` [Generate plan]  
   - *Issues empty*: `No data defects found. Data is ready for planning.`  
   - *Audit empty*: `No actions recorded yet.`

6. **Forbidden Patterns**  
   - No all-caps labels (`ALL CAPS`).  
   - No tracked-out eyebrow text above headings (`— OVERVIEW —`).  
   - No monospace for small labels.  
   - No meta strings joined with middle dots (`W1 · D2 · 20 Cartons`). Use commas or spaced rules.  
   - No labels like `WORD - fragment`.  
   - No arrow glyphs (`->`, `→`, `←`, `>>`) on buttons or links.  
   - No gradient washes or decorative blobs.  
   - No single accented word in a headline.  
   - No artificial numbering on non-sequential items.  
   - No marketing adjectives (`revolutionary`, `intelligent`, `cutting-edge`, `AI-powered`).

---

## 2. Standard Dictionary

| Entity / Concept | Standard Term | Avoid |
|---|---|---|
| Physical product package | `Carton` / `Cartons` | `Box`, `Case`, `Package` |
| Primary item quantity | `Units` | `Pieces`, `Items` |
| Shipping pathway | `Lane` | `Route`, `Channel` |
| Transit duration | `Lead time` | `Delivery days`, `Travel time` |
| Difference between lead times | `Lane gap` | `Lead time disparity` |
| Expiry constraint | `Shelf life` | `Perishability`, `Staleness` |
| Acceptance-life threshold | `Minimum acceptance life` ($E_{\text{short}}$) | `Dock threshold` |
| Primary shortfall | `Unmet demand` | `Stockout`, `Demand shortage` |
| Buffer shortfall | `Safety-stock gap` | `Buffer missing` |
| Master algorithm | `VyaparMitra` or `Method V` | `The AI Engine`, `Proprietary Model` |
| Baseline A | `Min/max rule` | `Rule A` |
| Baseline B | `Proportional split` | `Rule B` |
| Baseline C | `Forecast + greedy` | `Rule C` |
| Method O | `Oracle bound` | `Perfect Model` |
