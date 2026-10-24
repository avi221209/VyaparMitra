import React, { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Drawer,
  Button,
  Badge,
  Input,
  InlineMessage,
  Tooltip,
  useToast,
  formatINR,
  formatCartons,
  formatDays,
} from '../ui';
import { apiFetch, getStoredRole } from '../../lib/api';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Minus,
  Plus,
  ShieldAlert,
} from 'lucide-react';

export interface DispatchSlipDrawerProps {
  lineId: string | null;
  onClose: () => void;
  onLineUpdated?: () => void;
}

export function DispatchSlipDrawer({
  lineId,
  onClose,
  onLineUpdated,
}: DispatchSlipDrawerProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [cartons, setCartons] = useState<number>(0);
  const [rejectReason, setRejectReason] = useState<string>('');
  const [showRejectInput, setShowRejectInput] = useState<boolean>(false);
  const [violationMessage, setViolationMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const role = getStoredRole();
  const canModify = role === 'planner' || role === 'reviewer';

  // Fetch explanation card data for this line
  const {
    data: lineData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['plan-line-explanation', lineId],
    queryFn: () => apiFetch<any>(`/api/plan/lines/${lineId}`),
    enabled: Boolean(lineId),
  });

  useEffect(() => {
    if (lineData) {
      setCartons(lineData.cartons || 0);
      setViolationMessage(null);
      setShowRejectInput(false);
      setRejectReason('');
    }
  }, [lineData]);

  // Approve / Edit Mutation
  const approveMutation = useMutation({
    mutationFn: (newCartons?: number) =>
      apiFetch(`/api/plan/lines/${lineId}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          edited_cartons: newCartons !== undefined ? newCartons : cartons,
        }),
      }),
    onSuccess: (data, newCartons) => {
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['plan-line-explanation', lineId] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      setViolationMessage(null);
      onLineUpdated?.();

      if (newCartons !== undefined && newCartons !== lineData?.cartons) {
        toast({ type: 'success', message: 'Cartons updated' });
      } else {
        toast({
          type: 'success',
          message: 'Approved',
          undoAction: () => rejectMutation.mutate('Undo approval'),
        });
      }
    },
    onError: (err: any) => {
      const msg = err.message || 'Edit refused';
      setViolationMessage(msg);
      toast({ type: 'error', message: 'Edit refused' });
      inputRef.current?.focus();
    },
  });

  // Reject Mutation
  const rejectMutation = useMutation({
    mutationFn: (reason: string) =>
      apiFetch(`/api/plan/lines/${lineId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason || 'Manual rejection' }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['plan-line-explanation', lineId] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      setShowRejectInput(false);
      onLineUpdated?.();
      toast({
        type: 'info',
        message: 'Rejected',
        undoAction: () => approveMutation.mutate(lineData?.cartons),
      });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Rejection failed' });
    },
  });

  if (!lineId) return null;

  const sources = lineData?.sources_considered || [];
  const checks = lineData?.constraints_checked || {};
  const residualRisk = lineData?.residual_risk || {};
  const status = lineData?.status || 'draft';

  return (
    <Drawer
      open={Boolean(lineId)}
      onClose={onClose}
      title={lineData?.product_name || 'Dispatch slip'}
      subtitle={
        <div className="flex items-center gap-2 mt-0.5 text-body">
          <span className="font-medium text-ink">
            {lineData?.source_id} to {lineData?.destination_id}, {lineData?.cartons} cartons
          </span>
          <span className="text-line">|</span>
          <Badge
            variant={status === 'approved' ? 'ok' : status === 'rejected' ? 'madder' : 'neutral'}
          >
            {status}
          </Badge>
        </div>
      }
      footer={
        <div className="w-full flex items-center justify-between gap-3 bg-surface pt-3 border-t border-line">
          <div className="flex items-center gap-2">
            {!showRejectInput ? (
              <Tooltip content={!canModify ? 'Warehouse role cannot reject' : ''}>
                <span>
                  <Button
                    variant="quiet"
                    disabled={!canModify || rejectMutation.isPending}
                    onClick={() => setShowRejectInput(true)}
                  >
                    Reject
                  </Button>
                </span>
              </Tooltip>
            ) : (
              <Button
                variant="danger"
                size="sm"
                disabled={!canModify || rejectMutation.isPending}
                loading={rejectMutation.isPending}
                onClick={() => rejectMutation.mutate(rejectReason)}
              >
                Confirm rejection
              </Button>
            )}
          </div>

          <div className="flex items-center gap-2">
            {cartons !== lineData?.cartons ? (
              <Button
                variant="secondary"
                disabled={!canModify || approveMutation.isPending}
                loading={approveMutation.isPending}
                onClick={() => approveMutation.mutate(cartons)}
              >
                Save cartons
              </Button>
            ) : (
              <Tooltip content={!canModify ? 'Warehouse role cannot approve' : ''}>
                <span>
                  <Button
                    variant="primary"
                    disabled={!canModify || status === 'approved' || approveMutation.isPending}
                    loading={approveMutation.isPending}
                    onClick={() => approveMutation.mutate()}
                  >
                    Approve
                  </Button>
                </span>
              </Tooltip>
            )}
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-6">
        {/* Rule Violation Alert (HTTP 409) */}
        {violationMessage && (
          <InlineMessage severity="error">
            {violationMessage}
          </InlineMessage>
        )}

        {/* Inline Carton Stepper */}
        <div className="flex flex-col gap-2 pb-5 border-b border-line">
          <label className="text-meta font-medium text-ink">
            Dispatched cartons
          </label>
          <div className="flex items-center justify-between">
            <div className="flex items-center border border-line-strong rounded-control bg-surface overflow-hidden">
              <button
                type="button"
                disabled={!canModify || cartons <= 0}
                onClick={() => setCartons((c) => Math.max(0, c - 1))}
                aria-label="Decrease cartons"
                className="w-9 h-9 flex items-center justify-center text-ink-2 hover:bg-paper hover:text-ink disabled:opacity-40"
              >
                <Minus className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
              <input
                ref={inputRef}
                type="number"
                value={cartons}
                disabled={!canModify}
                onChange={(e) => setCartons(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-20 text-center font-semibold tabular-nums border-x border-line-strong h-9 bg-surface text-ink text-body focus-visible:outline-none"
              />
              <button
                type="button"
                disabled={!canModify}
                onClick={() => setCartons((c) => c + 1)}
                aria-label="Increase cartons"
                className="w-9 h-9 flex items-center justify-center text-ink-2 hover:bg-paper hover:text-ink disabled:opacity-40"
              >
                <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
            </div>
            <div className="text-right">
              <span className="text-meta text-ink-3 block">Freight cost</span>
              <span className="text-body font-semibold text-ink tabular-nums">
                {formatINR(lineData?.cost || 0)}
              </span>
            </div>
          </div>
        </div>

        {/* Reject Reason Field (If Opened) */}
        {showRejectInput && (
          <div className="p-3 border border-madder/30 bg-madder-wash rounded-control flex flex-col gap-2">
            <label className="text-meta font-semibold text-madder">
              Reason for rejection
            </label>
            <Input
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="e.g. Broken packaging or unexpected store priority"
              autoFocus
            />
          </div>
        )}

        {/* SECTION 1: Sources Considered (Ruled rows, not boxed) */}
        <div className="flex flex-col gap-3 pb-5 border-b border-line">
          <div className="flex items-center justify-between">
            <h3 className="text-section font-serif font-semibold text-ink">
              Sources considered
            </h3>
            <span className="text-meta text-ink-3 tabular-nums">
              {sources.length} sources evaluated
            </span>
          </div>

          <div className="border-t border-line divide-y divide-line">
            {sources.map((sc: any) => {
              const isEligible = sc.is_eligible;
              return (
                <div
                  key={sc.source_id}
                  className={`py-3 flex items-start gap-3 text-body ${
                    isEligible ? 'bg-transparent' : 'opacity-70'
                  }`}
                >
                  {isEligible ? (
                    <CheckCircle2 className="w-4 h-4 text-ok shrink-0 mt-0.5" strokeWidth={1.5} />
                  ) : (
                    <XCircle className="w-4 h-4 text-madder shrink-0 mt-0.5" strokeWidth={1.5} />
                  )}
                  <div className="flex-1">
                    <div className="flex items-center justify-between font-medium text-ink">
                      <span>{sc.source_name || sc.source_id}</span>
                      <span className="text-meta tabular-nums text-ink-2">
                        {formatINR(sc.cost_per_carton)} / carton, {formatDays(sc.lead_time_days)} lead time
                      </span>
                    </div>
                    <p className="text-meta text-ink-2 mt-0.5 leading-relaxed">
                      {sc.reason || (isEligible ? 'Eligible candidate subject to network constraints' : 'Excluded by constraints')}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* SECTION 2: Checks (Compact two-column table with icons + text) */}
        <div className="flex flex-col gap-3 pb-5 border-b border-line">
          <h3 className="text-section font-serif font-semibold text-ink">
            Checks
          </h3>
          <div className="w-full border-t border-line divide-y divide-line text-body">
            {/* C1: Stock */}
            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Batch stock availability</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.stock?.detail || 'Verified'}
              </span>
            </div>

            {/* C4: Lead Time Gap */}
            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Lead time gap</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.lead_time_gap?.detail || 'Verified'}
              </span>
            </div>

            {/* C6: Lane Capacity */}
            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Lane load capacity</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.lane_capacity?.detail || 'Within lane limit'}
              </span>
            </div>

            {/* Shelf Life */}
            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Shelf life at arrival</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.shelf_life?.detail || 'Passes minimum acceptance life'}
              </span>
            </div>
          </div>
        </div>

        {/* SECTION 3: What is still uncovered (Ruled entries) */}
        <div className="flex flex-col gap-3">
          <h3 className="text-section font-serif font-semibold text-ink">
            What is still uncovered
          </h3>
          <div className="border-t border-line divide-y divide-line text-body">
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-ink-2">Unmet demand</span>
              <span className="font-semibold tabular-nums">
                {residualRisk.unmet_demand_cartons > 0 ? (
                  <span className="text-madder">{formatCartons(residualRisk.unmet_demand_cartons)}</span>
                ) : (
                  <span className="text-ok">0 cartons</span>
                )}
              </span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-ink-2">Safety-stock gap</span>
              <span className="font-semibold tabular-nums">
                {residualRisk.safety_stock_gap_cartons > 0 ? (
                  <span className="text-turmeric">{formatCartons(residualRisk.safety_stock_gap_cartons)}</span>
                ) : (
                  <span className="text-ok">0 cartons</span>
                )}
              </span>
            </div>
          </div>
        </div>
      </div>
    </Drawer>
  );
}
