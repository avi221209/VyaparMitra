# VyaparMitra Design System Specification

**Regional FMCG Distribution Intelligence & Planning Ledger**

---

## 1. Subject & Aesthetic Idea

The product represents the planning desk of a regional Indian FMCG distributor: godown registers, dispatch slips, physical receipt ledgers.  
It borrows the quiet clarity and rigor of a well-kept commercial ledger:
- **Ruled Rows**: Fine lines separating entries rather than floating containers.
- **Tabular Figures**: Every numeric quantity (`cartons`, `rupees`, `days`, `percentages`) is right-aligned with `tabular-nums`.
- **Calm Color**: Low-saturation surfaces and disciplined inks.
- **Boldness in One Place**: The **Dispatch Slip** right-side drawer (the signature ledger card) and the **Network Strip** flow diagram. Everything else remains calm, quiet, and disciplined.

---

## 2. Color Tokens

All colors are stored as CSS custom properties in `src/styles/tokens.css` and mapped to Tailwind configuration in `tailwind.config.ts`. Components use semantic tokens only—never raw hexadecimal literals.

| Token | Hex Value | Role / Usage | Contrast Ratio (WCAG) |
|---|---|---|---|
| `paper` | `#F5F6F4` | Base page background | 15.2:1 against ink |
| `surface` | `#FFFFFF` | Cards, registers, drawers, modals | 16.5:1 against ink |
| `ink` | `#16202A` | Primary text, titles, numbers | 16.5:1 on surface |
| `ink-2` | `#4A5663` | Secondary labels, descriptions | 7.5:1 on surface |
| `ink-3` | `#667381` | Smallest metadata only on surface | 4.85:1 on surface |
| `line` | `#DDE2E7` | Table row rules, dividers | Decorative |
| `line-strong`| `#7E8E9E` | UI control borders, input outlines | 3.36:1 on surface (passes 3:1) |
| `brand` | `#0F5C4D` | Actions, focus rings, primary highlights | 7.9:1 on surface |
| `brand-wash`| `#E4F0EC` | Active row tints, badge backgrounds | 6.76:1 with brand |
| `turmeric` | `#B37400` | Attention, flags, simulated data stamp | 3.88:1 on surface (passes 3:1) |
| `turmeric-wash`| `#FBF0D7` | Attention badge background | 14.56:1 with ink |
| `madder` | `#A3344F` | Shortfalls, unmet demand, critical errors | 6.64:1 on surface |
| `madder-wash`| `#F7E4E9` | Error badge & alert background | 5.45:1 with madder |
| `ok` | `#2E7D4F` | Full fulfillment, passed checks | 5.05:1 on surface |

*Contrast Validation*: Validated automatically by `scripts/contrast.mjs` on every build. All text meets WCAG AA (4.5:1), and all interactive borders/stamps meet 3.0:1.

---

## 3. Typography

All fonts are self-hosted via `@fontsource-variable` to ensure 100% offline functionality.

- **UI & Controls**: `Public Sans Variable` (`@fontsource-variable/public-sans`)
- **Titles & Headline Figures**: `Source Serif 4 Variable` (`@fontsource-variable/source-serif-4`)

### Type Scale

| Element | Font | Size | Line Height | Tracking | Usage |
|---|---|---|---|---|---|
| Display | Source Serif 4 | 40px | 1.15 | Tight | Single headline metric on Evaluate |
| Page Title | Source Serif 4 | 28px | 1.25 | Tight | Page header |
| Section Title| Source Serif 4 | 20px | 1.25 | Normal | Register & panel headings |
| Large Body | Public Sans | 16px | 1.5 | Normal | Modal headers, highlighted copy |
| Body & Table| Public Sans | 14px | 1.5 | Normal | Main table rows, inputs, descriptions |
| Table Meta | Public Sans | 12px / 13px | 16px / 18px | Normal | Row subtext, timestamps, chips |

- **Tabular Figures**: `font-variant-numeric: tabular-nums;` enforced globally on all numbers.
- **Line Length**: Max 72 characters (`max-w-[72ch]`).

---

## 4. Forbidden Design Elements

The following patterns are strictly prohibited across the entire product:
1. **No all-caps labels** (e.g. `STATUS`, `ACTIONS`). Use sentence case (`Status`, `Actions`).
2. **No tracked-out eyebrow text** above headings (e.g. `— DISTRIBUTION PLAN —`).
3. **No monospace font** for small labels.
4. **No meta strings joined with middle dots** (`·`). Use commas or spaced rules.
5. **No labels like "WORD - fragment"**.
6. **No arrow glyphs** on buttons or links (`->`, `→`, `>>`). Use clear verbs or Lucide icons.
7. **No gradient washes or decorative blobs**.
8. **No single accented word** in a headline.
9. **No numbered markers** on non-sequential content.
10. **No marketing adjectives** or apologetic copy.

---

## 5. Shape, Spacing & Depth

- **Border Radii**:
  - `2px` (`rounded-chip`): Table cells, status badges, simulated stamp.
  - `6px` (`rounded-control`): Buttons, inputs, form selects, inline messages.
  - `12px` (`rounded-overlay`): Drawers, modals, menus.
- **Shadows**:
  - Content has **zero box-shadow**. Content is delineated by spacing and fine rules (`line`).
  - Overlay shadow: `0 12px 32px rgba(22, 32, 42, 0.14)`.
- **Spacing Scale**: 4px base (4, 8, 12, 16, 24, 32, 48, 64px).
  - Page Max Width: `1360px`.
  - Desktop Padding: `32px` (`p-8`).
  - Mobile Padding: `16px` (`p-4`).
- **Table Row Density**:
  - Comfortable: `44px` height.
  - Compact: `36px` height.
  - Remembered across visits via `localStorage`.

---

## 6. App Shell Layout

- **Left Rail (232px)**:
  - Collapses to icons only below `1100px`.
  - Transforms into fixed bottom bar below `720px`.
  - Wordmark: "VyaparMitra" in Source Serif 4.
  - Navigation items: `Data`, `Plan`, `Review`, `Evaluate`, `Audit`.
  - State marks: Real status indicator per item (e.g. Done tick, `Loaded`, `Active`, `Cached`), never raw digit counts.
- **Top Bar**:
  - Page title left (Serif 28px).
  - Right: Dataset name (`FMCG Network`), "Simulated data" stamp (turmeric border, 2px radius, rotated -1.5°), and quiet role select (`Planner`, `Warehouse`, `Reviewer`) sent as `X-Role`.
- **Unreachable Backend Banner**:
  - Appears across top if backend `/api/health` fails.
  - Active retry button with spinner.

---

## 7. Component Kit (`src/components/ui`)

1. `Button`: Primary, secondary, quiet, danger. Immediate 100ms feedback, loading spinner, disabled state.
2. `Field`: Label, required indicator, hint, error text.
3. `Input`: Tabular-nums on numeric, 6px radius, brand focus ring.
4. `Select`: Native styled select matching input styling.
5. `DataTable`: Sticky header, sticky first column, right-aligned numbers, hover tint, keyboard focus, density toggle, skeleton loader.
6. `Badge`: Always icon + text, never color alone.
7. `Drawer`: Right 480px, 180ms slide, 12px radius, backdrop, escape handler.
8. `Modal`: Centered dialog, 12px radius, shadow overlay.
9. `Toast`: Accessible alert with 8s "Undo" support.
10. `Tooltip`: Radix tooltip for role gating and explanations.
11. `Tabs`: Underline tab list with active brand indicator.
12. `Stat`: Serif figure with plain label.
13. `InlineMessage`: Severity icon + direct sentence, no apologies.
14. `EmptyState`: Plain explanation + direct action button.
15. `Skeleton`: Table-shaped layout placeholders.
16. `Formatters`: `formatINR`, `formatCartons`, `formatDate`, `formatDays`.

---

## 8. Dev-Only Specification Route

A dedicated route `/design` renders live token swatches, typography hierarchy, and every component state.
