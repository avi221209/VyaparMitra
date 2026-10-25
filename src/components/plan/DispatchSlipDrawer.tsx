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
  ShieldCheck,
  TrendingUp,
  Truck,
  ArrowRight,
} from 'lucide-react';

export interface RescueDrawerContext {
  runId: string;
  destinationId: string;
  destinationName: string;
  productId: string;
  productName: string;
  unmetCartons: number;
  rescueAnalysis: any;
}

export interface DispatchSlipDrawerProps {
  lineId: string | null;
  rescueContext?: RescueDrawerContext | null;
  onClose: () => void;
  onLineUpdated?: () => void;
}

export function DispatchSlipDrawer({
  lineId,
  rescueContext,
  onClose,
  onLineUpdated,
}: DispatchSlipDrawerProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [cartons, setCartons] = useState<number>(0);
  const [rejectReason, setRejectReason] = useState<string>('');
  const [showRejectInput, setShowRejectInput] = useState<boolean>(false);
  const [violationMessage, setViolationMessage] = useState<string | null>(null);
  const [rescueCartons, setRescueCartons] = useState<number>(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const role = getStoredRole();
  const canModify = role === 'planner' || role === 'reviewer';

  const isRescueMode = Boolean(rescueContext);

  // Fetch explanation card data for this line (if lineId provided)
  const {
    data: lineData,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['plan-line-explanation', lineId],
    queryFn: () => apiFetch<any>(`/api/plan/lines/${lineId}`),
    enabled: Boolean(lineId && !rescueContext),
  });

  const isLineRescue = Boolean(lineData?.is_surplus_rescue);

  useEffect(() => {
    if (lineData) {
      setCartons(lineData.cartons || 0);
      setViolationMessage(null);
      setShowRejectInput(false);
      setRejectReason('');
    }
  }, [lineData]);

  useEffect(() => {
    if (rescueContext) {
      const bestQty = rescueContext.rescueAnalysis?.best_rescuable_cartons || 0;
      setRescueCartons(bestQty);
      setViolationMessage(null);
    }
  }, [rescueContext]);

  // Standard Approve / Edit Mutation
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

  // Standard Reject Mutation
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

  // Apply Shortfall Rescue Mutation
  const applyRescueMutation = useMutation({
    mutationFn: async () => {
      if (!rescueContext) return;
      const listingId = rescueContext.rescueAnalysis?.best_listing_id;
      if (!listingId) throw new Error('No eligible surplus listing selected.');

      return apiFetch<any>(`/api/plan/${rescueContext.runId}/rescue/apply`, {
        method: 'POST',
        body: JSON.stringify({
          destination_id: rescueContext.destinationId,
          product_id: rescueContext.productId,
          listing_id: listingId,
          cartons: rescueCartons,
        }),
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      onLineUpdated?.();
      onClose();

      const createdLineId = data?.line_id;
      const runId = rescueContext?.runId;
      const sourceName = rescueContext?.rescueAnalysis?.best_source_name || data?.source_id;

      toast({
        type: 'success',
        message: `Rescued ${rescueCartons} cartons from ${sourceName}`,
        undoAction: async () => {
          if (createdLineId && runId) {
            await apiFetch(`/api/plan/${runId}/rescue/undo`, {
              method: 'POST',
              body: JSON.stringify({ line_id: createdLineId }),
            });
            queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
            queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
            onLineUpdated?.();
          }
        },
      });
    },
    onError: (err: any) => {
      const msg = err.message || 'Surplus rescue failed';
      setViolationMessage(msg);
      toast({ type: 'error', message: msg });
    },
  });

  const isOpen = Boolean(lineId || rescueContext);
  if (!isOpen) return null;

  // Render Rescue Mode (either from Unmet panel inspect OR a surplus rescue line)
  if (isRescueMode || isLineRescue) {
    const analysis = rescueContext ? rescueContext.rescueAnalysis : lineData?.rescue_analysis;
    const destName = rescueContext?.destinationName || lineData?.destination_id;
    const prodName = rescueContext?.productName || lineData?.product_id;
    const unmetQty = rescueContext?.unmetCartons ?? lineData?.residual_risk?.unmet_demand_cartons ?? lineData?.cartons ?? 0;
    const comparison = analysis?.comparison;
    const bestSource = analysis?.eligible_sources?.[0];
    const gate = bestSource?.gate;
    const gains = bestSource?.gains_from_trade;
    const allSources = analysis?.all_sources || [];
    const hasEligible = (analysis?.eligible_sources || []).length > 0;
    const maxRescuable = analysis?.best_rescuable_cartons || 0;

    return (
      <Drawer
        open={isOpen}
        onClose={onClose}
        title={prodName || 'Surplus rescue slip'}
        subtitle={
          <div className="flex items-center gap-2 mt-0.5 text-body">
            <span className="font-medium text-ink">
              Destination: {destName} · Shortfall: {formatCartons(unmetQty)}
            </span>
            <span className="text-line">|</span>
            <Badge variant="ok">Surplus rescue</Badge>
          </div>
        }
        footer={
          <div className="w-full flex items-center justify-between gap-3 bg-surface pt-3 border-t border-line">
            <div className="flex items-center gap-2">
              <Button variant="quiet" size="sm" onClick={onClose}>
                Close
              </Button>
            </div>

            {rescueContext && (
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-meta text-ink-2 font-medium">Rescue cartons:</span>
                  <div className="flex items-center border border-line-strong rounded-control bg-surface overflow-hidden">
                    <button
                      type="button"
                      disabled={!canModify || rescueCartons <= 0}
                      onClick={() => setRescueCartons((c) => Math.max(0, c - 1))}
                      aria-label="Decrease rescue cartons"
                      className="w-8 h-8 flex items-center justify-center text-ink-2 hover:bg-paper hover:text-ink disabled:opacity-40"
                    >
                      <Minus className="w-3 h-3" strokeWidth={1.5} />
                    </button>
                    <input
                      type="number"
                      value={rescueCartons}
                      max={maxRescuable}
                      disabled={!canModify}
                      onChange={(e) =>
                        setRescueCartons(
                          Math.min(maxRescuable, Math.max(0, parseInt(e.target.value) || 0))
                        )
                      }
                      className="w-16 text-center font-semibold tabular-nums border-x border-line-strong h-8 bg-surface text-ink text-meta focus-visible:outline-none"
                    />
                    <button
                      type="button"
                      disabled={!canModify || rescueCartons >= maxRescuable}
                      onClick={() => setRescueCartons((c) => Math.min(maxRescuable, c + 1))}
                      aria-label="Increase rescue cartons"
                      className="w-8 h-8 flex items-center justify-center text-ink-2 hover:bg-paper hover:text-ink disabled:opacity-40"
                    >
                      <Plus className="w-3 h-3" strokeWidth={1.5} />
                    </button>
                  </div>
                </div>

                <Tooltip content={!canModify ? 'Warehouse role cannot apply surplus rescue' : ''}>
                  <span>
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={!canModify || !hasEligible || rescueCartons <= 0 || applyRescueMutation.isPending}
                      loading={applyRescueMutation.isPending}
                      onClick={() => applyRescueMutation.mutate()}
                    >
                      Apply rescue
                    </Button>
                  </span>
                </Tooltip>
              </div>
            )}
          </div>
        }
      >
        <div className="flex flex-col gap-6">
          {violationMessage && (
            <InlineMessage severity="error">{violationMessage}</InlineMessage>
          )}

          {/* SECTION 1: Landed cost-to-serve comparison (3-way) */}
          <div className="flex flex-col gap-3 pb-5 border-b border-line">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-section font-serif font-semibold text-ink">
                  Landed cost-to-serve comparison
                </h3>
                <span className="text-meta text-ink-3">
                  Shortfall resolution options in rupees
                </span>
              </div>
              {comparison?.net_savings_vs_unmet_inr && comparison.net_savings_vs_unmet_inr > 0 ? (
                <Badge variant="ok">
                  Saves {formatINR(comparison.net_savings_vs_unmet_inr)}
                </Badge>
              ) : null}
            </div>

            <div className="border border-line rounded-control overflow-hidden bg-surface">
              <table className="w-full text-left border-collapse text-body font-sans">
                <thead>
                  <tr className="border-b border-line bg-paper/60 text-meta font-medium text-ink-2">
                    <th className="py-2 px-3">Option</th>
                    <th className="py-2 px-3 text-right">Freight</th>
                    <th className="py-2 px-3 text-right">Purchase / Margin</th>
                    <th className="py-2 px-3 text-right">Cost-to-Serve</th>
                    <th className="py-2 px-3 text-right">Net Savings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-meta">
                  {/* 1. Leave Unmet */}
                  <tr className="hover:bg-paper/30">
                    <td className="py-2.5 px-3 font-medium text-ink">
                      1. Leave unmet
                      <span className="block text-[11px] text-ink-3">Stockout / lost sales margin</span>
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-ink-2">
                      {formatINR(comparison?.leave_unmet?.freight_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-madder font-medium">
                      {formatINR(comparison?.leave_unmet?.lost_sales_margin_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-madder">
                      {formatINR(comparison?.leave_unmet?.total_cost_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-ink-3">—</td>
                  </tr>

                  {/* 2. Regular Supplier */}
                  <tr className="hover:bg-paper/30">
                    <td className="py-2.5 px-3 font-medium text-ink">
                      2. Regular supplier
                      <span className="block text-[11px] text-ink-3">
                        Lead-time gap: {comparison?.regular_supplier?.lead_time_days || 0}d lost sales
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-ink-2">
                      {formatINR(comparison?.regular_supplier?.freight_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-ink font-medium">
                      {formatINR(
                        (comparison?.regular_supplier?.purchase_cost_inr || 0) +
                          (comparison?.regular_supplier?.lost_sales_margin_inr || 0)
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-ink">
                      {formatINR(comparison?.regular_supplier?.total_cost_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right text-ink-3">—</td>
                  </tr>

                  {/* 3. Shortfall Rescue */}
                  <tr className="bg-ok-wash/40 font-semibold hover:bg-ok-wash/60">
                    <td className="py-2.5 px-3 font-semibold text-ok">
                      3. Shortfall rescue
                      <span className="block text-[11px] text-ink-2 font-normal">
                        Verified spare from {analysis?.best_source_name || 'peer godown'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-ink">
                      {formatINR(comparison?.shortfall_rescue?.freight_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums text-ink font-medium">
                      {formatINR(comparison?.shortfall_rescue?.purchase_cost_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-bold text-ok">
                      {formatINR(comparison?.shortfall_rescue?.total_cost_inr || 0)}
                    </td>
                    <td className="py-2.5 px-3 text-right tabular-nums font-bold text-ok">
                      +{formatINR(comparison?.net_savings_vs_unmet_inr || 0)}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* SECTION 2: Gains-from-trade price band */}
          {gains && (
            <div className="flex flex-col gap-3 pb-5 border-b border-line">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-section font-serif font-semibold text-ink">
                    Gains-from-trade price band
                  </h3>
                  <span className="text-meta text-ink-3">
                    Fair risk-sharing price between peer godown and buyer
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="brand">
                    Split 50/50
                  </Badge>
                </div>
              </div>

              {/* Price Band Visualization */}
              <div className="p-4 border border-line bg-paper/30 rounded-control flex flex-col gap-3">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="flex flex-col items-start text-left">
                    <span className="text-[11px] text-ink-3 uppercase font-medium">Seller Floor</span>
                    <span className="text-body font-semibold text-ink tabular-nums">
                      {formatINR(gains.seller_floor_per_carton, true)}
                    </span>
                    <span className="text-[11px] text-ink-3">Break-even salvage</span>
                  </div>

                  <div className="flex flex-col items-center">
                    <span className="text-[11px] text-brand uppercase font-bold">Suggested Price</span>
                    <span className="text-section font-bold text-brand tabular-nums">
                      {formatINR(gains.suggested_price_per_carton, true)}
                    </span>
                    <span className="text-[11px] text-ink-2 font-medium">Fair trade point</span>
                  </div>

                  <div className="flex flex-col items-end text-right">
                    <span className="text-[11px] text-ink-3 uppercase font-medium">Buyer Ceiling</span>
                    <span className="text-body font-semibold text-ink tabular-nums">
                      {formatINR(gains.buyer_ceiling_per_carton, true)}
                    </span>
                    <span className="text-[11px] text-ink-3">Stockout avoidance</span>
                  </div>
                </div>

                {/* Ruled band bar */}
                <div className="w-full h-2.5 bg-line rounded-chip relative overflow-hidden">
                  <div className="absolute left-0 top-0 bottom-0 w-full bg-gradient-to-r from-turmeric/40 via-brand to-ok/40" />
                </div>

                {/* Net Gains in Rupees */}
                <div className="flex items-center justify-between pt-2 border-t border-line text-meta">
                  <div className="flex items-center gap-1.5">
                    <span className="text-ink-2">Seller net gain:</span>
                    <span className="font-semibold text-ok tabular-nums">
                      +{formatINR(gains.seller_gain_inr)}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-ink-2">Buyer net gain:</span>
                    <span className="font-semibold text-ok tabular-nums">
                      +{formatINR(gains.buyer_gain_inr)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 3: Verified spare stock gate */}
          {gate && (
            <div className="flex flex-col gap-3 pb-5 border-b border-line">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-section font-serif font-semibold text-ink">
                    Verified spare stock gate
                  </h3>
                  <span className="text-meta text-ink-3">
                    Ring-fencing seller's own forecast + safety stock
                  </span>
                </div>
                <Badge variant={gate.verified_spare_cartons > 0 ? 'ok' : 'madder'}>
                  {gate.verified_spare_cartons > 0 ? 'Gate open' : 'Ring-fenced'}
                </Badge>
              </div>

              <div className="border border-line rounded-control divide-y divide-line text-meta bg-surface">
                <div className="py-2.5 px-3 flex items-center justify-between">
                  <span className="text-ink font-medium">Seller on-hand stock</span>
                  <span className="font-semibold text-ink tabular-nums">
                    {formatCartons(gate.on_hand)}
                  </span>
                </div>
                <div className="py-2.5 px-3 flex items-center justify-between">
                  <span className="text-ink font-medium">Reserved stock</span>
                  <span className="text-ink-2 tabular-nums">
                    {formatCartons(gate.reserved)}
                  </span>
                </div>
                <div className="py-2.5 px-3 flex items-center justify-between">
                  <div>
                    <span className="text-ink font-medium">Seller protected need</span>
                    <span className="block text-[11px] text-ink-3">
                      {gate.protection_days}-day forecast ({gate.seller_daily_forecast} ctns/d) + safety stock (z={gate.z})
                    </span>
                  </div>
                  <span className="font-semibold text-turmeric tabular-nums">
                    {formatCartons(gate.seller_protected_need)}
                  </span>
                </div>
                <div className="py-2.5 px-3 flex items-center justify-between bg-paper/40">
                  <span className="text-ink font-semibold">Verified spare available to trade</span>
                  <span className="font-bold text-ok tabular-nums">
                    {formatCartons(gate.verified_spare_cartons)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: Surplus sources considered & Explained refusals */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-section font-serif font-semibold text-ink">
                  Surplus sources considered
                </h3>
                <span className="text-meta text-ink-3">
                  Deterministic gate checks across network listings
                </span>
              </div>
              <span className="text-meta text-ink-2 tabular-nums">
                {allSources.length} sources audited
              </span>
            </div>

            <div className="border-t border-line divide-y divide-line">
              {allSources.map((sc: any, idx: number) => {
                const isEligible = sc.is_eligible;
                return (
                  <div
                    key={idx}
                    className={`py-3 flex items-start gap-3 text-body ${
                      isEligible ? 'bg-transparent' : 'opacity-80'
                    }`}
                  >
                    {isEligible ? (
                      <CheckCircle2
                        className="w-4 h-4 text-ok shrink-0 mt-0.5"
                        strokeWidth={1.5}
                      />
                    ) : (
                      <XCircle
                        className="w-4 h-4 text-madder shrink-0 mt-0.5"
                        strokeWidth={1.5}
                      />
                    )}
                    <div className="flex-1">
                      <div className="flex items-center justify-between font-medium text-ink">
                        <span>{sc.source_name || sc.listing_id}</span>
                        <span className="text-meta tabular-nums text-ink-2">
                          {formatINR(sc.freight_per_carton)} / ctn · {formatDays(sc.lead_time_days)} lead time
                        </span>
                      </div>
                      <p className="text-meta text-ink-2 mt-0.5 leading-relaxed">
                        {sc.reason}
                      </p>
                      {isEligible && (
                        <div className="flex items-center gap-3 mt-1 text-meta text-ink font-medium">
                          <span>Spare: {formatCartons(sc.verified_spare_cartons)}</span>
                          <span>·</span>
                          <span className="text-ok">Rescuable: {formatCartons(sc.rescuable_cartons)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </Drawer>
    );
  }

  // Standard Dispatch Slip Drawer (Non-rescue)
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
          <InlineMessage severity="error">{violationMessage}</InlineMessage>
        )}

        {/* Inline Carton Stepper */}
        <div className="flex flex-col gap-2 pb-5 border-b border-line">
          <label className="text-meta font-medium text-ink">Dispatched cartons</label>
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

        {/* SECTION 1: Sources Considered */}
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
                    <CheckCircle2
                      className="w-4 h-4 text-ok shrink-0 mt-0.5"
                      strokeWidth={1.5}
                    />
                  ) : (
                    <XCircle
                      className="w-4 h-4 text-madder shrink-0 mt-0.5"
                      strokeWidth={1.5}
                    />
                  )}
                  <div className="flex-1">
                    <div className="flex items-center justify-between font-medium text-ink">
                      <span>{sc.source_name || sc.source_id}</span>
                      <span className="text-meta tabular-nums text-ink-2">
                        {formatINR(sc.cost_per_carton)} / carton, {formatDays(sc.lead_time_days)} lead time
                      </span>
                    </div>
                    <p className="text-meta text-ink-2 mt-0.5 leading-relaxed">
                      {sc.reason ||
                        (isEligible
                          ? 'Eligible candidate subject to network constraints'
                          : 'Excluded by constraints')}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* SECTION 2: Checks */}
        <div className="flex flex-col gap-3 pb-5 border-b border-line">
          <h3 className="text-section font-serif font-semibold text-ink">Checks</h3>
          <div className="w-full border-t border-line divide-y divide-line text-body">
            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Batch stock availability</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.stock?.detail || 'Verified'}
              </span>
            </div>

            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Lead time gap</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.lead_time_gap?.detail || 'Verified'}
              </span>
            </div>

            <div className="py-2.5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />
                <span className="text-ink font-medium">Lane load capacity</span>
              </div>
              <span className="text-meta text-right tabular-nums text-ink-2">
                {checks.lane_capacity?.detail || 'Within lane limit'}
              </span>
            </div>

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

        {/* SECTION 3: What is still uncovered */}
        <div className="flex flex-col gap-3">
          <h3 className="text-section font-serif font-semibold text-ink">
            What is still uncovered
          </h3>
          <div className="border-t border-line divide-y divide-line text-body">
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-ink-2">Unmet demand</span>
              <span className="font-semibold tabular-nums">
                {residualRisk.unmet_demand_cartons > 0 ? (
                  <span className="text-madder">
                    {formatCartons(residualRisk.unmet_demand_cartons)}
                  </span>
                ) : (
                  <span className="text-ok">0 cartons</span>
                )}
              </span>
            </div>
            <div className="py-2.5 flex items-center justify-between">
              <span className="text-ink-2">Safety-stock gap</span>
              <span className="font-semibold tabular-nums">
                {residualRisk.safety_stock_gap_cartons > 0 ? (
                  <span className="text-turmeric">
                    {formatCartons(residualRisk.safety_stock_gap_cartons)}
                  </span>
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
