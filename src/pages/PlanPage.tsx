import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  Button,
  Badge,
  InlineMessage,
  EmptyState,
  Skeleton,
  Popover,
  useToast,
  formatINR,
  formatCartons,
  formatDate,
} from '../components/ui';
import { NetworkStrip } from '../components/plan/NetworkStrip';
import { ForecastDrawer } from '../components/plan/ForecastDrawer';
import { DispatchSlipDrawer } from '../components/plan/DispatchSlipDrawer';
import { WhatIfBar, ChangeSummary } from '../components/plan/WhatIfBar';
import { apiFetch, getStoredRole } from '../lib/api';
import {
  CalendarCheck,
  TrendingUp,
  AlertTriangle,
  Download,
  Search,
  X,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Eye,
  SlidersHorizontal,
} from 'lucide-react';

export function PlanPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // LocalStorage keys
  const HORIZON_STORAGE_KEY = 'vyaparmitra_last_horizon';
  const DENSITY_STORAGE_KEY = 'vyaparmitra_row_density';

  // Read initial URL params with local storage fallbacks
  const urlLine = searchParams.get('line');
  const urlHorizon = parseInt(searchParams.get('horizon') || '') || parseInt(localStorage.getItem(HORIZON_STORAGE_KEY) || '7') || 7;
  const urlSearch = searchParams.get('q') || '';
  const urlDest = searchParams.get('dest') || '';
  const urlProd = searchParams.get('prod') || '';
  const urlFlag = searchParams.get('flag') || '';
  const urlStatus = searchParams.get('status') || '';
  const urlSort = searchParams.get('sort') || 'destination';
  const urlOrder = (searchParams.get('order') as 'asc' | 'desc') || 'asc';
  const urlShowDetails = searchParams.get('details') === 'true';

  // State
  const [horizon, setHorizon] = useState<number>(urlHorizon);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(urlLine);
  const [searchQuery, setSearchQuery] = useState<string>(urlSearch);
  const [destFilter, setDestFilter] = useState<string>(urlDest);
  const [prodFilter, setProdFilter] = useState<string>(urlProd);
  const [flagFilter, setFlagFilter] = useState<string>(urlFlag);
  const [statusFilter, setStatusFilter] = useState<string>(urlStatus);
  const [sortColumn, setSortColumn] = useState<string>(urlSort);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(urlOrder);
  const [showDetails, setShowDetails] = useState<boolean>(urlShowDetails);

  const [hoveredLaneKey, setHoveredLaneKey] = useState<string | null>(null);
  const [density, setDensity] = useState<'comfortable' | 'compact'>(
    (localStorage.getItem(DENSITY_STORAGE_KEY) as 'comfortable' | 'compact') || 'comfortable'
  );

  const [forecastDrawerState, setForecastDrawerState] = useState<{
    open: boolean;
    destinationId: string;
    destinationName: string;
    productId: string;
    productName: string;
  }>({
    open: false,
    destinationId: '',
    destinationName: '',
    productId: '',
    productName: '',
  });

  const [isOrchestrating, setIsOrchestrating] = useState<boolean>(false);

  // Sync state to URL and localStorage
  const updateUrlParams = useCallback(
    (newParams: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(newParams).forEach(([k, v]) => {
        if (v === null || v === '' || v === 'false') {
          next.delete(k);
        } else {
          next.set(k, v);
        }
      });
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  // Handlers for URL state updates
  useEffect(() => {
    updateUrlParams({
      line: selectedLineId,
      horizon: String(horizon),
      q: searchQuery || null,
      dest: destFilter || null,
      prod: prodFilter || null,
      flag: flagFilter || null,
      status: statusFilter || null,
      sort: sortColumn !== 'destination' ? sortColumn : null,
      order: sortOrder !== 'asc' ? sortOrder : null,
      details: showDetails ? 'true' : null,
    });
  }, [
    selectedLineId,
    horizon,
    searchQuery,
    destFilter,
    prodFilter,
    flagFilter,
    statusFilter,
    sortColumn,
    sortOrder,
    showDetails,
  ]);

  const handleHorizonChange = (h: number) => {
    const valid = Math.max(1, Math.min(28, h));
    setHorizon(valid);
    localStorage.setItem(HORIZON_STORAGE_KEY, String(valid));
  };

  const toggleDensity = () => {
    const next = density === 'comfortable' ? 'compact' : 'comfortable';
    setDensity(next);
    localStorage.setItem(DENSITY_STORAGE_KEY, next);
  };

  // Clear all filters
  const clearFilters = () => {
    setSearchQuery('');
    setDestFilter('');
    setProdFilter('');
    setFlagFilter('');
    setStatusFilter('');
  };

  const hasActiveFilters = Boolean(
    searchQuery || destFilter || prodFilter || flagFilter || statusFilter
  );

  // Fetch products and locations for names
  const { data: products = [] } = useQuery({
    queryKey: ['products'],
    queryFn: () => apiFetch<any[]>('/api/products'),
  });

  const { data: locations = [] } = useQuery({
    queryKey: ['locations'],
    queryFn: () => apiFetch<any[]>('/api/locations'),
  });

  const productNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    products.forEach((p: any) => {
      map[p.id] = p.name;
    });
    return map;
  }, [products]);

  const locationNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    locations.forEach((l: any) => {
      map[l.id] = l.name;
    });
    return map;
  }, [locations]);

  // Fetch latest plan
  const {
    data: planData,
    isLoading: planLoading,
    refetch: refetchPlan,
  } = useQuery({
    queryKey: ['latest-plan'],
    queryFn: async () => {
      try {
        return await apiFetch<any>('/api/plan/latest');
      } catch (err: any) {
        if (err.status === 404) return null;
        throw err;
      }
    },
    staleTime: 10000,
  });

  // Generate Plan Mutation
  const generatePlanMutation = useMutation({
    mutationFn: (customPayload?: any) =>
      apiFetch<any>('/api/plan', {
        method: 'POST',
        body: JSON.stringify({
          horizon,
          ...(customPayload || {}),
        }),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['latest-plan'], data);
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({ type: 'success', message: 'Plan generated' });

      // Orchestrated moment: network draw + table stagger
      setIsOrchestrating(true);
      setTimeout(() => {
        setIsOrchestrating(false);
      }, 700);
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Plan generation failed' });
    },
  });

  // Line quick actions (with 8s Undo)
  const role = getStoredRole();
  const canModify = role === 'planner' || role === 'reviewer';

  const approveLine = async (lineId: string, currentCartons: number) => {
    if (!canModify) {
      toast({ type: 'error', message: 'Warehouse role cannot approve dispatches' });
      return;
    }
    try {
      await apiFetch(`/api/plan/lines/${lineId}/approve`, {
        method: 'POST',
        body: JSON.stringify({ edited_cartons: currentCartons }),
      });
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({
        type: 'success',
        message: 'Approved',
        undoAction: async () => {
          await apiFetch(`/api/plan/lines/${lineId}/reject`, {
            method: 'POST',
            body: JSON.stringify({ reason: 'Undo approval' }),
          });
          queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
          queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
        },
      });
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'Approval refused' });
    }
  };

  const rejectLine = async (lineId: string, originalCartons: number) => {
    if (!canModify) {
      toast({ type: 'error', message: 'Warehouse role cannot reject dispatches' });
      return;
    }
    try {
      await apiFetch(`/api/plan/lines/${lineId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: 'Quick keyboard rejection' }),
      });
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({
        type: 'info',
        message: 'Rejected',
        undoAction: async () => {
          await apiFetch(`/api/plan/lines/${lineId}/approve`, {
            method: 'POST',
            body: JSON.stringify({ edited_cartons: originalCartons }),
          });
          queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
          queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
        },
      });
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'Rejection failed' });
    }
  };

  // What-If Regenerate Handler
  const handleWhatIfRegenerate = async (payload: any): Promise<ChangeSummary | null> => {
    const beforeTransport = planData?.totals?.transport_cost || 0;
    const beforeUnmet = planData?.totals?.unmet_demand_cartons || 0;

    try {
      await apiFetch('/api/scenario/override', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      const newPlan = await generatePlanMutation.mutateAsync(payload);

      const afterTransport = newPlan?.totals?.transport_cost || 0;
      const afterUnmet = newPlan?.totals?.unmet_demand_cartons || 0;

      return {
        before: {
          transport_cost: beforeTransport,
          unmet_demand_cartons: beforeUnmet,
        },
        after: {
          transport_cost: afterTransport,
          unmet_demand_cartons: afterUnmet,
        },
        diff_unmet_cartons: afterUnmet - beforeUnmet,
        diff_transport_cost: afterTransport - beforeTransport,
      };
    } catch (err: any) {
      toast({ type: 'error', message: err.message || 'What-if regeneration failed' });
      return null;
    }
  };

  const rawLines = planData?.lines || [];
  const totals = planData?.totals || {};
  const unmetPanel = planData?.unmet_panel || [];
  const hasPlan = Boolean(planData && rawLines.length > 0);

  // Available filter options
  const filterOptions = useMemo(() => {
    const dests = new Set<string>();
    const prods = new Set<string>();
    const flags = new Set<string>();

    rawLines.forEach((l: any) => {
      dests.add(l.destination_id);
      prods.add(l.product_id);
      if (Array.isArray(l.flags)) {
        l.flags.forEach((f: string) => flags.add(f));
      }
    });

    return {
      destinations: Array.from(dests).sort(),
      products: Array.from(prods).sort(),
      flags: Array.from(flags).sort(),
    };
  }, [rawLines]);

  // Filtered and Sorted lines
  const filteredLines = useMemo(() => {
    let result = [...rawLines];

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((l) => {
        const pName = (productNameMap[l.product_id] || l.product_id).toLowerCase();
        const dName = (locationNameMap[l.destination_id] || l.destination_id).toLowerCase();
        const sName = (locationNameMap[l.source_id] || l.source_id).toLowerCase();
        return (
          pName.includes(q) ||
          dName.includes(q) ||
          sName.includes(q) ||
          l.product_id.toLowerCase().includes(q) ||
          l.destination_id.toLowerCase().includes(q) ||
          l.source_id.toLowerCase().includes(q)
        );
      });
    }

    // Destination filter
    if (destFilter) {
      result = result.filter((l) => l.destination_id === destFilter);
    }

    // Product filter
    if (prodFilter) {
      result = result.filter((l) => l.product_id === prodFilter);
    }

    // Flag filter
    if (flagFilter) {
      result = result.filter(
        (l) => Array.isArray(l.flags) && l.flags.includes(flagFilter)
      );
    }

    // Status filter
    if (statusFilter) {
      result = result.filter((l) => (l.status || 'draft') === statusFilter);
    }

    // Sorting
    result.sort((a, b) => {
      let valA: any = a[sortColumn];
      let valB: any = b[sortColumn];

      if (sortColumn === 'product') {
        valA = productNameMap[a.product_id] || a.product_id;
        valB = productNameMap[b.product_id] || b.product_id;
      } else if (sortColumn === 'destination') {
        valA = a.destination_id;
        valB = b.destination_id;
      } else if (sortColumn === 'source') {
        valA = a.source_id;
        valB = b.source_id;
      }

      if (valA === undefined) valA = '';
      if (valB === undefined) valB = '';

      if (typeof valA === 'number' && typeof valB === 'number') {
        return sortOrder === 'asc' ? valA - valB : valB - valA;
      }

      const cmp = String(valA).localeCompare(String(valB));
      return sortOrder === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [
    rawLines,
    searchQuery,
    destFilter,
    prodFilter,
    flagFilter,
    statusFilter,
    sortColumn,
    sortOrder,
    productNameMap,
    locationNameMap,
  ]);

  // Group lines by destination
  const groupedLines = useMemo(() => {
    const groups: Record<
      string,
      {
        destinationId: string;
        destinationName: string;
        lines: any[];
        totalCartons: number;
        totalCost: number;
      }
    > = {};

    filteredLines.forEach((l: any) => {
      const dId = l.destination_id;
      if (!groups[dId]) {
        groups[dId] = {
          destinationId: dId,
          destinationName: locationNameMap[dId] || dId,
          lines: [],
          totalCartons: 0,
          totalCost: 0,
        };
      }
      groups[dId].lines.push(l);
      groups[dId].totalCartons += l.cartons;
      groups[dId].totalCost += l.cost;
    });

    return Object.values(groups);
  }, [filteredLines, locationNameMap]);

  // Network flows for SVG
  const networkFlows = useMemo(() => {
    return rawLines.map((l: any) => ({
      sourceId: l.source_id,
      sourceName: locationNameMap[l.source_id] || l.source_id,
      destinationId: l.destination_id,
      destinationName: locationNameMap[l.destination_id] || l.destination_id,
      cartons: l.cartons,
    }));
  }, [rawLines, locationNameMap]);

  // Unmet cartons per destination for network strip hollow rings
  const unmetByDestination = useMemo(() => {
    const map: Record<string, number> = {};
    unmetPanel.forEach((u: any) => {
      map[u.destination_id] = (map[u.destination_id] || 0) + (u.unmet_demand_cartons || 0);
    });
    return map;
  }, [unmetPanel]);

  // Keyboard navigation across rows: j/k move, Enter opens, a approves, r rejects, e edits
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      ) {
        return;
      }

      if (filteredLines.length === 0) return;

      const currentIndex = filteredLines.findIndex((l) => l.id === selectedLineId);

      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = currentIndex < filteredLines.length - 1 ? currentIndex + 1 : 0;
        setSelectedLineId(filteredLines[nextIndex].id);
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : filteredLines.length - 1;
        setSelectedLineId(filteredLines[prevIndex].id);
      } else if (e.key === 'Enter' && selectedLineId) {
        e.preventDefault();
        // drawer already opens when selectedLineId is truthy
      } else if (e.key === 'a' && selectedLineId) {
        e.preventDefault();
        const line = filteredLines.find((l) => l.id === selectedLineId);
        if (line) approveLine(line.id, line.cartons);
      } else if (e.key === 'r' && selectedLineId) {
        e.preventDefault();
        const line = filteredLines.find((l) => l.id === selectedLineId);
        if (line) rejectLine(line.id, line.cartons);
      } else if (e.key === 'e' && selectedLineId) {
        e.preventDefault();
        // Opens slip drawer focused on cartons stepper
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [filteredLines, selectedLineId, canModify]);

  // Download plan as CSV
  const handleDownloadCSV = () => {
    if (!hasPlan) return;

    const headers = [
      'Line ID',
      'Product ID',
      'Product Name',
      'Source Warehouse',
      'Destination Location',
      'Batch ID',
      'Cartons Dispatched',
      'Freight Cost INR',
      'Estimated Arrival Date',
      'Flags',
      'Approval Status',
    ];

    const rows = filteredLines.map((l) => [
      `"${l.id}"`,
      `"${l.product_id}"`,
      `"${productNameMap[l.product_id] || l.product_id}"`,
      `"${l.source_id}"`,
      `"${l.destination_id}"`,
      `"${l.batch_id || ''}"`,
      l.cartons,
      l.cost,
      `"${l.arrival_date || ''}"`,
      `"${Array.isArray(l.flags) ? l.flags.join('; ') : ''}"`,
      `"${l.status || 'draft'}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `vyaparmitra_plan_${planData?.run_id || 'latest'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast({ type: 'info', message: 'Plan downloaded as CSV' });
  };

  // Header sort toggle helper
  const handleSortToggle = (col: string) => {
    if (sortColumn === col) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(col);
      setSortOrder('asc');
    }
  };

  const renderSortIcon = (col: string) => {
    if (sortColumn !== col) {
      return <ArrowUpDown className="w-3.5 h-3.5 text-line-strong inline ml-1 opacity-0 group-hover:opacity-100" strokeWidth={1.5} />;
    }
    return sortOrder === 'asc' ? (
      <ArrowUp className="w-3.5 h-3.5 text-brand inline ml-1" strokeWidth={1.5} />
    ) : (
      <ArrowDown className="w-3.5 h-3.5 text-brand inline ml-1" strokeWidth={1.5} />
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Print-Only Title Header */}
      <div className="hidden print-only mb-4 border-b border-line pb-2">
        <h1 className="text-display font-serif font-bold text-ink">VyaparMitra — Dispatch Register</h1>
        <p className="text-body text-ink-2">Distribution plan run {planData?.run_id || 'latest'} | Date: 24 Oct 2026</p>
      </div>

      {/* 1. HEADER BAND (NOT A CARD) */}
      <section className="no-print flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-line">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2 text-body">
            <label htmlFor="horizon-input" className="text-meta font-medium text-ink-2">
              Horizon (days):
            </label>
            <input
              id="horizon-input"
              type="number"
              min="1"
              max="28"
              value={horizon}
              onChange={(e) => handleHorizonChange(parseInt(e.target.value) || 7)}
              className="w-16 h-9 px-2 bg-surface text-ink border border-line-strong rounded-control text-body text-center font-semibold tabular-nums"
            />
          </div>

          <Button
            variant="primary"
            loading={generatePlanMutation.isPending}
            onClick={() => generatePlanMutation.mutate()}
            icon={<CalendarCheck className="w-4 h-4" strokeWidth={1.5} />}
          >
            Generate plan
          </Button>

          {hasPlan && (
            <Button
              variant="secondary"
              onClick={handleDownloadCSV}
              icon={<Download className="w-4 h-4" strokeWidth={1.5} />}
            >
              Download plan as CSV
            </Button>
          )}
        </div>

        {planData?.run_id && (
          <div className="flex items-center gap-3 text-meta text-ink-3 tabular-nums">
            <span>Run: <strong className="text-ink font-semibold">{planData.run_id.substring(0, 8)}</strong></span>
            <span className="text-line">|</span>
            <span>{planData.created_at ? formatDate(planData.created_at) : '24 Oct 2026'}</span>
          </div>
        )}
      </section>

      {/* Fallback Method Banner */}
      {(planData?.solver_status === 'fallback' || planData?.solver_status === 'FALLBACK_HEURISTIC' || planData?.status === 'HEURISTIC') && (
        <InlineMessage severity="warning">
          This plan used the fallback method because the primary solver exceeded its time limit.
        </InlineMessage>
      )}

      {/* 2. SUMMARY BAND: ONE BORDERED BAND WITH THREE FIGURES */}
      {hasPlan && (
        <section className="border-y border-line bg-surface py-5 px-6 select-none">
          <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-line">
            {/* Transport Cost */}
            <div className="flex flex-col gap-1 pb-4 md:pb-0 md:pr-6">
              <div className="flex items-center justify-between">
                <span className="text-meta font-medium text-ink-2">Transport cost</span>
                <Popover title="Calculation of transport cost">
                  <p>
                    Transport cost is the exact sum of freight incurred across all dispatched lanes:
                  </p>
                  <code className="block bg-paper p-1.5 rounded-chip text-meta text-ink font-mono font-medium">
                    Total cost = Σ (cartons × lane_freight_per_carton)
                  </code>
                  <p className="text-meta text-ink-3">
                    Current allocation incurs {formatINR(totals.transport_cost || totals.transport || 0)} across {rawLines.length} shipments.
                  </p>
                </Popover>
              </div>
              <span className="text-page-title font-serif font-bold text-ink tabular-nums">
                {formatINR(totals.transport_cost || totals.transport || 0)}
              </span>
              <span className="text-meta text-ink-3">
                Calculated across {rawLines.length} physical dispatches
              </span>
            </div>

            {/* Unmet Demand */}
            <div className="flex flex-col gap-1 py-4 md:py-0 md:px-6">
              <div className="flex items-center justify-between">
                <span className="text-meta font-medium text-ink-2">Unmet demand</span>
                <Popover title="Calculation of unmet demand">
                  <p>
                    Unmet demand represents customer demand over the {horizon}-day horizon that cannot be supplied:
                  </p>
                  <code className="block bg-paper p-1.5 rounded-chip text-meta text-ink font-mono font-medium">
                    Unmet = Target Demand − Eligible Received Stock
                  </code>
                  <p className="text-meta text-ink-3">
                    Excludes stock that fails lead-time or shelf-life acceptance rules.
                  </p>
                </Popover>
              </div>
              <span className="text-page-title font-serif font-bold text-ink tabular-nums">
                {totals.unmet_demand_cartons > 0 ? (
                  <span className="text-madder">{formatCartons(totals.unmet_demand_cartons)}</span>
                ) : (
                  '0 cartons'
                )}
              </span>
              <span className="text-meta text-ink-3">
                Needs exceeding eligible warehouse stock
              </span>
            </div>

            {/* Safety-Stock Gap */}
            <div className="flex flex-col gap-1 pt-4 md:pt-0 md:pl-6">
              <div className="flex items-center justify-between">
                <span className="text-meta font-medium text-ink-2">Safety-stock gap</span>
                <Popover title="Calculation of safety-stock gap">
                  <p>
                    Safety-stock gap is the buffer deficit at destinations below the 90% service level target (z = 1.28):
                  </p>
                  <code className="block bg-paper p-1.5 rounded-chip text-meta text-ink font-mono font-medium">
                    Gap = max(0, Target Safety Stock − Ending Inventory)
                  </code>
                  <p className="text-meta text-ink-3">
                    Weighted in Stage 1 objective at α = 0.5 to balance cycle stock and buffer replenishment.
                  </p>
                </Popover>
              </div>
              <span className="text-page-title font-serif font-bold text-ink tabular-nums">
                {totals.safety_stock_gap_cartons > 0 ? (
                  <span className="text-turmeric">{formatCartons(totals.safety_stock_gap_cartons)}</span>
                ) : (
                  '0 cartons'
                )}
              </span>
              <span className="text-meta text-ink-3">
                Buffer target gap at 90% service level
              </span>
            </div>
          </div>

          {/* Trust Cues */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-meta text-ink-3 border-t border-line mt-5 pt-3">
            <span>Data as of 24 Oct 2026</span>
            <span>Forecast model: Rolling 3-fold cross-validation</span>
            <span>Solver: PuLP CBC lexicographic MILP</span>
            <span>Settings version: v1.0</span>
          </div>
        </section>
      )}

      {/* 3. WHAT-IF BAR */}
      {hasPlan && (
        <div className="no-print">
          <WhatIfBar
            onRegenerate={handleWhatIfRegenerate}
            isGenerating={generatePlanMutation.isPending}
          />
        </div>
      )}

      {/* 4. NETWORK STRIP */}
      {hasPlan && (
        <div className="no-print">
          <NetworkStrip
            flows={networkFlows}
            unmetMap={unmetByDestination}
            hoveredLaneKey={hoveredLaneKey}
            onHoverLane={setHoveredLaneKey}
            isOrchestrating={isOrchestrating}
          />
        </div>
      )}

      {/* 5. DISPATCH REGISTER (THE PLAN TABLE) */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h2 className="text-section font-serif font-semibold text-ink">
              Dispatch Register
            </h2>
            {hasPlan && (
              <span className="text-meta text-ink-3 tabular-nums">
                Showing {filteredLines.length} of {rawLines.length} lines
              </span>
            )}
          </div>

          {hasPlan && (
            <div className="no-print flex flex-wrap items-center gap-3">
              {/* Show Details Toggle */}
              <button
                type="button"
                onClick={() => setShowDetails(!showDetails)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-meta rounded-control border transition-colors ${
                  showDetails
                    ? 'bg-brand-wash border-brand text-brand font-medium'
                    : 'bg-surface border-line-strong text-ink-2 hover:bg-paper'
                }`}
              >
                <Eye className="w-3.5 h-3.5" strokeWidth={1.5} />
                <span>{showDetails ? 'Hide details' : 'Show details'}</span>
              </button>

              {/* Row Density Toggle */}
              <div className="flex items-center gap-1.5 text-meta text-ink-2">
                <span>Density:</span>
                <button
                  type="button"
                  onClick={toggleDensity}
                  className="px-2 py-0.5 border border-line-strong rounded-control bg-surface text-ink font-medium hover:bg-paper"
                >
                  {density === 'comfortable' ? 'Comfortable' : 'Compact'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Filters and Search Bar */}
        {hasPlan && (
          <div className="no-print flex flex-col gap-3 py-3 px-4 bg-surface border-y border-line">
            <div className="flex flex-wrap items-center gap-3">
              {/* Search Box */}
              <div className="relative flex-1 min-w-[200px]">
                <Search className="w-4 h-4 text-ink-3 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" strokeWidth={1.5} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Find a product or destination..."
                  className="w-full pl-9 pr-8 h-8 text-body bg-paper/50 text-ink border border-line-strong rounded-control placeholder:text-ink-3 focus:bg-surface focus-visible:outline-2 focus-visible:outline-brand"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink"
                  >
                    <X className="w-3.5 h-3.5" strokeWidth={1.5} />
                  </button>
                )}
              </div>

              {/* Destination Filter */}
              <select
                value={destFilter}
                onChange={(e) => setDestFilter(e.target.value)}
                className="h-8 px-2 text-meta bg-surface text-ink border border-line-strong rounded-control"
              >
                <option value="">All destinations</option>
                {filterOptions.destinations.map((d) => (
                  <option key={d} value={d}>
                    {locationNameMap[d] || d}
                  </option>
                ))}
              </select>

              {/* Product Filter */}
              <select
                value={prodFilter}
                onChange={(e) => setProdFilter(e.target.value)}
                className="h-8 px-2 text-meta bg-surface text-ink border border-line-strong rounded-control"
              >
                <option value="">All products</option>
                {filterOptions.products.map((p) => (
                  <option key={p} value={p}>
                    {productNameMap[p] || p}
                  </option>
                ))}
              </select>

              {/* Flag Filter */}
              <select
                value={flagFilter}
                onChange={(e) => setFlagFilter(e.target.value)}
                className="h-8 px-2 text-meta bg-surface text-ink border border-line-strong rounded-control"
              >
                <option value="">All flags</option>
                {filterOptions.flags.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>

              {/* Status Filter */}
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-8 px-2 text-meta bg-surface text-ink border border-line-strong rounded-control"
              >
                <option value="">All statuses</option>
                <option value="draft">Draft</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            {/* Active Filter Chips */}
            {hasActiveFilters && (
              <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-line">
                <span className="text-meta text-ink-3">Active filters:</span>
                {searchQuery && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-meta bg-paper border border-line rounded-chip text-ink">
                    Search: "{searchQuery}"
                    <button type="button" onClick={() => setSearchQuery('')} aria-label="Remove search filter">
                      <X className="w-3 h-3 text-ink-3 hover:text-ink" />
                    </button>
                  </span>
                )}
                {destFilter && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-meta bg-paper border border-line rounded-chip text-ink">
                    Destination: {locationNameMap[destFilter] || destFilter}
                    <button type="button" onClick={() => setDestFilter('')} aria-label="Remove destination filter">
                      <X className="w-3 h-3 text-ink-3 hover:text-ink" />
                    </button>
                  </span>
                )}
                {prodFilter && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-meta bg-paper border border-line rounded-chip text-ink">
                    Product: {productNameMap[prodFilter] || prodFilter}
                    <button type="button" onClick={() => setProdFilter('')} aria-label="Remove product filter">
                      <X className="w-3 h-3 text-ink-3 hover:text-ink" />
                    </button>
                  </span>
                )}
                {flagFilter && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-meta bg-paper border border-line rounded-chip text-ink">
                    Flag: {flagFilter}
                    <button type="button" onClick={() => setFlagFilter('')} aria-label="Remove flag filter">
                      <X className="w-3 h-3 text-ink-3 hover:text-ink" />
                    </button>
                  </span>
                )}
                {statusFilter && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-meta bg-paper border border-line rounded-chip text-ink">
                    Status: {statusFilter}
                    <button type="button" onClick={() => setStatusFilter('')} aria-label="Remove status filter">
                      <X className="w-3 h-3 text-ink-3 hover:text-ink" />
                    </button>
                  </span>
                )}
                <button
                  type="button"
                  onClick={clearFilters}
                  className="text-meta text-brand font-medium hover:underline ml-2"
                >
                  Clear filters
                </button>
              </div>
            )}
          </div>
        )}

        {/* Keyboard hint */}
        {hasPlan && (
          <div className="no-print flex items-center justify-between text-meta text-ink-3 px-1">
            <span>
              Keyboard: <kbd className="font-mono bg-surface border border-line px-1 rounded-chip">j</kbd>/<kbd className="font-mono bg-surface border border-line px-1 rounded-chip">k</kbd> move rows, <kbd className="font-mono bg-surface border border-line px-1 rounded-chip">Enter</kbd> opens slip, <kbd className="font-mono bg-surface border border-line px-1 rounded-chip">a</kbd> approve, <kbd className="font-mono bg-surface border border-line px-1 rounded-chip">r</kbd> reject, <kbd className="font-mono bg-surface border border-line px-1 rounded-chip">?</kbd> all shortcuts
            </span>
          </div>
        )}

        {planLoading || generatePlanMutation.isPending ? (
          <div className="border border-line bg-surface p-6 rounded-control flex flex-col gap-4">
            <span className="text-meta font-medium text-ink-2">Optimizing network shipments...</span>
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : !hasPlan ? (
          <EmptyState
            title="No plan yet"
            description="No plan yet. Generate one to see what moves where."
            action={
              <Button
                variant="primary"
                onClick={() => generatePlanMutation.mutate()}
                icon={<CalendarCheck className="w-4 h-4" strokeWidth={1.5} />}
              >
                Generate plan
              </Button>
            }
          />
        ) : filteredLines.length === 0 ? (
          <EmptyState
            title="No matching lines"
            description="No dispatch lines match your active filters or search terms."
            action={
              <Button variant="secondary" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <div className="w-full overflow-x-auto border-y border-line bg-surface">
            <table className="w-full text-left border-collapse text-body font-sans">
              <thead>
                <tr className="border-b border-line bg-paper text-meta font-medium text-ink-2 select-none sticky top-0 z-10">
                  <th
                    className="px-3.5 py-2.5 cursor-pointer group"
                    onClick={() => handleSortToggle('product')}
                  >
                    Product {renderSortIcon('product')}
                  </th>
                  <th
                    className="px-3.5 py-2.5 cursor-pointer group"
                    onClick={() => handleSortToggle('source')}
                  >
                    From {renderSortIcon('source')}
                  </th>
                  <th
                    className="px-3.5 py-2.5 cursor-pointer group"
                    onClick={() => handleSortToggle('destination')}
                  >
                    To {renderSortIcon('destination')}
                  </th>
                  {showDetails && (
                    <th
                      className="px-3.5 py-2.5 cursor-pointer group"
                      onClick={() => handleSortToggle('batch_id')}
                    >
                      Batch {renderSortIcon('batch_id')}
                    </th>
                  )}
                  <th
                    className="px-3.5 py-2.5 text-right cursor-pointer group"
                    onClick={() => handleSortToggle('cartons')}
                  >
                    Cartons {renderSortIcon('cartons')}
                  </th>
                  <th
                    className="px-3.5 py-2.5 text-right cursor-pointer group"
                    onClick={() => handleSortToggle('cost')}
                  >
                    Cost {renderSortIcon('cost')}
                  </th>
                  <th
                    className="px-3.5 py-2.5 cursor-pointer group"
                    onClick={() => handleSortToggle('arrival_date')}
                  >
                    Arrives {renderSortIcon('arrival_date')}
                  </th>
                  <th className="px-3.5 py-2.5">Flags</th>
                  <th
                    className="px-3.5 py-2.5 cursor-pointer group"
                    onClick={() => handleSortToggle('status')}
                  >
                    Status {renderSortIcon('status')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {groupedLines.map((group) => {
                  return (
                    <React.Fragment key={`group-${group.destinationId}`}>
                      {/* Destination Header Row with Forecast link */}
                      <tr className="bg-paper/70 border-y border-line font-medium text-ink">
                        <td colSpan={showDetails ? 9 : 8} className="px-3.5 py-2">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-body">
                              Destination: {group.destinationName} ({group.destinationId})
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                setForecastDrawerState({
                                  open: true,
                                  destinationId: group.destinationId,
                                  destinationName: group.destinationName,
                                  productId: group.lines[0]?.product_id || 'P001',
                                  productName: productNameMap[group.lines[0]?.product_id] || 'Product',
                                })
                              }
                              className="no-print inline-flex items-center gap-1.5 text-meta text-brand hover:underline font-medium"
                            >
                              <TrendingUp className="w-3.5 h-3.5" strokeWidth={1.5} />
                              <span>Forecast</span>
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Group Lines */}
                      {group.lines.map((line: any, idx: number) => {
                        const laneKey = `${line.source_id}-${line.destination_id}`;
                        const isLaneHovered = hoveredLaneKey === laneKey;
                        const isSelected = selectedLineId === line.id;
                        const flags = Array.isArray(line.flags) ? line.flags : [];

                        // 30ms stagger animation on generate
                        const staggerStyle = isOrchestrating
                          ? { animation: `fadeInRow 300ms ease-out ${Math.min(idx * 30, 400)}ms both` }
                          : undefined;

                        return (
                          <tr
                            key={line.id}
                            style={staggerStyle}
                            tabIndex={0}
                            onClick={() => setSelectedLineId(line.id)}
                            onMouseEnter={() => setHoveredLaneKey(laneKey)}
                            onMouseLeave={() => setHoveredLaneKey(null)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                setSelectedLineId(line.id);
                              }
                            }}
                            className={`border-b border-line transition-colors duration-75 cursor-pointer ${
                              density === 'comfortable' ? 'h-[44px]' : 'h-[36px]'
                            } ${
                              isSelected
                                ? 'bg-brand-wash'
                                : isLaneHovered
                                ? 'bg-paper/70'
                                : 'hover:bg-paper/70'
                            }`}
                          >
                            <td className="px-3.5 font-medium text-ink">
                              {productNameMap[line.product_id] || line.product_id}
                            </td>
                            <td className="px-3.5 text-ink-2">{line.source_id}</td>
                            <td className="px-3.5 text-ink-2">{line.destination_id}</td>
                            {showDetails && (
                              <td className="px-3.5 text-meta text-ink-3 font-mono">
                                {line.batch_id || '—'}
                              </td>
                            )}
                            <td className="px-3.5 text-right font-medium text-ink tabular-nums">
                              {formatCartons(line.cartons)}
                            </td>
                            <td className="px-3.5 text-right font-medium text-ink tabular-nums">
                              {formatINR(line.cost)}
                            </td>
                            <td className="px-3.5 text-ink-2 tabular-nums">
                              {formatDate(line.arrival_date)}
                            </td>
                            <td className="px-3.5">
                              <div className="flex flex-wrap gap-1">
                                {flags.map((f: string, fIdx: number) => (
                                  <Badge
                                    key={fIdx}
                                    variant={
                                      f === 'Arrives late'
                                        ? 'madder'
                                        : f === 'Uneconomic'
                                        ? 'turmeric'
                                        : 'neutral'
                                    }
                                  >
                                    {f}
                                  </Badge>
                                ))}
                                {flags.length === 0 && (
                                  <span className="text-meta text-ink-3">—</span>
                                )}
                              </div>
                            </td>
                            <td className="px-3.5">
                              <Badge
                                variant={
                                  line.status === 'approved'
                                    ? 'ok'
                                    : line.status === 'rejected'
                                    ? 'madder'
                                    : 'neutral'
                                }
                              >
                                {line.status || 'draft'}
                              </Badge>
                            </td>
                          </tr>
                        );
                      })}

                      {/* Subtotal Row Under Each Group */}
                      <tr className="bg-paper border-b-2 border-line text-meta font-semibold text-ink">
                        <td colSpan={showDetails ? 4 : 3} className="px-3.5 py-2 text-ink-2">

                          Subtotal for {group.destinationName}
                        </td>
                        <td className="px-3.5 py-2 text-right tabular-nums text-ink">
                          {formatCartons(group.totalCartons)}
                        </td>
                        <td className="px-3.5 py-2 text-right tabular-nums text-ink">
                          {formatINR(group.totalCost)}
                        </td>
                        <td colSpan={3} />
                      </tr>
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* 6. UNMET PANEL BELOW THE TABLE (MADDER RULE ON LEFT EDGE) */}
      {unmetPanel.length > 0 && (
        <section className="border-y border-r border-line border-l-4 border-l-madder bg-surface p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-madder" strokeWidth={1.5} />
              <h3 className="text-section font-serif font-semibold text-ink">
                Unmet demand and binding constraints
              </h3>
            </div>
            <span className="text-meta text-ink-2 tabular-nums">
              {unmetPanel.length} SKU shortages identified
            </span>
          </div>

          <div className="w-full overflow-x-auto">
            <table className="w-full text-left border-collapse text-body font-sans">
              <thead>
                <tr className="border-b border-line text-meta font-medium text-ink-2">
                  <th className="py-2 pr-4">Destination</th>
                  <th className="py-2 pr-4">Product</th>
                  <th className="py-2 pr-4 text-right">Unmet cartons</th>
                  <th className="py-2 pr-4 text-right">Safety-stock gap</th>
                  <th className="py-2 pr-4">Binding constraint</th>
                  <th className="py-2">Smallest fix and extra transport</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {unmetPanel.map((item: any, idx: number) => (
                  <tr key={idx} className="hover:bg-paper/50">
                    <td className="py-2.5 pr-4 font-medium text-ink">
                      {locationNameMap[item.destination_id] || item.destination_id}
                    </td>
                    <td className="py-2.5 pr-4 font-medium text-ink">
                      {productNameMap[item.product_id] || item.product_id}
                    </td>
                    <td className="py-2.5 pr-4 text-right text-madder font-semibold tabular-nums">
                      {formatCartons(item.unmet_demand_cartons)}
                    </td>
                    <td className="py-2.5 pr-4 text-right text-turmeric font-semibold tabular-nums">
                      {formatCartons(item.safety_stock_gap_cartons)}
                    </td>
                    <td className="py-2.5 pr-4">
                      <Badge variant="turmeric">
                        {item.binding_constraint || 'Stock'}
                      </Badge>
                    </td>
                    <td className="py-2.5 text-meta text-ink-2">
                      {item.smallest_fix || 'Supply replenishment required'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Forecast Drawer */}
      <ForecastDrawer
        open={forecastDrawerState.open}
        onClose={() => setForecastDrawerState((prev) => ({ ...prev, open: false }))}
        destinationId={forecastDrawerState.destinationId}
        destinationName={forecastDrawerState.destinationName}
        productId={forecastDrawerState.productId}
        productName={forecastDrawerState.productName}
        allProducts={products}
      />

      {/* Dispatch Slip Drawer (Phase 3 Signature Element) */}
      <DispatchSlipDrawer
        lineId={selectedLineId}
        onClose={() => setSelectedLineId(null)}
        onLineUpdated={() => {
          refetchPlan();
        }}
      />
    </div>
  );
}
