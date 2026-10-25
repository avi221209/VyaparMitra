# VyaparMitra Production Dashboard & Project Cleanup — Implementation Plan

> **Goal:** Transform VyaparMitra into a simple, honest, production-quality regional FMCG distribution engine with a live dashboard backed by real API data, offline India network map, cleaned app shell, and zero demo scaffolding.

---

## 1. Scope & Architectural Boundaries

### Additions
- **Backend Router (`backend/app/routers/dashboard.py`)**:
  - `GET /api/v1/dashboard/summary?run_id=&horizon=`: Single-call aggregation returning KPIs, network graph with coordinates, top at-risk stock items, latest plan, walk-forward forecast chart data, and pending approvals.
  - `GET /api/v1/notifications`: Pending dispatches + attention items + critical data issues.
  - `GET /api/v1/search?q=`: Grouped search over products, locations, plan runs, and routes.
- **Backend Geo Service (`backend/app/services/geo.py`)**:
  - Static dictionary mapping Indian distribution nodes (Gurgaon, Bhiwandi, Kolkata, Ahmedabad, Bengaluru, Pune + fallbacks) to (lat, lon) coordinates without external API calls.
- **Backend Tests (`backend/tests/test_dashboard.py`)**:
  - Pure function status threshold boundaries (Critical < 0.5, Low Stock < 1.0, Healthy >= 1.0).
  - Division by zero safety.
  - Empty database graceful fallback (zeroes and empty lists, no 500 errors).
  - Idempotency & read-only verification (zero DB writes).
  - Notifications count and search grouping verification.
- **Bundled GeoJSON**:
  - Bundled Survey of India compliant India boundary GeoJSON (including Kashmir and Arunachal Pradesh) for offline SVG projection.
- **Frontend Dashboard (`src/pages/DashboardPage.tsx`)**:
  - Row 1: Time-aware greeting + Planning Period card with horizon editor trigger.
  - Row 2: 4 KPI Cards (Total Products, Active Locations, Total Inventory units, Items Needing Attention).
  - Row 3: Offline India Network Map (60%) with SVG pins/bezier flows + Stock Status table (40%) with category icons and status chips.
  - Row 4: Recent Distribution Plan card + Demand Forecast SVG line chart (W-4 to W+4) + Pending Approvals card with Approve/Reject inline actions and 8-second undo.
- **Frontend AppShell (`src/components/layout/AppShell.tsx`)**:
  - Top bar (72px): Leaf logo mark + Source Serif 4 title + "Smarter Distribution. Stronger Bharat." tagline + debounced search dropdown + notifications bell popover + profile chip with role selector + tasteful "Sample data" badge.
  - Mint-tinted sidebar (232px) with updated 6-item nav, "Need Help?" 5-step guide card, and responsive collapsing.
- **Production Artifacts**:
  - Multi-stage `Dockerfile` and `docker-compose.yml`.
  - GitHub Actions CI workflow (`.github/workflows/ci.yml`).

### Changes
- **Route Consolidation**:
  - Standardize all endpoints exclusively under `/api/v1/...`.
  - Update `src/lib/api.ts` and test suite to call `/api/v1/...`.
- **Sample Data Indicator**:
  - Replace rotated simulation stamp with clean top-bar "Sample data" badge active only when loaded data is the bundled sample.
- **CORS & Environment**:
  - Read `ALLOWED_ORIGINS` in `config.py` from environment.
- **Documentation**:
  - Rewrite `README.md` to remove hackathon references ("Triwizathon", "Team Stark", "PS2") and present clear production guide.
  - Update `docs/ASSUMPTIONS.md`, `docs/PROGRESS.md`, `docs/DESIGN.md`, `docs/MEASURED.md`.

### Deletions (Strictly Limited to Phase 4 Specification)
- **UI Components & Pages**:
  - `src/pages/LandingPage.tsx` and root route `/` assignment.
  - `src/pages/DesignSystemPage.tsx` and `/design` route.
  - Old `DemoGuideDrawer.tsx` content (replaced with 5-step operational guide).
  - Rotated "Simulated data" stamp component and banner styles.
  - "Load file with errors" and "Load low W1 stock" buttons on `/data`.
- **Demo Endpoints & Test Files**:
  - Endpoints `/demo/backup`, `/plan/load-backup`, `/data/seed`, `/simulator/seed`.
  - `backend/tests/test_demo_endpoints.py`.
- **Demo Assets & Scripts**:
  - `data/backup_demo_plan.json`.
  - `data/defect_manifest.json`.
  - `scratch/` directory.
  - `scripts/capture_screens.ps1`.
  - `scripts/measure_demo_timing.py`.
- **Superfluous Docs**:
  - `DEMO_CHECKLIST.md`, `DEMO_SCRIPT.md`, `VIDEO_SCRIPT.md`, `UX_REDESIGN_PROGRESS.md`, `UX_TESTS.md`, `COPY.md`.

---

## 2. Phase Execution Schedule

| Phase | Core Deliverable | Verification Gate |
|---|---|---|
| **Phase 0** | Baseline established, git safety verified, .env.example tracked | 69/69 pytest passed, repo clean |
| **Phase 1** | `/api/v1/dashboard/summary`, `/notifications`, `/search`, geo service, tests | `pytest backend/tests/test_dashboard.py` + full suite |
| **Phase 2** | App shell redesign (leaf logo, search, bell popover, profile, mint rail, 5-step guide) | `npm run build` + contrast script |
| **Phase 3** | `DashboardPage.tsx` with all 4 rows, SVG India map, charts, approvals, WCAG AA audit | Browser inspection (1440 & 390), contrast check, push |
| **Phase 4** | Clean demo code, deduplicate routes to `/api/v1`, prune files, update tests | Full pytest suite + frontend build |
| **Phase 5** | Dockerfile, compose, GitHub Actions, README rewrite, ASSUMPTIONS & MEASURED update | Full test pass, final commit & push |

---
