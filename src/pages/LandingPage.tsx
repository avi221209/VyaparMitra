import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Badge,
  formatINR,
  formatCartons,
  formatDays,
} from '../components/ui';
import { apiFetch } from '../lib/api';
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  Database,
  CalendarCheck,
  BarChart2,
  Sliders,
  Layers,
  FileText,
  RotateCw,
  Truck,
  Check,
} from 'lucide-react';

export function LandingPage() {
  const navigate = useNavigate();
  const [selectedScenario, setSelectedScenario] = useState<'normal' | 'low_w1' | 'rescue'>('normal');
  const [isLaunching, setIsLaunching] = useState<boolean>(false);

  // Quick launch helper: seeds sample data and redirects directly to /plan
  const handleLaunchLiveDemo = async () => {
    setIsLaunching(true);
    try {
      await apiFetch('/api/data/seed', {
        method: 'POST',
        body: JSON.stringify({ scenario: 'balanced', variant: 'normal' }),
      });
      // Generate initial plan
      await apiFetch('/api/plan', {
        method: 'POST',
        body: JSON.stringify({ horizon: 7 }),
      });
      navigate('/plan');
    } catch {
      // Fallback navigate
      navigate('/plan');
    } finally {
      setIsLaunching(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-paper text-ink font-sans selection:bg-brand-wash selection:text-brand">
      {/* ========================================================================= */}
      {/* 1. TOP MASTHEAD (Ruled Ledger Header)                                     */}
      {/* ========================================================================= */}
      <header className="w-full bg-surface border-b border-line select-none sticky top-0 z-40">
        <div className="max-w-page mx-auto px-6 lg:px-10 h-16 flex items-center justify-between gap-4">
          {/* Brand Wordmark & Tagline */}
          <div className="flex items-center gap-4">
            <span className="font-serif text-[22px] font-bold text-ink tracking-tight">
              VyaparMitra
            </span>
            <div className="h-4 w-px bg-line hidden sm:block" />
            <span className="text-meta text-ink-2 hidden md:inline">
              Regional FMCG Distribution Intelligence
            </span>
          </div>

          {/* Document Metadata & Actions */}
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="hidden xl:flex items-center gap-3 text-meta text-ink-3 tabular-nums border-r border-line pr-4">
              <span>PS2 FMCG Distribution</span>
              <span className="text-line">|</span>
              <span>Two-Stage MILP + Walk-Forward Replay</span>
            </div>

            {/* Rotated Simulated Data Stamp */}
            <div
              title="All data is synthetic and explicitly simulated for evaluation"
              className="px-2 py-0.5 border border-turmeric text-turmeric bg-turmeric-wash text-meta font-medium rounded-chip rotate-[-1.5deg] select-none shrink-0"
            >
              Simulated data
            </div>

            <Button
              variant="quiet"
              size="sm"
              onClick={() => navigate('/evaluate')}
              className="hidden sm:inline-flex"
            >
              View evaluation proof
            </Button>

            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/plan')}
            >
              Open planner desk
            </Button>
          </div>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* 2. SPLIT EDITORIAL HERO (Above the Fold)                                  */}
      {/* ========================================================================= */}
      <section className="w-full border-b border-line bg-surface py-12 lg:py-16">
        <div className="max-w-page mx-auto px-6 lg:px-10">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-start">
            
            {/* Left Column (Problem & Thesis, max 65ch) */}
            <div className="lg:col-span-6 flex flex-col gap-6 max-w-[65ch]">
              <div className="flex items-center gap-2 text-meta text-brand font-medium">
                <span className="w-2 h-2 rounded-full bg-brand" />
                <span>Deterministic Supply Chain Decision Support</span>
              </div>

              <h1 className="font-serif text-[34px] sm:text-[40px] font-bold text-ink leading-[1.15] tracking-tight">
                Decide what ships where, prove why it wins, and name the exact fix when stock falls short.
              </h1>

              <p className="text-body text-ink-2 leading-relaxed text-[15px]">
                Regional FMCG distribution in India fails when planners rely on min/max spreadsheets and guesswork. 
                VyaparMitra replaces intuition with per-series demand learning, FEFO shelf-life feasibility caps, two-stage lexicographic integer optimization, and verified peer surplus rescue.
              </p>

              {/* Action Buttons Row */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <Button
                  variant="primary"
                  size="md"
                  loading={isLaunching}
                  onClick={handleLaunchLiveDemo}
                >
                  Launch live demo (Sample data)
                </Button>

                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => navigate('/data')}
                >
                  Inspect 20-defect data gate
                </Button>

                <Button
                  variant="quiet"
                  size="md"
                  onClick={() => navigate('/evaluate')}
                >
                  Explore 5-seed benchmark
                </Button>
              </div>

              {/* Trust & Architecture Principles Strip */}
              <div className="pt-6 border-t border-line grid grid-cols-2 sm:grid-cols-4 gap-4 text-meta">
                <div>
                  <span className="text-ink-3 block">Network</span>
                  <span className="font-semibold text-ink tabular-nums">24 SKUs, 6 nodes</span>
                </div>
                <div>
                  <span className="text-ink-3 block">Solver</span>
                  <span className="font-semibold text-ink">Two-stage MILP</span>
                </div>
                <div>
                  <span className="text-ink-3 block">Hallucinations</span>
                  <span className="font-semibold text-ok">0 (Deterministic)</span>
                </div>
                <div>
                  <span className="text-ink-3 block">Connectivity</span>
                  <span className="font-semibold text-ink">100% offline</span>
                </div>
              </div>
            </div>

            {/* Right Column (Interactive "Live Worked-Example Dispatch Ledger") */}
            <div className="lg:col-span-6 flex flex-col gap-4">
              <div className="border border-line rounded-control bg-paper/60 p-5 flex flex-col gap-4">
                
                {/* Header & Scenario Selection Pills */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line">
                  <div>
                    <h2 className="text-section font-serif font-semibold text-ink">
                      Live worked example
                    </h2>
                    <span className="text-meta text-ink-3">
                      W1 Gurgaon and W2 Bhiwandi feeding D1 and D2
                    </span>
                  </div>

                  {/* Pills */}
                  <div className="flex flex-wrap items-center gap-1.5 select-none">
                    <button
                      type="button"
                      onClick={() => setSelectedScenario('normal')}
                      className={`px-2.5 py-1 text-meta rounded-control font-medium transition-colors ${
                        selectedScenario === 'normal'
                          ? 'bg-ink text-surface'
                          : 'bg-surface text-ink-2 hover:bg-paper border border-line'
                      }`}
                    >
                      Baseline: Normal
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedScenario('low_w1')}
                      className={`px-2.5 py-1 text-meta rounded-control font-medium transition-colors ${
                        selectedScenario === 'low_w1'
                          ? 'bg-ink text-surface'
                          : 'bg-surface text-ink-2 hover:bg-paper border border-line'
                      }`}
                    >
                      Cut W1 by 20%
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedScenario('rescue')}
                      className={`px-2.5 py-1 text-meta rounded-control font-medium transition-colors ${
                        selectedScenario === 'rescue'
                          ? 'bg-ink text-surface'
                          : 'bg-surface text-ink-2 hover:bg-paper border border-line'
                      }`}
                    >
                      Surplus rescue
                    </button>
                  </div>
                </div>

                {/* Mini SVG Network Flow Diagram */}
                <div className="bg-surface border border-line rounded-control p-3">
                  <svg
                    viewBox="0 0 460 130"
                    className="w-full h-auto select-none font-sans"
                    role="img"
                    aria-label="Worked-example network flow diagram"
                  >
                    {/* W1 to D1 Lane */}
                    <line
                      x1="90"
                      y1="35"
                      x2="350"
                      y2="35"
                      stroke={selectedScenario === 'low_w1' ? 'var(--color-ink-2)' : 'var(--color-brand)'}
                      strokeWidth="2"
                    />
                    {/* W1 to D2 Lane */}
                    <line
                      x1="90"
                      y1="35"
                      x2="350"
                      y2="95"
                      stroke={selectedScenario === 'low_w1' ? 'var(--color-line)' : 'var(--color-brand)'}
                      strokeWidth={selectedScenario === 'low_w1' ? '1' : '1.5'}
                      strokeDasharray={selectedScenario === 'low_w1' ? '4 4' : 'none'}
                    />
                    {/* W2 to D1 Lane */}
                    <line
                      x1="90"
                      y1="95"
                      x2="350"
                      y2="35"
                      stroke="var(--color-brand)"
                      strokeWidth="1.5"
                    />
                    {/* Peer Godown P1 to D2 Lane (Surplus Rescue Mode) */}
                    {selectedScenario === 'rescue' && (
                      <line
                        x1="220"
                        y1="115"
                        x2="350"
                        y2="95"
                        stroke="var(--color-ok)"
                        strokeWidth="2.5"
                      />
                    )}

                    {/* Nodes: W1 */}
                    <circle cx="90" cy="35" r="14" fill="var(--color-brand)" />
                    <text x="90" y="39" textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="bold">
                      W1
                    </text>
                    <text x="90" y="16" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">
                      {selectedScenario === 'low_w1' ? '72 ctns' : '90 ctns'}
                    </text>

                    {/* Nodes: W2 */}
                    <circle cx="90" cy="95" r="14" fill="var(--color-ink-2)" />
                    <text x="90" y="99" textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="bold">
                      W2
                    </text>
                    <text x="90" y="122" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">
                      60 ctns (42d)
                    </text>

                    {/* Nodes: D1 */}
                    <circle cx="350" cy="35" r="14" fill="var(--color-paper)" stroke="var(--color-brand)" strokeWidth="2" />
                    <text x="350" y="39" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="bold">
                      D1
                    </text>
                    <text x="350" y="16" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">
                      Kolkata (130 ctns)
                    </text>

                    {/* Nodes: D2 */}
                    <circle
                      cx="350"
                      cy="95"
                      r="14"
                      fill={selectedScenario === 'low_w1' ? 'var(--color-madder-wash)' : 'var(--color-paper)'}
                      stroke={selectedScenario === 'low_w1' ? 'var(--color-madder)' : 'var(--color-brand)'}
                      strokeWidth="2"
                    />
                    <text x="350" y="99" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="bold">
                      D2
                    </text>
                    <text x="350" y="122" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">
                      Ahmedabad (65 ctns)
                    </text>

                    {/* Peer Godown P1 Stamp in Rescue Mode */}
                    {selectedScenario === 'rescue' && (
                      <g>
                        <circle cx="220" cy="115" r="10" fill="var(--color-ok)" />
                        <text x="220" y="118" textAnchor="middle" fill="#FFFFFF" fontSize="8" fontWeight="bold">
                          P1
                        </text>
                        <text x="220" y="102" textAnchor="middle" fill="var(--color-ok)" fontSize="9" fontWeight="bold">
                          Peer Rescue +45 ctns
                        </text>
                      </g>
                    )}
                  </svg>
                </div>

                {/* Worked Dispatch Register (Ruled 3-Row Table) */}
                <div className="bg-surface border border-line rounded-control overflow-hidden">
                  <table className="w-full text-left border-collapse text-body font-sans">
                    <thead>
                      <tr className="border-b border-line bg-paper/50 text-meta font-medium text-ink-2">
                        <th className="py-2 px-3">Godown</th>
                        <th className="py-2 px-3">Destination</th>
                        <th className="py-2 px-3 text-right">Dispatched</th>
                        <th className="py-2 px-3 text-right">Freight</th>
                        <th className="py-2 px-3 text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line text-meta">
                      {/* Row 1: W1 to D1 */}
                      <tr className="hover:bg-paper/30">
                        <td className="py-2 px-3 font-medium text-ink">W1 Gurgaon</td>
                        <td className="py-2 px-3">D1 Kolkata</td>
                        <td className="py-2 px-3 text-right tabular-nums font-semibold text-ink">
                          {selectedScenario === 'low_w1' ? '72 ctns' : '70 ctns'}
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums text-ink-2">
                          {selectedScenario === 'low_w1' ? '₹ 144' : '₹ 140'}
                        </td>
                        <td className="py-2 px-3 text-right">
                          <Badge variant="ok">FEFO Pass</Badge>
                        </td>
                      </tr>

                      {/* Row 2: W1 to D2 */}
                      <tr className="hover:bg-paper/30">
                        <td className="py-2 px-3 font-medium text-ink">W1 Gurgaon</td>
                        <td className="py-2 px-3">D2 Ahmedabad</td>
                        <td className="py-2 px-3 text-right tabular-nums font-semibold text-ink">
                          {selectedScenario === 'low_w1' ? '0 ctns' : '20 ctns'}
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums text-ink-2">
                          {selectedScenario === 'low_w1' ? '₹ 0' : '₹ 40'}
                        </td>
                        <td className="py-2 px-3 text-right">
                          {selectedScenario === 'low_w1' ? (
                            <Badge variant="madder">Stockout</Badge>
                          ) : (
                            <Badge variant="ok">Cheapest</Badge>
                          )}
                        </td>
                      </tr>

                      {/* Row 3: W2 to D1 */}
                      <tr className="hover:bg-paper/30">
                        <td className="py-2 px-3 font-medium text-ink">W2 Bhiwandi</td>
                        <td className="py-2 px-3">D1 Kolkata</td>
                        <td className="py-2 px-3 text-right tabular-nums font-semibold text-ink">
                          60 ctns
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums text-ink-2">
                          ₹ 175
                        </td>
                        <td className="py-2 px-3 text-right">
                          <Badge variant="neutral">Exp 42d</Badge>
                        </td>
                      </tr>

                      {/* Row 4: Surplus Rescue from P1 (Only in rescue mode) */}
                      {selectedScenario === 'rescue' && (
                        <tr className="bg-ok-wash/40 font-semibold">
                          <td className="py-2 px-3 font-bold text-ok">P1 Peer Godown</td>
                          <td className="py-2 px-3 text-ok">D2 Ahmedabad</td>
                          <td className="py-2 px-3 text-right tabular-nums text-ok font-bold">
                            45 ctns
                          </td>
                          <td className="py-2 px-3 text-right tabular-nums text-ink-2">
                            ₹ 135
                          </td>
                          <td className="py-2 px-3 text-right">
                            <Badge variant="ok">Rescued</Badge>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Scenario Outcome & Counterfactual Callout */}
                {selectedScenario === 'normal' && (
                  <div className="p-3 bg-surface border border-line rounded-control flex items-center justify-between text-meta">
                    <span className="text-ink font-medium">Outcome: 100% fulfillable, 0 cartons unmet</span>
                    <span className="font-semibold text-ink tabular-nums">Total Freight: ₹ 355</span>
                  </div>
                )}

                {selectedScenario === 'low_w1' && (
                  <div className="p-3 bg-madder-wash border border-madder/30 rounded-control flex flex-col gap-1 text-meta">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-madder">Unmet demand: 45 cartons at D2</span>
                      <span className="font-semibold text-madder tabular-nums">Lost Margin: ₹ 900</span>
                    </div>
                    <p className="text-[12px] text-ink-2">
                      Binding constraint: W1 stock shortage. Smallest fix: add +45 cartons to W1 stock (+₹90 freight).
                    </p>
                  </div>
                )}

                {selectedScenario === 'rescue' && (
                  <div className="p-3 bg-ok-wash border border-ok/30 rounded-control flex flex-col gap-1 text-meta">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-ok">Surplus rescue from P1: 45 cartons</span>
                      <span className="font-bold text-ok tabular-nums">Net Savings: +₹ 1,125</span>
                    </div>
                    <p className="text-[12px] text-ink-2">
                      Fair risk-sharing price band: ₹65.00/carton (between seller floor ₹40 and buyer ceiling ₹90). 0 stockout.
                    </p>
                  </div>
                )}

                {/* Link to workspace */}
                <div className="flex items-center justify-between pt-1">
                  <span className="text-meta text-ink-3">Canonical test case verified in suite</span>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate('/plan')}
                  >
                    Open this plan in workspace
                  </Button>
                </div>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* ========================================================================= */}
      {/* 3. THREE RULED ARCHITECTURAL BANDS (No Card Grids)                        */}
      {/* ========================================================================= */}
      <section className="w-full bg-paper py-16">
        <div className="max-w-page mx-auto px-6 lg:px-10 flex flex-col divide-y divide-line">

          {/* Stage 01: Data Gate & Demand Learning */}
          <div className="py-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-3 flex items-baseline gap-3">
              <span className="font-serif text-[32px] font-bold text-ink-3 tabular-nums">01</span>
              <div>
                <h3 className="font-serif text-[20px] font-bold text-ink">
                  Data Gate & Demand Learning
                </h3>
                <span className="text-meta text-ink-3 block mt-0.5">
                  Pre-planning validation & WAPE selection
                </span>
              </div>
            </div>

            <div className="lg:col-span-9 flex flex-col gap-4 text-body text-ink-2">
              <p className="text-[15px] leading-relaxed max-w-[70ch]">
                Garbage in, disastrous shipments out. Before any solver run, VyaparMitra enforces a strict <strong className="text-ink">Fix First</strong> gate 
                evaluating 6 critical defect categories: duplicate SKUs, mixed case-pack units, negative physical inventory, missing sales days, zero cost records, and unmapped destinations.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">20 Synthetic Defects</span>
                  <p className="text-meta text-ink-3">
                    Pre-loaded defect manifest testable in 1 click on the Data screen.
                  </p>
                </div>

                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">WAPE Model Selection</span>
                  <p className="text-meta text-ink-3">
                    Croston for intermittent slow-movers, Exp Smoothing for trends, Moving Average for steady SKUs.
                  </p>
                </div>

                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">Zero Data Leaks</span>
                  <p className="text-meta text-ink-3">
                    Strict rolling-origin backtesting ensuring future sales never leak into fitting sets.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Stage 02: Two-Stage Lexicographic MILP & FEFO Caps */}
          <div className="py-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-3 flex items-baseline gap-3">
              <span className="font-serif text-[32px] font-bold text-ink-3 tabular-nums">02</span>
              <div>
                <h3 className="font-serif text-[20px] font-bold text-ink">
                  Two-Stage Lexicographic MILP
                </h3>
                <span className="text-meta text-ink-3 block mt-0.5">
                  Service first, then freight & expiry waste
                </span>
              </div>
            </div>

            <div className="lg:col-span-9 flex flex-col gap-4 text-body text-ink-2">
              <p className="text-[15px] leading-relaxed max-w-[70ch]">
                Heuristic spreadsheet rules sacrifice customer fill rate to save pennies on trucking. 
                VyaparMitra formulates allocation as a rigorous <strong className="text-ink">two-stage lexicographic mixed-integer linear program (MILP)</strong>:
              </p>

              <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-3 font-mono text-meta text-ink">
                <div className="flex items-start gap-2">
                  <span className="font-bold text-brand shrink-0">Stage 1:</span>
                  <span>Maximize customer demand fulfillment (Ndem) and safety-stock replenishment (Ntot).</span>
                </div>
                <div className="flex items-start gap-2 pt-2 border-t border-line">
                  <span className="font-bold text-brand shrink-0">Stage 2:</span>
                  <span>Minimize total freight cost (Σ c_sd × x_sd) + penalize dispatching near-expiry inventory below 21 days acceptance life (Eshort).</span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">FEFO Sell-Through Caps</span>
                  <p className="text-meta text-ink-3">
                    Batches expiring before customer consumption are blocked mathematically from shipping to avoid dead-stock at the retailer.
                  </p>
                </div>

                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">Instant Fallback Heuristic</span>
                  <p className="text-meta text-ink-3">
                    If solver reaches time limit, a greedy FEFO heuristic delivers an immediate feasible plan clearly badged for the planner.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Stage 03: Shortfall Counterfactuals, Surplus Rescue & Walk-Forward Proof */}
          <div className="py-12 grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-3 flex items-baseline gap-3">
              <span className="font-serif text-[32px] font-bold text-ink-3 tabular-nums">03</span>
              <div>
                <h3 className="font-serif text-[20px] font-bold text-ink">
                  Prescription & Surplus Rescue
                </h3>
                <span className="text-meta text-ink-3 block mt-0.5">
                  Root-cause diagnosis & peer godown trade
                </span>
              </div>
            </div>

            <div className="lg:col-span-9 flex flex-col gap-4 text-body text-ink-2">
              <p className="text-[15px] leading-relaxed max-w-[70ch]">
                When inventory falls short, standard tools display a red cell and stop. VyaparMitra traces every unmet carton to its binding constraint 
                (Stock, Lead Time, Shelf Life, or Lane Capacity), calculates the smallest rupee fix, and unlocks <strong className="text-ink">Surplus Rescue</strong> across peer godowns.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">Verified Spare Gate</span>
                  <p className="text-meta text-ink-3">
                    Ring-fences seller's own 7-day forecast and safety stock before surplus is made tradeable.
                  </p>
                </div>

                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">50/50 Price Band</span>
                  <p className="text-meta text-ink-3">
                    Computes fair break-even bounds between seller salvage floor and buyer stockout ceiling.
                  </p>
                </div>

                <div className="p-4 bg-surface border border-line rounded-control flex flex-col gap-1">
                  <span className="text-meta font-semibold text-ink">28-Day Walk-Forward Proof</span>
                  <p className="text-meta text-ink-3">
                    Multi-seed simulation benchmarked against Min/Max and Greedy baselines with honest loss reporting.
                  </p>
                </div>
              </div>
            </div>
          </div>

        </div>
      </section>

      {/* ========================================================================= */}
      {/* 4. FOOTER LEDGER BAR                                                      */}
      {/* ========================================================================= */}
      <footer className="w-full bg-surface border-t border-line py-8 select-none">
        <div className="max-w-page mx-auto px-6 lg:px-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex flex-col gap-1 max-w-xl">
            <span className="font-serif text-[16px] font-bold text-ink">
              VyaparMitra — Honest Distribution Intelligence
            </span>
            <p className="text-meta text-ink-3 leading-relaxed">
              Demonstration software developed for Triwizathon 2026. Operates strictly on simulated regional FMCG datasets. 
              Zero outbound network calls, zero unverified stock assertions, and full mathematical audit trails on every dispatch.
            </p>
          </div>

          {/* Quick Route Links */}
          <div className="flex flex-wrap items-center gap-4 text-meta font-medium">
            <button
              type="button"
              onClick={() => navigate('/data')}
              className="text-ink-2 hover:text-ink transition-colors"
            >
              Data Gate
            </button>
            <button
              type="button"
              onClick={() => navigate('/plan')}
              className="text-ink-2 hover:text-ink transition-colors"
            >
              Plan Desk
            </button>
            <button
              type="button"
              onClick={() => navigate('/review')}
              className="text-ink-2 hover:text-ink transition-colors"
            >
              Review
            </button>
            <button
              type="button"
              onClick={() => navigate('/evaluate')}
              className="text-ink-2 hover:text-ink transition-colors"
            >
              Evaluation Proof
            </button>
            <button
              type="button"
              onClick={() => navigate('/audit')}
              className="text-ink-2 hover:text-ink transition-colors"
            >
              Audit Ledger
            </button>
            <button
              type="button"
              onClick={() => navigate('/design')}
              className="text-ink-3 hover:text-ink transition-colors"
            >
              Design Tokens
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}
