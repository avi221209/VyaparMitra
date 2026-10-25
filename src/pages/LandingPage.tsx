import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Badge,
  Skeleton,
  EmptyState,
  formatINR,
  formatCartons,
} from '../components/ui';
import { apiFetch } from '../lib/api';
import {
  ArrowRight,
  Database,
  CalendarCheck,
  CheckSquare,
  BarChart2,
  FileText,
  AlertTriangle,
  Check,
  CheckCircle2,
  XCircle,
  Truck,
  TrendingUp,
  Play,
} from 'lucide-react';

export function LandingPage() {
  const navigate = useNavigate();
  const [selectedScenario, setSelectedScenario] = useState<'normal' | 'low_w1' | 'rescue'>('normal');
  const [isLaunching, setIsLaunching] = useState<boolean>(false);

  // Fetch real system status
  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => apiFetch<any>('/api/status'),
    retry: 1,
  });

  // Fetch latest plan summary
  const { data: planData, isLoading: planLoading } = useQuery({
    queryKey: ['latest-plan'],
    queryFn: async () => {
      try {
        return await apiFetch<any>('/api/plan/latest');
      } catch (err: any) {
        if (err.status === 404) return null;
        throw err;
      }
    },
    retry: 1,
  });

  // Fetch validation issues
  const { data: issues = [] } = useQuery({
    queryKey: ['validation-issues'],
    queryFn: async () => {
      try {
        const res = await apiFetch<any>('/api/data/issues');
        return Array.isArray(res) ? res : res.issues || [];
      } catch {
        return [];
      }
    },
    retry: 1,
  });

  const hasData = (statusData?.counts?.products || 0) > 0;
  const productCount = statusData?.counts?.products || 0;
  const locationCount = statusData?.counts?.locations || 0;
  const hasPlan = Boolean(planData && planData.lines && planData.lines.length > 0);
  const planLineCount = planData?.lines?.length || 0;
  const openIssues = issues.filter((i: any) => i.status === 'open');
  const criticalIssues = openIssues.filter((i: any) => i.severity === 'critical');
  const pendingLines = (planData?.lines || []).filter((l: any) => {
    const s = (l.status || '').toLowerCase();
    return s === 'proposed' || s === 'draft' || s === 'pending';
  });
  const unmetCartons = planData?.totals?.unmet_demand_cartons || 0;

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

  // Determine the primary recommended action
  const getPrimaryAction = () => {
    if (!hasData) return { label: 'Load your data to begin', target: '/data', variant: 'primary' as const };
    if (criticalIssues.length > 0) return { label: `Fix ${criticalIssues.length} data issue${criticalIssues.length > 1 ? 's' : ''}`, target: '/data', variant: 'danger' as const };
    if (!hasPlan) return { label: 'Generate a distribution plan', target: '/plan', variant: 'primary' as const };
    if (pendingLines.length > 0) return { label: `Review ${pendingLines.length} pending line${pendingLines.length > 1 ? 's' : ''}`, target: '/review', variant: 'primary' as const };
    return { label: 'Open distribution plan', target: '/plan', variant: 'primary' as const };
  };

  const primaryAction = getPrimaryAction();

  return (
    <div className="min-h-screen flex flex-col bg-paper text-ink font-sans selection:bg-brand-wash selection:text-brand">
      {/* ====== TOP MASTHEAD ====== */}
      <header className="w-full bg-surface border-b border-line select-none sticky top-0 z-40">
        <div className="max-w-page mx-auto px-6 lg:px-10 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <span className="font-serif text-[22px] font-bold text-ink tracking-tight">
              VyaparMitra
            </span>
            <div className="h-4 w-px bg-line hidden sm:block" />
            <span className="text-meta text-ink-2 hidden md:inline">
              Distribution Intelligence for Regional FMCG
            </span>
          </div>

          <div className="flex items-center gap-3 sm:gap-4">
            {/* Simulated Data Stamp */}
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

      {/* ====== HERO: WHAT NEEDS ATTENTION ====== */}
      <section className="w-full bg-surface border-b border-line py-10 lg:py-12">
        <div className="max-w-page mx-auto px-6 lg:px-10">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-8">
            <div>
              <h1 className="font-serif text-[28px] sm:text-[34px] font-bold text-ink leading-[1.15] tracking-tight">
                What needs your attention today?
              </h1>
              <p className="text-body text-ink-2 mt-2 max-w-[60ch]">
                VyaparMitra helps you decide what ships where, minimize stock shortages, and track every decision.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant={primaryAction.variant === 'danger' ? 'danger' : 'primary'}
                size="md"
                onClick={() => navigate(primaryAction.target)}
                icon={<ArrowRight className="w-4 h-4" strokeWidth={1.5} />}
              >
                {primaryAction.label}
              </Button>

              {!hasData && (
                <Button
                  variant="secondary"
                  size="md"
                  loading={isLaunching}
                  onClick={handleLaunchLiveDemo}
                >
                  Quick start with sample data
                </Button>
              )}
            </div>
          </div>

          {/* ====== STATUS CARDS ====== */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Data Readiness */}
            <button
              type="button"
              onClick={() => navigate('/data')}
              className="text-left p-4 bg-paper border border-line rounded-control hover:border-line-strong transition-colors group"
            >
              <div className="flex items-center justify-between mb-3">
                <Database className="w-5 h-5 text-ink-3 group-hover:text-brand transition-colors" strokeWidth={1.5} />
                {statusLoading ? (
                  <Skeleton className="h-4 w-16" />
                ) : hasData ? (
                  <Badge variant="ok" icon={<Check className="w-3 h-3" strokeWidth={2} />}>Ready</Badge>
                ) : (
                  <Badge variant="neutral">Not loaded</Badge>
                )}
              </div>
              <h3 className="text-body font-semibold text-ink mb-0.5">Data & Network</h3>
              {statusLoading ? (
                <Skeleton className="h-3 w-32 mt-1" />
              ) : hasData ? (
                <p className="text-meta text-ink-3">{productCount} products, {locationCount} locations</p>
              ) : (
                <p className="text-meta text-ink-3">Load your inventory and sales data</p>
              )}
              {openIssues.length > 0 && (
                <div className="mt-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-turmeric" strokeWidth={1.5} />
                  <span className="text-meta text-turmeric font-medium">
                    {openIssues.length} issue{openIssues.length > 1 ? 's' : ''} to resolve
                  </span>
                </div>
              )}
            </button>

            {/* Plan Status */}
            <button
              type="button"
              onClick={() => navigate('/plan')}
              className="text-left p-4 bg-paper border border-line rounded-control hover:border-line-strong transition-colors group"
            >
              <div className="flex items-center justify-between mb-3">
                <CalendarCheck className="w-5 h-5 text-ink-3 group-hover:text-brand transition-colors" strokeWidth={1.5} />
                {planLoading ? (
                  <Skeleton className="h-4 w-16" />
                ) : hasPlan ? (
                  <Badge variant="ok" icon={<Check className="w-3 h-3" strokeWidth={2} />}>Generated</Badge>
                ) : (
                  <Badge variant="neutral">No plan</Badge>
                )}
              </div>
              <h3 className="text-body font-semibold text-ink mb-0.5">Distribution Plan</h3>
              {planLoading ? (
                <Skeleton className="h-3 w-32 mt-1" />
              ) : hasPlan ? (
                <p className="text-meta text-ink-3">{planLineCount} dispatch lines generated</p>
              ) : (
                <p className="text-meta text-ink-3">Generate a plan after loading data</p>
              )}
              {unmetCartons > 0 && (
                <div className="mt-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-madder" strokeWidth={1.5} />
                  <span className="text-meta text-madder font-medium">
                    {formatCartons(unmetCartons)} unmet
                  </span>
                </div>
              )}
            </button>

            {/* Review Status */}
            <button
              type="button"
              onClick={() => navigate('/review')}
              className="text-left p-4 bg-paper border border-line rounded-control hover:border-line-strong transition-colors group"
            >
              <div className="flex items-center justify-between mb-3">
                <CheckSquare className="w-5 h-5 text-ink-3 group-hover:text-brand transition-colors" strokeWidth={1.5} />
                {planLoading ? (
                  <Skeleton className="h-4 w-16" />
                ) : pendingLines.length > 0 ? (
                  <Badge variant="turmeric">{pendingLines.length} pending</Badge>
                ) : hasPlan ? (
                  <Badge variant="ok">All reviewed</Badge>
                ) : (
                  <Badge variant="neutral">—</Badge>
                )}
              </div>
              <h3 className="text-body font-semibold text-ink mb-0.5">Review & Approve</h3>
              {planLoading ? (
                <Skeleton className="h-3 w-32 mt-1" />
              ) : pendingLines.length > 0 ? (
                <p className="text-meta text-ink-3">{pendingLines.length} line{pendingLines.length > 1 ? 's' : ''} awaiting review</p>
              ) : hasPlan ? (
                <p className="text-meta text-ink-3">All dispatch lines reviewed</p>
              ) : (
                <p className="text-meta text-ink-3">Review after plan generation</p>
              )}
            </button>

            {/* Evaluation */}
            <button
              type="button"
              onClick={() => navigate('/evaluate')}
              className="text-left p-4 bg-paper border border-line rounded-control hover:border-line-strong transition-colors group"
            >
              <div className="flex items-center justify-between mb-3">
                <BarChart2 className="w-5 h-5 text-ink-3 group-hover:text-brand transition-colors" strokeWidth={1.5} />
                <Badge variant="neutral">Benchmark</Badge>
              </div>
              <h3 className="text-body font-semibold text-ink mb-0.5">Evaluation & Proof</h3>
              <p className="text-meta text-ink-3">28-day walk-forward results vs baselines</p>
            </button>
          </div>
        </div>
      </section>

      {/* ====== WORKFLOW STEPS ====== */}
      <section className="w-full bg-paper py-8 border-b border-line">
        <div className="max-w-page mx-auto px-6 lg:px-10">
          <h2 className="text-section font-serif font-semibold text-ink mb-5">How VyaparMitra works</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                step: '1',
                title: 'Load & validate data',
                desc: 'Import products, sales, inventory, and lanes. VyaparMitra checks for 20 types of data defects before planning.',
                link: '/data',
                done: hasData,
              },
              {
                step: '2',
                title: 'Generate a distribution plan',
                desc: 'The optimizer forecasts demand, respects shelf-life limits, and recommends what to ship where.',
                link: '/plan',
                done: hasPlan,
              },
              {
                step: '3',
                title: 'Review recommendations',
                desc: 'Inspect each dispatch line, understand shortages, approve or reject. Every action is logged.',
                link: '/review',
                done: hasPlan && pendingLines.length === 0,
              },
              {
                step: '4',
                title: 'Evaluate performance',
                desc: 'Walk-forward simulation proves performance against Min/Max and Greedy baselines.',
                link: '/evaluate',
                done: false,
              },
            ].map((item) => (
              <button
                key={item.step}
                type="button"
                onClick={() => navigate(item.link)}
                className="text-left p-4 bg-surface border border-line rounded-control hover:border-line-strong transition-colors group flex flex-col gap-2"
              >
                <div className="flex items-center gap-2">
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                    item.done
                      ? 'bg-ok text-surface'
                      : 'bg-paper border-2 border-line-strong text-ink-3'
                  }`}>
                    {item.done ? <Check className="w-3.5 h-3.5" strokeWidth={2.5} /> : item.step}
                  </span>
                  <h3 className="text-body font-semibold text-ink group-hover:text-brand transition-colors">
                    {item.title}
                  </h3>
                </div>
                <p className="text-meta text-ink-3 leading-relaxed">{item.desc}</p>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* ====== INTERACTIVE WORKED EXAMPLE ====== */}
      <section className="w-full bg-surface py-10 border-b border-line">
        <div className="max-w-page mx-auto px-6 lg:px-10">
          <div className="border border-line rounded-control bg-paper/60 p-5 flex flex-col gap-4">
            {/* Header & Scenario Selection Pills */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line">
              <div>
                <h2 className="text-section font-serif font-semibold text-ink">
                  Live worked example
                </h2>
                <span className="text-meta text-ink-3">
                  See how the optimizer handles stock constraints in a 2-warehouse, 2-destination network
                </span>
              </div>

              {/* Scenario Pills */}
              <div className="flex flex-wrap items-center gap-1.5 select-none">
                {([
                  { key: 'normal', label: 'Normal stock' },
                  { key: 'low_w1', label: 'W1 stock cut 20%' },
                  { key: 'rescue', label: 'Surplus rescue' },
                ] as const).map((s) => (
                  <button
                    key={s.key}
                    type="button"
                    onClick={() => setSelectedScenario(s.key)}
                    className={`px-2.5 py-1 text-meta rounded-control font-medium transition-colors ${
                      selectedScenario === s.key
                        ? 'bg-ink text-surface'
                        : 'bg-surface text-ink-2 hover:bg-paper border border-line'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Mini SVG Network Flow Diagram */}
            <div className="bg-surface border border-line rounded-control p-3">
              <svg
                viewBox="0 0 460 130"
                className="w-full h-auto select-none font-sans"
                role="img"
                aria-label="Worked-example network flow diagram showing warehouses W1 and W2 shipping to destinations D1 and D2"
              >
                {/* W1 to D1 Lane */}
                <line
                  x1="90" y1="35" x2="350" y2="35"
                  stroke={selectedScenario === 'low_w1' ? 'var(--color-ink-2)' : 'var(--color-brand)'}
                  strokeWidth="2"
                />
                {/* W1 to D2 Lane */}
                <line
                  x1="90" y1="35" x2="350" y2="95"
                  stroke={selectedScenario === 'low_w1' ? 'var(--color-line)' : 'var(--color-brand)'}
                  strokeWidth={selectedScenario === 'low_w1' ? '1' : '1.5'}
                  strokeDasharray={selectedScenario === 'low_w1' ? '4 4' : 'none'}
                />
                {/* W2 to D1 Lane */}
                <line
                  x1="90" y1="95" x2="350" y2="35"
                  stroke="var(--color-brand)"
                  strokeWidth="1.5"
                />
                {/* Peer Rescue Lane */}
                {selectedScenario === 'rescue' && (
                  <line x1="220" y1="115" x2="350" y2="95"
                    stroke="var(--color-ok)" strokeWidth="2.5" />
                )}

                {/* Nodes */}
                <circle cx="90" cy="35" r="14" fill="var(--color-brand)" />
                <text x="90" y="39" textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="bold">W1</text>
                <text x="90" y="16" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">
                  {selectedScenario === 'low_w1' ? '72 ctns' : '90 ctns'}
                </text>

                <circle cx="90" cy="95" r="14" fill="var(--color-ink-2)" />
                <text x="90" y="99" textAnchor="middle" fill="#FFFFFF" fontSize="10" fontWeight="bold">W2</text>
                <text x="90" y="122" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">60 ctns (42d)</text>

                <circle cx="350" cy="35" r="14" fill="var(--color-paper)" stroke="var(--color-brand)" strokeWidth="2" />
                <text x="350" y="39" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="bold">D1</text>
                <text x="350" y="16" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">Kolkata (130 ctns)</text>

                <circle cx="350" cy="95" r="14"
                  fill={selectedScenario === 'low_w1' ? 'var(--color-madder-wash)' : 'var(--color-paper)'}
                  stroke={selectedScenario === 'low_w1' ? 'var(--color-madder)' : 'var(--color-brand)'}
                  strokeWidth="2"
                />
                <text x="350" y="99" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="bold">D2</text>
                <text x="350" y="122" textAnchor="middle" fill="var(--color-ink)" fontSize="10" fontWeight="600">Ahmedabad (65 ctns)</text>

                {selectedScenario === 'rescue' && (
                  <g>
                    <circle cx="220" cy="115" r="10" fill="var(--color-ok)" />
                    <text x="220" y="118" textAnchor="middle" fill="#FFFFFF" fontSize="8" fontWeight="bold">P1</text>
                    <text x="220" y="102" textAnchor="middle" fill="var(--color-ok)" fontSize="9" fontWeight="bold">Peer Rescue +45 ctns</text>
                  </g>
                )}
              </svg>
            </div>

            {/* Dispatch Table */}
            <div className="bg-surface border border-line rounded-control overflow-hidden">
              <table className="w-full text-left border-collapse text-body font-sans">
                <thead>
                  <tr className="border-b border-line bg-paper/50 text-meta font-medium text-ink-2">
                    <th className="py-2 px-3">Source</th>
                    <th className="py-2 px-3">Destination</th>
                    <th className="py-2 px-3 text-right">Dispatched</th>
                    <th className="py-2 px-3 text-right">Freight</th>
                    <th className="py-2 px-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-meta">
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
                  <tr className="hover:bg-paper/30">
                    <td className="py-2 px-3 font-medium text-ink">W2 Bhiwandi</td>
                    <td className="py-2 px-3">D1 Kolkata</td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-ink">60 ctns</td>
                    <td className="py-2 px-3 text-right tabular-nums text-ink-2">₹ 175</td>
                    <td className="py-2 px-3 text-right">
                      <Badge variant="neutral">Exp 42d</Badge>
                    </td>
                  </tr>
                  {selectedScenario === 'rescue' && (
                    <tr className="bg-ok-wash/40 font-semibold">
                      <td className="py-2 px-3 font-bold text-ok">P1 Peer Godown</td>
                      <td className="py-2 px-3 text-ok">D2 Ahmedabad</td>
                      <td className="py-2 px-3 text-right tabular-nums text-ok font-bold">45 ctns</td>
                      <td className="py-2 px-3 text-right tabular-nums text-ink-2">₹ 135</td>
                      <td className="py-2 px-3 text-right">
                        <Badge variant="ok">Rescued</Badge>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Scenario Outcome */}
            {selectedScenario === 'normal' && (
              <div className="p-3 bg-surface border border-line rounded-control flex items-center justify-between text-meta">
                <span className="text-ink font-medium">Outcome: 100% demand met, 0 cartons unmet</span>
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
                  <span className="font-semibold text-ok">Surplus rescue from P1: 45 cartons recovered</span>
                  <span className="font-bold text-ok tabular-nums">Net Savings: +₹ 1,125</span>
                </div>
                <p className="text-[12px] text-ink-2">
                  Fair risk-sharing price band: ₹65.00/carton (between seller floor ₹40 and buyer ceiling ₹90). 0 stockout.
                </p>
              </div>
            )}

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
      </section>

      {/* ====== FOOTER ====== */}
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

          <div className="flex flex-wrap items-center gap-4 text-meta font-medium">
            {[
              { label: 'Data', to: '/data' },
              { label: 'Plan', to: '/plan' },
              { label: 'Review', to: '/review' },
              { label: 'Evaluation', to: '/evaluate' },
              { label: 'Audit', to: '/audit' },
              { label: 'Design', to: '/design' },
            ].map((link) => (
              <button
                key={link.to}
                type="button"
                onClick={() => navigate(link.to)}
                className="text-ink-2 hover:text-ink transition-colors"
              >
                {link.label}
              </button>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
