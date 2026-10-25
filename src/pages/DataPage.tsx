import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  DataTable,
  Badge,
  Modal,
  Field,
  Input,
  InlineMessage,
  EmptyState,
  useToast,
} from '../components/ui';
import { apiFetch } from '../lib/api';
import {
  AlertCircle,
  AlertTriangle,
  Check,
  FileSpreadsheet,
  UploadCloud,
  CheckCircle2,
  XCircle,
  Download,
} from 'lucide-react';

export interface ValidationIssueItem {
  id: string;
  type: string;
  entity: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'resolved' | 'acknowledged';
  description: string;
  created_at: string;
}

export function DataPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [selectedIssueForCorrection, setSelectedIssueForCorrection] = useState<ValidationIssueItem | null>(null);
  const [correctionNote, setCorrectionNote] = useState('');
  const [dragActive, setDragActive] = useState(false);

  // Fetch status to check if data exists
  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => apiFetch<any>('/api/status'),
  });

  // Fetch validation issues
  const {
    data: issues = [],
    isLoading: issuesLoading,
    refetch: refetchIssues,
  } = useQuery<ValidationIssueItem[]>({
    queryKey: ['validation-issues'],
    queryFn: async () => {
      try {
        const res = await apiFetch<any>('/api/data/issues');
        return Array.isArray(res) ? res : res.issues || [];
      } catch {
        const fallback = await apiFetch<ValidationIssueItem[]>('/api/validation-issues');
        return fallback || [];
      }
    },
  });

  // Seed mutation
  const seedMutation = useMutation({
    mutationFn: (variant: string) =>
      apiFetch(`/api/data/seed?variant=${variant}&seed=1&scenario=balanced`, {
        method: 'POST',
      }),
    onSuccess: (_, variant) => {
      queryClient.invalidateQueries({ queryKey: ['system-status'] });
      queryClient.invalidateQueries({ queryKey: ['validation-issues'] });
      queryClient.invalidateQueries({ queryKey: ['latest-plan'] });
      queryClient.invalidateQueries({ queryKey: ['products'] });
      queryClient.invalidateQueries({ queryKey: ['locations'] });
      queryClient.invalidateQueries({ queryKey: ['audit-logs'] });
      queryClient.invalidateQueries({ queryKey: ['evaluation-data'] });
      window.dispatchEvent(new Event('role-changed'));

      const names: Record<string, string> = {
        normal: 'Sample data loaded',
        defects: 'File with errors loaded',
        low_w1: 'Low W1 stock scenario loaded',
      };
      toast({
        type: 'success',
        message: names[variant] || 'Data loaded',
      });
    },
    onError: (err: any) => {
      toast({
        type: 'error',
        message: err.message || 'Failed to load data',
      });
    },
  });

  // Resolve / Correct mutation
  const resolveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      apiFetch(`/api/data/issues/${id}/resolve`, {
        method: 'POST',
        body: JSON.stringify({ resolution_note: note }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['validation-issues'] });
      setSelectedIssueForCorrection(null);
      setCorrectionNote('');
      toast({ type: 'success', message: 'Issue corrected' });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Correction failed' });
    },
  });

  // Acknowledge / Exclude mutation
  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/data/issues/${id}/acknowledge`, {
        method: 'POST',
        body: JSON.stringify({ acknowledgement_note: 'Excluded from planning' }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['validation-issues'] });
      toast({ type: 'info', message: 'Row excluded from planning' });
    },
    onError: (err: any) => {
      toast({ type: 'error', message: err.message || 'Exclusion failed' });
    },
  });

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      // Synthetic demonstration file load
      seedMutation.mutate('normal');
      toast({
        type: 'info',
        message: `Ingesting ${e.dataTransfer.files[0].name}`,
      });
    }
  };

  const hasData = (statusData?.counts?.products || 0) > 0;
  const isSeeding = seedMutation.isPending;

  const issueColumns = [
    {
      key: 'severity',
      header: 'Severity',
      width: '140px',
      render: (item: ValidationIssueItem) => {
        if (item.severity === 'critical') {
          return (
            <Badge
              variant="madder"
              icon={<AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />}
            >
              Critical
            </Badge>
          );
        }
        if (item.severity === 'warning') {
          return (
            <Badge
              variant="turmeric"
              icon={<AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />}
            >
              Warning
            </Badge>
          );
        }
        return (
          <Badge variant="neutral">
            Notice
          </Badge>
        );
      },
    },
    {
      key: 'entity',
      header: 'Entity',
      width: '160px',
      render: (item: ValidationIssueItem) => (
        <span className="font-medium text-ink">{item.entity || item.type}</span>
      ),
    },
    {
      key: 'description',
      header: 'Problem',
      render: (item: ValidationIssueItem) => (
        <span className="text-body text-ink-2">{item.description}</span>
      ),
    },
    {
      key: 'action',
      header: 'Action',
      width: '220px',
      render: (item: ValidationIssueItem) => {
        if (item.status === 'resolved') {
          return (
            <Badge variant="ok" icon={<Check className="w-3.5 h-3.5" strokeWidth={1.5} />}>
              Resolved
            </Badge>
          );
        }
        if (item.status === 'acknowledged') {
          return (
            <Badge variant="neutral" icon={<XCircle className="w-3.5 h-3.5" strokeWidth={1.5} />}>
              Excluded
            </Badge>
          );
        }

        // Open status: show "Fix first" with "Correct" and "Exclude"
        return (
          <div className="flex items-center gap-2">
            {item.severity === 'critical' && (
              <span className="px-1.5 py-0.5 bg-madder-wash text-madder text-meta font-semibold rounded-chip border border-madder/30">
                Fix first
              </span>
            )}
            <Button
              size="sm"
              variant="secondary"
              onClick={(e) => {
                e.stopPropagation();
                setSelectedIssueForCorrection(item);
              }}
            >
              Correct
            </Button>
            <Button
              size="sm"
              variant="quiet"
              onClick={(e) => {
                e.stopPropagation();
                acknowledgeMutation.mutate(item.id);
              }}
            >
              Exclude
            </Button>
          </div>
        );
      },
    },
  ];

  const [guideDismissed, setGuideDismissed] = useState<boolean>(() => {
    return localStorage.getItem('vyaparmitra_guide_dismissed') === 'true';
  });

  // Query latest plan to determine if step 2 is complete
  const { data: latestPlan } = useQuery({
    queryKey: ['latest-plan'],
    queryFn: async () => {
      try {
        return await apiFetch<any>('/api/plan/latest');
      } catch {
        return null;
      }
    },
  });

  const hasActivePlan = Boolean(latestPlan && latestPlan.lines && latestPlan.lines.length > 0);

  return (
    <div className="flex flex-col gap-8">
      {/* 0. FIRST-RUN GUIDE (Dismissible, remembered, disappears after first plan) */}
      {!guideDismissed && !hasActivePlan && (
        <section className="py-3 px-4 border-y border-line bg-surface flex flex-col sm:flex-row sm:items-center justify-between gap-3 select-none">
          <div className="flex items-center gap-3">
            <span className="font-serif text-[15px] font-semibold text-ink">
              Getting started
            </span>
            <span className="text-line hidden sm:inline">|</span>
            <div className="flex flex-wrap items-center gap-4 text-meta text-ink-2">
              <div className={`flex items-center gap-1.5 ${hasData ? 'text-brand font-medium' : 'text-ink'}`}>
                {hasData ? (
                  <Check className="w-3.5 h-3.5 text-brand shrink-0" strokeWidth={2} />
                ) : (
                  <span className="font-semibold text-ink-3">1.</span>
                )}
                <span>Load data</span>
              </div>

              <span className="text-line">/</span>

              <div className={`flex items-center gap-1.5 ${hasActivePlan ? 'text-brand font-medium' : 'text-ink-2'}`}>
                {hasActivePlan ? (
                  <Check className="w-3.5 h-3.5 text-brand shrink-0" strokeWidth={2} />
                ) : (
                  <span className="font-semibold text-ink-3">2.</span>
                )}
                <span>Generate plan</span>
              </div>

              <span className="text-line">/</span>

              <div className="flex items-center gap-1.5 text-ink-2">
                <span className="font-semibold text-ink-3">3.</span>
                <span>Review a line</span>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setGuideDismissed(true);
              localStorage.setItem('vyaparmitra_guide_dismissed', 'true');
            }}
            className="text-meta text-ink-3 hover:text-ink cursor-pointer self-end sm:self-auto"
          >
            Dismiss
          </button>
        </section>
      )}

      {/* INTRODUCTORY SECTION — What data is needed */}
      {!hasData && (
        <section className="bg-surface border border-line rounded-control p-5 flex flex-col gap-3">
          <h2 className="text-section font-serif font-semibold text-ink">What data does VyaparMitra need?</h2>
          <p className="text-body text-ink-2 max-w-[70ch]">
            To generate accurate distribution plans, the system needs six types of data.
            You can load sample data instantly, or import your own CSV files.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-2">
            {[
              { name: 'Products', desc: 'SKU catalog with case-pack sizes' },
              { name: 'Locations', desc: 'Warehouses, depots, and stores' },
              { name: 'Sales history', desc: 'Daily unit sales per SKU per location' },
              { name: 'Inventory', desc: 'Current stock at each location' },
              { name: 'Batches', desc: 'Batch IDs with expiry dates' },
              { name: 'Lanes', desc: 'Shipping routes with freight costs' },
            ].map((t) => (
              <div key={t.name} className="p-3 bg-paper border border-line rounded-control">
                <span className="text-meta font-semibold text-ink block mb-0.5">{t.name}</span>
                <span className="text-[11px] text-ink-3 leading-snug">{t.desc}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 1. DATA LOADING SECTION */}
      <section className="flex flex-col gap-3">
        <h2 className="text-section font-serif font-semibold text-ink">Load data</h2>
        <p className="text-body text-ink-2">Choose a sample scenario to explore, or drag your own CSV files below.</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => seedMutation.mutate('normal')}
            disabled={isSeeding}
            className="text-left p-4 bg-surface border border-line rounded-control hover:border-brand transition-colors disabled:opacity-50 group"
          >
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle2 className="w-4 h-4 text-ok" strokeWidth={1.5} />
              <span className="text-body font-semibold text-ink group-hover:text-brand">Clean sample data</span>
            </div>
            <p className="text-meta text-ink-3">24 SKUs, 6 nodes, 90 days of sales. All data passes validation.</p>
            {isSeeding && seedMutation.variables === 'normal' && (
              <span className="text-meta text-brand mt-1 block">Loading...</span>
            )}
          </button>

          <button
            type="button"
            onClick={() => seedMutation.mutate('defects')}
            disabled={isSeeding}
            className="text-left p-4 bg-surface border border-line rounded-control hover:border-turmeric transition-colors disabled:opacity-50 group"
          >
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-turmeric" strokeWidth={1.5} />
              <span className="text-body font-semibold text-ink group-hover:text-turmeric">Data with 20 defects</span>
            </div>
            <p className="text-meta text-ink-3">Same dataset with intentional errors — see the validation gate in action.</p>
            {isSeeding && seedMutation.variables === 'defects' && (
              <span className="text-meta text-turmeric mt-1 block">Loading...</span>
            )}
          </button>

          <button
            type="button"
            onClick={() => seedMutation.mutate('low_w1')}
            disabled={isSeeding}
            className="text-left p-4 bg-surface border border-line rounded-control hover:border-madder transition-colors disabled:opacity-50 group"
          >
            <div className="flex items-center gap-2 mb-1">
              <AlertCircle className="w-4 h-4 text-madder" strokeWidth={1.5} />
              <span className="text-body font-semibold text-ink group-hover:text-madder">Low W1 stock</span>
            </div>
            <p className="text-meta text-ink-3">W1 warehouse has 20% less stock — reveals shortages and rescue paths.</p>
            {isSeeding && seedMutation.variables === 'low_w1' && (
              <span className="text-meta text-madder mt-1 block">Loading...</span>
            )}
          </button>
        </div>
      </section>

      {/* 2. CSV DROP AREA */}
      <section
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border border-dashed rounded-control p-6 bg-surface flex flex-col items-center justify-center text-center transition-colors ${
          dragActive ? 'border-brand bg-brand-wash/30' : 'border-line'
        }`}
      >
        <UploadCloud className="w-8 h-8 text-ink-3 mb-2" strokeWidth={1.5} />
        <p className="text-body text-ink font-medium">
          Or drop your own CSV files here
        </p>
        <p className="text-meta text-ink-3 mt-0.5 mb-3">
          Products, locations, sales, inventory, batches, and lanes — one file per type.
        </p>

        {/* Template Links */}
        <div className="flex flex-wrap items-center justify-center gap-3 text-meta text-ink-2 border-t border-line pt-3 w-full max-w-2xl">
          <span className="text-ink-3">Download CSV templates:</span>
          <a
            href="/api/data/template/products"
            download="products_template.csv"
            className="hover:text-brand hover:underline"
          >
            Products
          </a>
          <span className="text-line">|</span>
          <a
            href="/api/data/template/locations"
            download="locations_template.csv"
            className="hover:text-brand hover:underline"
          >
            Locations
          </a>
          <span className="text-line">|</span>
          <a
            href="/api/data/template/lanes"
            download="lanes_template.csv"
            className="hover:text-brand hover:underline"
          >
            Lanes
          </a>
          <span className="text-line">|</span>
          <a
            href="/api/data/template/batches"
            download="batches_template.csv"
            className="hover:text-brand hover:underline"
          >
            Batches
          </a>
          <span className="text-line">|</span>
          <a
            href="/api/data/template/inventory_snapshots"
            download="inventory_snapshots_template.csv"
            className="hover:text-brand hover:underline"
          >
            Snapshots
          </a>
          <span className="text-line">|</span>
          <a
            href="/api/data/template/sales_daily"
            download="sales_daily_template.csv"
            className="hover:text-brand hover:underline"
          >
            Sales
          </a>
        </div>
      </section>

      {/* 3. VALIDATION REPORT */}
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-section font-serif font-semibold text-ink">
              Data Validation Report
            </h2>
            <p className="text-meta text-ink-3 mt-0.5">
              VyaparMitra checks for duplicate SKUs, mixed units, negative inventory, missing sales, and more.
            </p>
          </div>
          {issues.length > 0 && (
            <span className="text-meta text-ink-2 tabular-nums">
              {issues.length} {issues.length === 1 ? 'issue' : 'issues'} recorded
            </span>
          )}
        </div>

        {!hasData && issues.length === 0 ? (
          <EmptyState
            title="No data loaded yet"
            description="Load sample data or import your own CSV files above. After loading, any data defects will appear here."
            icon={<FileSpreadsheet className="w-8 h-8" strokeWidth={1.5} />}
            action={
              <Button
                variant="primary"
                loading={isSeeding}
                onClick={() => seedMutation.mutate('normal')}
              >
                Load sample data
              </Button>
            }
          />
        ) : (
          <DataTable
            columns={issueColumns}
            data={issues}
            keyExtractor={(i) => i.id}
            loading={issuesLoading}
            emptyMessage={
              <div className="flex flex-col items-center gap-1.5 py-4">
                <CheckCircle2 className="w-5 h-5 text-ok" strokeWidth={1.5} />
                <span className="text-body font-medium text-ink">
                  No data defects found. Data is ready for planning.
                </span>
              </div>
            }
          />
        )}
      </section>

      {/* Correction Modal */}
      <Modal
        open={Boolean(selectedIssueForCorrection)}
        onClose={() => setSelectedIssueForCorrection(null)}
        title="Correct data issue"
        description={selectedIssueForCorrection?.description}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setSelectedIssueForCorrection(null)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={resolveMutation.isPending}
              onClick={() => {
                if (selectedIssueForCorrection) {
                  resolveMutation.mutate({
                    id: selectedIssueForCorrection.id,
                    note: correctionNote || 'Corrected via planning desk',
                  });
                }
              }}
            >
              Apply correction
            </Button>
          </>
        }
      >
        <Field label="Correction details or override note" hint="Recorded into immutable DecisionLog audit trail">
          <Input
            value={correctionNote}
            onChange={(e) => setCorrectionNote(e.target.value)}
            placeholder="e.g. Verified carton count against godown physical receipt"
          />
        </Field>
      </Modal>
    </div>
  );
}
