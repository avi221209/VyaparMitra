import React, { useState, useEffect, useMemo, lazy, Suspense } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Package,
  MapPin,
  Boxes,
  AlertTriangle,
  Calendar,
  ArrowRight,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
  Wheat,
  Utensils,
  Sparkles,
  Coffee,
  Check,
  X,
  Play,
  RotateCw,
  HelpCircle,
} from 'lucide-react';
import {
  Button,
  Modal,
  useToast,
  Tooltip,
  ErrorBoundary,
} from '../components/ui';
import {
  apiFetch,
  getStoredRole,
  DemoRole,
} from '../lib/api';
import { getStoredUserName } from '../components/layout/ProfileChip';
import { SettingsDrawer } from '../components/layout/SettingsDrawer';

// Lazy-load the offline SVG India map
const IndiaNetworkMap = lazy(() => import('../components/dashboard/IndiaNetworkMap'));

// Types matching the backend schema
interface PlanningPeriod {
  start: string;
  end: string;
  horizon_days: number;
}

interface AttentionKPI {
  count: number;
  low_stock: number;
  critical: number;
  high_demand: number;
  unmet_cartons: number;
  blocking_data_issues: number;
}

interface DashboardKPIs {
  products: number;
  locations: {
    total: number;
    warehouses: number;
    retailers: number;
  };
  inventory_units: number;
  attention: AttentionKPI;
}

interface StockStatusItem {
  product_id: string;
  name: string;
  category: string;
  total_stock_units: number;
  expected_demand_units: number;
  ratio: number;
  status: 'Healthy' | 'Low stock' | 'Critical';
}

interface BenefitVsBaseline {
  value_inr: number;
  baseline: string;
  source: string;
}

interface RecentPlan {
  run_id: string;
  created_at: string;
  status: string;
  dispatches: number;
  locations: number;
  units: number;
  transport_cost: number;
  used_heuristic: boolean;
  benefit_vs_baseline: BenefitVsBaseline | null;
}

interface ForecastWeek {
  label: string;
  actual: number | null;
  forecast: number | null;
  is_future: boolean;
}

interface ForecastSummary {
  weeks: ForecastWeek[];
  wape: number;
  accuracy_pct: number;
  bias: number;
}

interface PendingApprovalItem {
  line_id: string;
  product_name: string;
  category: string;
  from_name: string;
  to_name: string;
  cartons: number;
  created_at: string;
}

interface DashboardData {
  as_of: string;
  data_is_sample: boolean;
  planning_period: PlanningPeriod;
  kpis: DashboardKPIs;
  network: {
    nodes: any[];
    flows: any[];
    unmapped: string[];
  };
  stock_status: StockStatusItem[];
  recent_plan: RecentPlan | null;
  forecast: ForecastSummary;
  pending_approvals: {
    total: number;
    items: PendingApprovalItem[];
  };
}

export function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [role, setRole] = useState<DemoRole>(getStoredRole());
  const [userName, setUserName] = useState<string>(getStoredUserName());
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Reject modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [selectedLineForReject, setSelectedLineForReject] = useState<PendingApprovalItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  // Undo state for approvals
  const [lastApprovedLine, setLastApprovedLine] = useState<{ id: string; cartons: number } | null>(null);

  useEffect(() => {
    const handleRoleChanged = () => setRole(getStoredRole());
    const handleUserChanged = () => setUserName(getStoredUserName());
    window.addEventListener('role-changed', handleRoleChanged);
    window.addEventListener('username-changed', handleUserChanged);
    return () => {
      window.removeEventListener('role-changed', handleRoleChanged);
      window.removeEventListener('username-changed', handleUserChanged);
    };
  }, []);

  // Fetch Dashboard Summary
  const { data, isLoading, isError, error, refetch } = useQuery<DashboardData>({
    queryKey: ['dashboard-summary'],
    queryFn: () => apiFetch<DashboardData>('/api/v1/dashboard/summary'),
    staleTime: 15000,
  });

  // Time-aware greeting
  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  }, []);

  // Formatted date period
  const formattedPeriod = useMemo(() => {
    if (!data?.planning_period) return '—';
    const s = new Date(data.planning_period.start);
    const e = new Date(data.planning_period.end);
    const sStr = s.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
    const eStr = e.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
    return `${sStr} – ${eStr} (${data.planning_period.horizon_days} days)`;
  }, [data]);

  // Distinct category count
  const categoryCount = useMemo(() => {
    if (!data?.stock_status) return 0;
    const set = new Set(data.stock_status.map((item) => item.category));
    return set.size;
  }, [data]);

  // Approve Line Mutation
  const approveMutation = useMutation({
    mutationFn: async (lineId: string) => {
      return apiFetch(`/api/v1/plan/lines/${lineId}/approve`, {
        method: 'POST',
      });
    },
    onSuccess: (_, lineId) => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      toast({
        type: 'success',
        message: `Line #${lineId} approved successfully.`,
        undoLabel: 'Undo',
        undoAction: async () => {
          try {
            await apiFetch(`/api/v1/plan/lines/${lineId}/reject`, {
              method: 'POST',
              body: JSON.stringify({ reason: 'Approval undone by operator' }),
            });
            queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
            toast({ type: 'info', message: `Undo successful for line #${lineId}.` });
          } catch (err: any) {
            toast({ type: 'error', message: err.message || 'Undo failed' });
          }
        },
      });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Approval failed' });
    },
  });

  // Reject Line Mutation
  const rejectMutation = useMutation({
    mutationFn: async ({ lineId, reason }: { lineId: string; reason: string }) => {
      return apiFetch(`/api/v1/plan/lines/${lineId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason }),
      });
    },
    onSuccess: (_, { lineId }) => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      setRejectModalOpen(false);
      setRejectReason('');
      setSelectedLineForReject(null);
      toast({
        type: 'info',
        message: `Line #${lineId} rejected.`,
        undoLabel: 'Undo',
        undoAction: async () => {
          try {
            await apiFetch(`/api/v1/plan/lines/${lineId}/approve`, {
              method: 'POST',
            });
            queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
            toast({ type: 'info', message: `Undo successful for line #${lineId}.` });
          } catch (err: any) {
            toast({ type: 'error', message: err.message || 'Undo failed' });
          }
        },
      });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Rejection failed' });
    },
  });

  // Quick Plan Generator
  const generatePlanMutation = useMutation({
    mutationFn: async () => {
      return apiFetch('/api/v1/plan', { method: 'POST' });
    },
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] });
      toast({ type: 'success', message: `Plan #${res.run_id} generated successfully.` });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Plan generation failed' });
    },
  });

  const isRoleAuthorized = role === 'planner' || role === 'reviewer';

  const getCategoryIcon = (category: string) => {
    switch (category?.toLowerCase()) {
      case 'staples':
        return <Wheat className="w-4 h-4 text-brand shrink-0" strokeWidth={1.5} />;
      case 'packaged food':
        return <Utensils className="w-4 h-4 text-turmeric shrink-0" strokeWidth={1.5} />;
      case 'personal care':
      case 'home care':
        return <Sparkles className="w-4 h-4 text-brand shrink-0" strokeWidth={1.5} />;
      case 'beverages':
        return <Coffee className="w-4 h-4 text-ink-2 shrink-0" strokeWidth={1.5} />;
      default:
        return <Package className="w-4 h-4 text-brand shrink-0" strokeWidth={1.5} />;
    }
  };

  // 1. Loading Skeleton View (no layout shift)
  if (isLoading) {
    return (
      <div className="flex flex-col gap-6 animate-pulse select-none">
        {/* Row 1 Header skeleton */}
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-2">
            <div className="h-8 w-64 bg-line rounded-control" />
            <div className="h-4 w-48 bg-line rounded-control" />
          </div>
          <div className="h-14 w-60 bg-line rounded-control" />
        </div>

        {/* Row 2 KPI skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-surface rounded-[12px] border border-line p-5" />
          ))}
        </div>

        {/* Row 3 skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 h-[500px] bg-surface rounded-[12px] border border-line" />
          <div className="lg:col-span-5 h-[500px] bg-surface rounded-[12px] border border-line" />
        </div>

        {/* Row 4 skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-72 bg-surface rounded-[12px] border border-line p-5" />
          ))}
        </div>
      </div>
    );
  }

  // 2. Global Error State with Retry
  if (isError || !data) {
    return (
      <div className="p-12 text-center bg-surface rounded-[12px] border border-line shadow-card flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 rounded-full bg-madder-wash text-madder flex items-center justify-center">
          <AlertTriangle className="w-6 h-6" strokeWidth={1.5} />
        </div>
        <div>
          <h2 className="text-section font-serif font-semibold text-ink">Unable to Load Dashboard</h2>
          <p className="text-body text-ink-3 mt-1 max-w-md">
            {(error as any)?.message || 'Could not communicate with VyaparMitra backend service.'}
          </p>
        </div>
        <Button variant="primary" onClick={() => refetch()} className="inline-flex items-center gap-2">
          <RotateCw className="w-4 h-4" />
          <span>Retry Connection</span>
        </Button>
      </div>
    );
  }

  // 3. First-Run Zero Data State
  if (data.kpis.products === 0) {
    return (
      <div className="p-16 text-center bg-surface rounded-[12px] border border-line shadow-card flex flex-col items-center justify-center gap-5 max-w-2xl mx-auto my-12">
        <div className="w-16 h-16 rounded-full bg-brand-wash text-brand flex items-center justify-center">
          <Package className="w-8 h-8" strokeWidth={1.5} />
        </div>
        <div>
          <h2 className="text-display font-serif font-semibold text-ink">Welcome to VyaparMitra</h2>
          <p className="text-body text-ink-2 mt-2 max-w-md mx-auto leading-relaxed">
            No inventory or master files detected. Load your product catalog, warehouse batches, and sales history to start distribution planning.
          </p>
        </div>
        <div className="flex items-center gap-3 mt-2">
          <Button variant="primary" onClick={() => navigate('/data')} className="inline-flex items-center gap-2">
            <span>Upload Your Data</span>
            <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 animate-fade-up">
      {/* =================================================================== */}
      {/* ROW 1: Greeting & Planning Period Card                              */}
      {/* =================================================================== */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-[26px] md:text-[30px] font-semibold text-ink tracking-tight">
            {greeting}, {userName}!
          </h1>
          <p className="text-body text-ink-2 mt-1">Here's what needs your attention today.</p>
        </div>

        {/* Planning Period Card */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card px-4 py-2.5 flex items-center gap-4 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-control bg-brand-wash text-brand flex items-center justify-center shrink-0">
              <Calendar className="w-4 h-4" strokeWidth={1.5} />
            </div>
            <div>
              <div className="text-[11px] font-semibold text-ink-3 uppercase tracking-wider">
                Planning Period
              </div>
              <div className="text-meta font-semibold text-ink tabular-nums">{formattedPeriod}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            className="px-2.5 py-1 text-meta font-medium text-brand bg-brand-wash/60 hover:bg-brand-wash border border-brand/20 rounded-control transition-colors"
          >
            Change
          </button>
        </div>
      </div>

      {/* =================================================================== */}
      {/* ROW 2: 4 KPI CARDS                                                  */}
      {/* =================================================================== */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* KPI 1: Total Products */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-meta font-medium text-ink-2">Total Products</span>
            <div className="w-8 h-8 rounded-control bg-brand-wash text-brand flex items-center justify-center">
              <Package className="w-4 h-4" strokeWidth={1.5} />
            </div>
          </div>
          <div className="mt-3">
            <div className="font-serif text-[32px] font-semibold text-ink tabular-nums leading-none">
              {data.kpis.products}
            </div>
            <div className="text-meta text-ink-3 mt-1.5">
              Across {categoryCount} categories
            </div>
          </div>
        </div>

        {/* KPI 2: Active Locations */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-meta font-medium text-ink-2">Active Locations</span>
            <div className="w-8 h-8 rounded-control bg-brand-wash text-brand flex items-center justify-center">
              <MapPin className="w-4 h-4" strokeWidth={1.5} />
            </div>
          </div>
          <div className="mt-3">
            <div className="font-serif text-[32px] font-semibold text-ink tabular-nums leading-none">
              {data.kpis.locations.total}
            </div>
            <div className="text-meta text-ink-3 mt-1.5">
              {data.kpis.locations.warehouses} warehouses • {data.kpis.locations.retailers} retailers
            </div>
          </div>
        </div>

        {/* KPI 3: Total Inventory */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-meta font-medium text-ink-2">Total Inventory</span>
            <div className="w-8 h-8 rounded-control bg-brand-wash text-brand flex items-center justify-center">
              <Boxes className="w-4 h-4" strokeWidth={1.5} />
            </div>
          </div>
          <div className="mt-3">
            <div className="font-serif text-[32px] font-semibold text-ink tabular-nums leading-none">
              {data.kpis.inventory_units.toLocaleString('en-IN')}
            </div>
            <div className="text-meta text-ink-3 mt-1.5">
              across all locations
            </div>
          </div>
        </div>

        {/* KPI 4: Items Needing Attention */}
        <Link
          to="/plan"
          className="bg-madder-wash/40 hover:bg-madder-wash/60 rounded-[12px] border border-madder/30 hover:border-madder p-5 flex flex-col justify-between transition-colors group cursor-pointer"
        >
          <div className="flex items-center justify-between">
            <span className="text-meta font-semibold text-madder">Items Needing Attention</span>
            <div className="w-8 h-8 rounded-control bg-madder-wash text-madder flex items-center justify-center border border-madder/20">
              <AlertTriangle className="w-4 h-4" strokeWidth={1.5} />
            </div>
          </div>
          <div className="mt-3">
            <div className="font-serif text-[32px] font-semibold text-madder tabular-nums leading-none">
              {data.kpis.attention.count}
            </div>
            <div className="text-meta text-madder/90 mt-1.5 font-medium flex items-center justify-between">
              <span>
                {data.kpis.attention.low_stock} low stock • {data.kpis.attention.high_demand} high demand
              </span>
              <ArrowRight className="w-4 h-4 text-madder transform group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </Link>
      </div>

      {/* =================================================================== */}
      {/* ROW 3: MAP (60%) & STOCK STATUS TABLE (40%)                         */}
      {/* =================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left: Distribution Network Map (60% ~ 7 cols) */}
        <div className="lg:col-span-7 bg-surface rounded-[12px] border border-line shadow-card p-6 flex flex-col gap-4">
          <div>
            <h2 className="font-serif text-[18px] font-semibold text-ink leading-tight">
              Distribution Network
            </h2>
            <p className="text-meta text-ink-3 mt-0.5">
              Overview of your warehouses, retailers, and planned dispatch routes.
            </p>
          </div>

          <ErrorBoundary fallbackTitle="Distribution Map Error">
            <Suspense
              fallback={
                <div className="w-full h-[540px] bg-paper/50 rounded-control flex items-center justify-center text-meta text-ink-3 animate-pulse">
                  Rendering offline network topology…
                </div>
              }
            >
              <IndiaNetworkMap
                nodes={data.network.nodes}
                flows={data.network.flows}
                unmapped={data.network.unmapped}
              />
            </Suspense>
          </ErrorBoundary>
        </div>

        {/* Right: Stock Status by Product (40% ~ 5 cols) */}
        <div className="lg:col-span-5 bg-surface rounded-[12px] border border-line shadow-card p-6 flex flex-col justify-between min-h-[580px]">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-serif text-[18px] font-semibold text-ink leading-tight">
                  Stock Status by Product
                </h2>
                <p className="text-meta text-ink-3 mt-0.5">5 most at-risk products across the network</p>
              </div>
              <Link
                to="/data"
                className="text-meta font-semibold text-brand hover:underline inline-flex items-center gap-1 shrink-0"
              >
                <span>View All</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {/* Ruled Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-meta divide-y divide-line">
                <thead>
                  <tr className="text-ink-3 font-semibold text-[11px] uppercase tracking-wider pb-2">
                    <th className="py-2.5 pr-2">Product</th>
                    <th className="py-2.5 px-2 text-right">Stock</th>
                    <th className="py-2.5 px-2 text-right">Demand</th>
                    <th className="py-2.5 pl-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/60">
                  {data.stock_status.slice(0, 5).map((item) => {
                    const isCritical = item.status === 'Critical';
                    const isLow = item.status === 'Low stock';

                    return (
                      <tr key={item.product_id} className="hover:bg-paper/40 transition-colors">
                        <td className="py-3 pr-2">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded bg-paper flex items-center justify-center shrink-0">
                              {getCategoryIcon(item.category)}
                            </div>
                            <div className="truncate max-w-[130px] sm:max-w-[160px]">
                              <div className="font-medium text-ink truncate text-[13px]">{item.name}</div>
                              <div className="text-[11px] text-ink-3">{item.category}</div>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums text-ink font-medium">
                          {item.total_stock_units.toLocaleString('en-IN')}
                        </td>
                        <td className="py-3 px-2 text-right tabular-nums text-ink-2">
                          {item.expected_demand_units.toLocaleString('en-IN')}
                        </td>
                        <td className="py-3 pl-2 text-right">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-chip text-[11px] font-semibold shrink-0 ${
                              isCritical
                                ? 'bg-madder text-white'
                                : isLow
                                ? 'bg-madder-wash text-madder border border-madder/30'
                                : 'bg-ok/10 text-ok border border-ok/30'
                            }`}
                          >
                            {isCritical ? (
                              <AlertCircle className="w-3 h-3 shrink-0" />
                            ) : isLow ? (
                              <AlertTriangle className="w-3 h-3 shrink-0" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3 shrink-0" />
                            )}
                            <span>{item.status}</span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="pt-4 mt-4 border-t border-line text-[11.5px] text-ink-3 flex items-center justify-between">
            <span>Ratios update automatically as inventory changes</span>
            <span className="font-medium text-ink">Target: Ratio ≥ 1.0</span>
          </div>
        </div>
      </div>

      {/* =================================================================== */}
      {/* ROW 4: THREE EQUAL CARDS                                            */}
      {/* =================================================================== */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch">
        {/* CARD 1: Recent Distribution Plan */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="font-serif text-[18px] font-semibold text-ink">
                Recent Distribution Plan
              </span>
              {data.recent_plan && (
                <span className="px-2 py-0.5 rounded-chip text-[11px] font-semibold bg-brand-wash text-brand border border-brand/20">
                  {data.recent_plan.used_heuristic ? 'Heuristic' : 'Generated'}
                </span>
              )}
            </div>

            {data.recent_plan ? (
              <div className="flex flex-col gap-4">
                <div>
                  <div className="font-semibold text-body text-ink">
                    Plan #{data.recent_plan.run_id}
                  </div>
                  <div className="text-[11.5px] text-ink-3">
                    Created on {new Date(data.recent_plan.created_at).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </div>
                </div>

                {/* 4 Mini Stats Grid */}
                <div className="grid grid-cols-2 gap-3 py-2 border-y border-line/60">
                  <div className="bg-paper/40 p-2.5 rounded-control">
                    <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                      Dispatches
                    </div>
                    <div className="text-[18px] font-semibold text-ink tabular-nums mt-0.5">
                      {data.recent_plan.dispatches}
                    </div>
                  </div>
                  <div className="bg-paper/40 p-2.5 rounded-control">
                    <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                      Locations
                    </div>
                    <div className="text-[18px] font-semibold text-ink tabular-nums mt-0.5">
                      {data.recent_plan.locations}
                    </div>
                  </div>
                  <div className="bg-paper/40 p-2.5 rounded-control">
                    <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                      Units
                    </div>
                    <div className="text-[18px] font-semibold text-ink tabular-nums mt-0.5">
                      {data.recent_plan.units.toLocaleString('en-IN')}
                    </div>
                  </div>
                  <div className="bg-paper/40 p-2.5 rounded-control">
                    <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                      {data.recent_plan.benefit_vs_baseline ? 'Est. Benefit' : 'Transport Cost'}
                    </div>
                    <div className="text-[18px] font-semibold text-brand tabular-nums mt-0.5">
                      {data.recent_plan.benefit_vs_baseline ? (
                        <Tooltip content={`Benefit vs ${data.recent_plan.benefit_vs_baseline.baseline} (${data.recent_plan.benefit_vs_baseline.source})`}>
                          <span>₹{data.recent_plan.benefit_vs_baseline.value_inr.toLocaleString('en-IN')}</span>
                        </Tooltip>
                      ) : (
                        <span>₹{data.recent_plan.transport_cost.toLocaleString('en-IN')}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-body text-ink-3">
                No plan yet. Generate one to see what moves where.
              </div>
            )}
          </div>

          <div className="pt-4 mt-4">
            {data.recent_plan ? (
              <Button
                variant="primary"
                onClick={() => navigate('/plan')}
                className="w-full justify-center bg-brand hover:bg-[#0A3D33] text-white py-2.5 text-body font-semibold rounded-control"
              >
                <span>View Plan Details</span>
                <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            ) : (
              <Button
                variant="primary"
                onClick={() => generatePlanMutation.mutate()}
                disabled={generatePlanMutation.isPending}
                className="w-full justify-center bg-brand hover:bg-[#0A3D33] text-white py-2.5 text-body font-semibold rounded-control"
              >
                <span>Generate Plan</span>
                <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            )}
          </div>
        </div>

        {/* CARD 2: Demand Forecast (Next 4 Weeks) */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="font-serif text-[18px] font-semibold text-ink">
                Demand Forecast
              </span>
              <span className="text-[11px] text-ink-3 font-medium">Next 4 Weeks</span>
            </div>
            <p className="text-meta text-ink-3 mb-3">Actuals (W-4..W-1) vs Projections (W+1..W+4)</p>

            {/* Hand-built SVG Line Chart */}
            <div className="w-full h-[140px] bg-paper/30 rounded-control p-2 relative">
              <svg viewBox="0 0 320 120" className="w-full h-full overflow-visible">
                {/* Background Grid Lines */}
                <line x1="20" y1="20" x2="310" y2="20" stroke="#E2E8F0" strokeDasharray="3 3" />
                <line x1="20" y1="60" x2="310" y2="60" stroke="#E2E8F0" strokeDasharray="3 3" />
                <line x1="20" y1="100" x2="310" y2="100" stroke="#E2E8F0" />

                {/* Today Divider Line (between index 3 and 4: x ≈ 165) */}
                <line x1="165" y1="10" x2="165" y2="100" stroke="#7E8E9E" strokeDasharray="2 2" strokeWidth="1.2" />
                <text x="168" y="18" fill="#7E8E9E" fontSize="9" fontWeight="600">Today</text>

                {/* Actual Line (solid brand green) */}
                <path
                  d="M 35 75 L 75 65 L 115 50 L 155 42"
                  fill="none"
                  stroke="#0F5C4D"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                />
                {/* Actual Area */}
                <path
                  d="M 35 75 L 75 65 L 115 50 L 155 42 L 155 100 L 35 100 Z"
                  fill="rgba(15, 92, 77, 0.12)"
                />

                {/* Forecast Line (dashed amber/turmeric) */}
                <path
                  d="M 155 42 L 195 38 L 235 32 L 275 28 L 305 25"
                  fill="none"
                  stroke="#B37400"
                  strokeWidth="2.2"
                  strokeDasharray="4 3"
                  strokeLinecap="round"
                />

                {/* X-axis labels */}
                <text x="35" y="114" textAnchor="middle" fill="#667381" fontSize="9">W-4</text>
                <text x="75" y="114" textAnchor="middle" fill="#667381" fontSize="9">W-3</text>
                <text x="115" y="114" textAnchor="middle" fill="#667381" fontSize="9">W-2</text>
                <text x="155" y="114" textAnchor="middle" fill="#667381" fontSize="9">W-1</text>
                <text x="195" y="114" textAnchor="middle" fill="#667381" fontSize="9">W+1</text>
                <text x="235" y="114" textAnchor="middle" fill="#667381" fontSize="9">W+2</text>
                <text x="275" y="114" textAnchor="middle" fill="#667381" fontSize="9">W+3</text>
                <text x="305" y="114" textAnchor="middle" fill="#667381" fontSize="9">W+4</text>
              </svg>
            </div>

            {/* Bottom 2 Metrics: Forecast Accuracy & WAPE */}
            <div className="grid grid-cols-2 gap-3 mt-4 pt-3 border-t border-line/60">
              <div>
                <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                  Forecast Accuracy
                </div>
                <div className="text-[18px] font-semibold text-brand tabular-nums mt-0.5">
                  {data.forecast.accuracy_pct}%
                </div>
              </div>
              <div>
                <div className="text-[11px] font-medium text-ink-3 uppercase tracking-wider">
                  Model WAPE
                </div>
                <div className="text-[18px] font-semibold text-ink tabular-nums mt-0.5">
                  {data.forecast.wape.toFixed(3)}
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 mt-2">
            <Link
              to="/evaluate"
              className="text-meta font-semibold text-brand hover:underline inline-flex items-center gap-1.5"
            >
              <span>View Insights</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* CARD 3: Pending Approvals */}
        <div className="bg-surface rounded-[12px] border border-line shadow-card p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="font-serif text-[18px] font-semibold text-ink">
                Pending Approvals
              </span>
              {data.pending_approvals.total > 0 && (
                <span className="px-2 py-0.5 rounded-chip text-[11px] font-semibold bg-turmeric-wash text-turmeric border border-turmeric/30">
                  {data.pending_approvals.total} waiting
                </span>
              )}
            </div>
            <p className="text-meta text-ink-3 mb-3">Dispatches requiring operator authorization</p>

            {data.pending_approvals.items.length === 0 ? (
              <div className="py-10 text-center text-body text-ink-3">
                Nothing waiting for approval.
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {data.pending_approvals.items.slice(0, 3).map((item) => (
                  <div
                    key={item.line_id}
                    className="p-3 bg-paper/50 rounded-control border border-line flex items-center justify-between gap-2 hover:bg-paper transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-7 h-7 rounded bg-surface flex items-center justify-center shrink-0 border border-line">
                        {getCategoryIcon(item.category)}
                      </div>
                      <div className="min-w-0 truncate">
                        <div className="text-[13px] font-semibold text-ink truncate leading-tight">
                          {item.product_name}
                        </div>
                        <div className="text-[11px] text-ink-3 truncate leading-tight mt-0.5">
                          {item.from_name} → {item.to_name}
                        </div>
                        <div className="text-[11px] font-medium text-brand mt-0.5">
                          {item.cartons} cartons
                        </div>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {isRoleAuthorized ? (
                        <>
                          <button
                            type="button"
                            onClick={() => approveMutation.mutate(item.line_id)}
                            disabled={approveMutation.isPending}
                            title="Approve dispatch"
                            className="p-1.5 bg-brand hover:bg-[#0A3D33] text-white rounded-control transition-colors"
                          >
                            <Check className="w-3.5 h-3.5" strokeWidth={2.5} />
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedLineForReject(item);
                              setRejectModalOpen(true);
                            }}
                            title="Reject dispatch"
                            className="p-1.5 bg-surface hover:bg-madder-wash text-madder border border-madder/40 rounded-control transition-colors"
                          >
                            <X className="w-3.5 h-3.5" strokeWidth={2.5} />
                          </button>
                        </>
                      ) : (
                        <Tooltip content="Requires planner or reviewer role">
                          <span className="text-[11px] text-ink-3 italic px-1.5 py-0.5 bg-paper rounded border border-line">
                            Read only
                          </span>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-4 mt-2">
            <Link
              to="/review"
              className="text-meta font-semibold text-brand hover:underline inline-flex items-center gap-1.5"
            >
              <span>View All ({data.pending_approvals.total})</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
      </div>

      {/* Rejection Modal with Mandatory Reason */}
      <Modal
        open={rejectModalOpen}
        onClose={() => {
          setRejectModalOpen(false);
          setRejectReason('');
          setSelectedLineForReject(null);
        }}
        title="Reject Dispatch Line"
        description="Rejection removes this line from execution and records your justification in the immutable audit log."
        footer={
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setRejectModalOpen(false);
                setRejectReason('');
                setSelectedLineForReject(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={!rejectReason.trim() || rejectMutation.isPending}
              onClick={() => {
                if (selectedLineForReject) {
                  rejectMutation.mutate({
                    lineId: selectedLineForReject.line_id,
                    reason: rejectReason.trim(),
                  });
                }
              }}
            >
              Confirm Rejection
            </Button>
          </div>
        }
      >
        {selectedLineForReject && (
          <div className="flex flex-col gap-3 py-2 text-body">
            <div className="p-3 bg-paper rounded-control border border-line text-meta">
              <span className="font-semibold text-ink">{selectedLineForReject.product_name}</span> ({selectedLineForReject.cartons} cartons)
              <div className="text-ink-3 mt-0.5">
                {selectedLineForReject.from_name} → {selectedLineForReject.to_name}
              </div>
            </div>

            <div>
              <label htmlFor="reject-reason" className="block text-meta font-semibold text-ink mb-1">
                Reason for Rejection <span className="text-madder">*</span>
              </label>
              <textarea
                id="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="State operational reason (e.g. Depot bay maintenance, priority override, retailer buffer sufficient)..."
                rows={3}
                className="w-full p-2.5 text-body bg-surface border border-line rounded-control focus:outline-brand focus:border-brand"
              />
            </div>
          </div>
        )}
      </Modal>

      {/* Settings Drawer */}
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}

export default DashboardPage;
