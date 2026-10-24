import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Badge,
  DataTable,
  Tooltip,
  InlineMessage,
  EmptyState,
  useToast,
  formatINR,
  formatCartons,
  formatDate,
} from '../components/ui';
import { DispatchSlipDrawer } from '../components/plan/DispatchSlipDrawer';
import { apiFetch, getStoredRole } from '../lib/api';
import {
  CheckSquare,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ShieldCheck,
  Filter,
} from 'lucide-react';

export function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const urlLine = searchParams.get('line');
  const urlStatus = (searchParams.get('status') as 'all' | 'draft' | 'approved' | 'rejected') || 'all';
  const urlDest = searchParams.get('dest') || 'all';

  const [selectedLineId, setSelectedLineId] = useState<string | null>(urlLine);
  const [statusFilter, setStatusFilter] = useState<'all' | 'draft' | 'approved' | 'rejected'>(urlStatus);
  const [destinationFilter, setDestinationFilter] = useState<string>(urlDest);

  // Sync to URL
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (selectedLineId) next.set('line', selectedLineId);
    else next.delete('line');

    if (statusFilter !== 'all') next.set('status', statusFilter);
    else next.delete('status');

    if (destinationFilter !== 'all') next.set('dest', destinationFilter);
    else next.delete('dest');

    setSearchParams(next, { replace: true });
  }, [selectedLineId, statusFilter, destinationFilter]);

  const role = getStoredRole();
  const canModify = role === 'planner' || role === 'reviewer';

  // Fetch latest plan
  const { data: planData, isLoading: planLoading, refetch: refetchPlan } = useQuery({
    queryKey: ['latest-plan'],
    queryFn: async () => {
      try {
        return await apiFetch<any>('/api/plan/latest');
      } catch (err: any) {
        if (err.status === 404) return null;
        throw err;
      }
    },
  });

  // Fetch products and locations
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

  // Bulk Approve Mutation
  const bulkApproveMutation = useMutation({
    mutationFn: async (linesToApprove: any[]) => {
      for (const line of linesToApprove) {
        await apiFetch(`/api/plan/lines/${line.id}/approve`, {
          method: 'POST',
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({ type: 'success', message: 'All pending lines approved' });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Approval failed' });
    },
  });

  const lines = planData?.lines || [];

  const isPending = (s?: string) => {
    const val = (s || '').toLowerCase();
    return val === 'proposed' || val === 'draft' || val === 'pending';
  };
  const isApproved = (s?: string) => {
    const val = (s || '').toLowerCase();
    return val === 'approved' || val === 'edited';
  };
  const isRejected = (s?: string) => (s || '').toLowerCase() === 'rejected';

  const filteredLines = useMemo(() => {
    return lines.filter((line: any) => {
      let matchStatus = true;
      if (statusFilter === 'draft') {
        matchStatus = isPending(line.status);
      } else if (statusFilter === 'approved') {
        matchStatus = isApproved(line.status);
      } else if (statusFilter === 'rejected') {
        matchStatus = isRejected(line.status);
      }
      const matchDest = destinationFilter === 'all' || line.destination_id === destinationFilter;
      return matchStatus && matchDest;
    });
  }, [lines, statusFilter, destinationFilter]);

  const pendingCount = lines.filter((l: any) => isPending(l.status)).length;
  const approvedCount = lines.filter((l: any) => isApproved(l.status)).length;
  const rejectedCount = lines.filter((l: any) => isRejected(l.status)).length;

  const columns = [
    {
      key: 'product_id',
      header: 'Product',
      render: (r: any) => productNameMap[r.product_id] || r.product_id,
    },
    { key: 'source_id', header: 'From' },
    {
      key: 'destination_id',
      header: 'To',
      render: (r: any) => locationNameMap[r.destination_id] || r.destination_id,
    },
    {
      key: 'cartons',
      header: 'Cartons',
      isNumeric: true,
      render: (r: any) => formatCartons(r.cartons),
    },
    {
      key: 'cost',
      header: 'Cost',
      isNumeric: true,
      render: (r: any) => formatINR(r.cost),
    },
    {
      key: 'arrival_date',
      header: 'Arrives',
      render: (r: any) => formatDate(r.arrival_date),
    },
    {
      key: 'status',
      header: 'Status',
      render: (r: any) => (
        <Badge
          variant={
            isApproved(r.status)
              ? 'ok'
              : isRejected(r.status)
              ? 'madder'
              : 'neutral'
          }
        >
          {r.status || 'PROPOSED'}
        </Badge>
      ),
    },
    {
      key: 'action',
      header: 'Action',
      render: (r: any) => (
        <Button
          size="sm"
          variant="secondary"
          onClick={(e) => {
            e.stopPropagation();
            setSelectedLineId(r.id);
          }}
        >
          Open slip
        </Button>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Role Notice */}
      {!canModify && (
        <InlineMessage severity="info">
          Warehouse role is read-only. Switch role to Planner or Reviewer in the top bar to approve or reject lines.
        </InlineMessage>
      )}

      {/* Review Metrics Header */}
      <section className="border-y border-line bg-surface py-4 px-6 select-none">
        <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-line">
          <div className="flex flex-col gap-1 pb-3 sm:pb-0 sm:pr-6">
            <span className="text-meta font-medium text-ink-2">Pending review</span>
            <span className="text-section font-serif font-bold text-ink tabular-nums">
              {pendingCount} lines
            </span>
          </div>
          <div className="flex flex-col gap-1 py-3 sm:py-0 sm:px-6">
            <span className="text-meta font-medium text-ink-2">Approved</span>
            <span className="text-section font-serif font-bold text-ok tabular-nums">
              {approvedCount} lines
            </span>
          </div>
          <div className="flex flex-col gap-1 pt-3 sm:pt-0 sm:pl-6">
            <span className="text-meta font-medium text-ink-2">Rejected</span>
            <span className="text-section font-serif font-bold text-madder tabular-nums">
              {rejectedCount} lines
            </span>
          </div>
        </div>
      </section>

      {/* Filter and Bulk Action Bar */}
      <section className="flex flex-wrap items-center justify-between gap-4 py-3 px-4 bg-surface border-y border-line text-body">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-meta text-ink-2">
            <Filter className="w-4 h-4 text-ink-3" strokeWidth={1.5} />
            <span>Filter:</span>
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as any)}
            className="h-8 px-2 bg-surface text-ink border border-line-strong rounded-control text-meta"
          >
            <option value="all">All statuses</option>
            <option value="draft">Pending draft</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>

          <select
            value={destinationFilter}
            onChange={(e) => setDestinationFilter(e.target.value)}
            className="h-8 px-2 bg-surface text-ink border border-line-strong rounded-control text-meta"
          >
            <option value="all">All destinations</option>
            <option value="D1">D1, Kolkata</option>
            <option value="D2">D2, Ahmedabad</option>
            <option value="S1">S1, Bengaluru</option>
            <option value="S2">S2, Pune</option>
          </select>
        </div>

        {pendingCount > 0 && (
          <Tooltip content={!canModify ? 'Warehouse role cannot approve' : ''}>
            <span>
              <Button
                variant="primary"
                size="sm"
                disabled={!canModify || bulkApproveMutation.isPending}
                loading={bulkApproveMutation.isPending}
                onClick={() =>
                  bulkApproveMutation.mutate(lines.filter((l: any) => isPending(l.status)))
                }
              >
                Approve all pending ({pendingCount})
              </Button>
            </span>
          </Tooltip>
        )}
      </section>

      {/* Review Table */}
      <section className="flex flex-col gap-4">
        {lines.length === 0 ? (
          <EmptyState
            title="No plan to review"
            description="Generate a plan on the Plan screen before reviewing dispatch lines."
            action={
              <Button variant="primary" onClick={() => (window.location.href = '/plan')}>
                Go to Plan
              </Button>
            }
          />
        ) : (
          <DataTable
            columns={columns}
            data={filteredLines}
            keyExtractor={(l) => l.id}
            onRowClick={(l) => setSelectedLineId(l.id)}
            emptyMessage="No dispatch lines match selected filters."
          />
        )}
      </section>

      {/* Dispatch Slip Drawer */}
      <DispatchSlipDrawer
        lineId={selectedLineId}
        onClose={() => setSelectedLineId(null)}
        onLineUpdated={() => refetchPlan()}
      />
    </div>
  );
}
