import React, { useState } from 'react';
import {
  Button,
  Field,
  Input,
  Select,
  Badge,
  DataTable,
  Drawer,
  Modal,
  Tabs,
  Stat,
  InlineMessage,
  EmptyState,
  Skeleton,
  Tooltip,
  useToast,
  formatINR,
  formatCartons,
  formatDate,
  formatDays,
} from '../components/ui';
import {
  Check,
  AlertTriangle,
  AlertCircle,
  Package,
  Layers,
  ArrowRight,
  Truck,
  RotateCcw,
} from 'lucide-react';

export function DesignSystemPage() {
  const { toast } = useToast();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('components');
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');

  const sampleData = [
    { id: '1', product: 'Atta 10kg', from: 'W1', to: 'D1', cartons: 45, cost: 4500, arrives: '26 Oct 2026', flag: 'Heuristic' },
    { id: '2', product: 'Mustard Oil 1L', from: 'W1', to: 'D2', cartons: 20, cost: 2400, arrives: '25 Oct 2026', flag: 'Uneconomic' },
    { id: '3', product: 'Bath Soap 125g', from: 'W2', to: 'S1', cartons: 80, cost: 6800, arrives: '27 Oct 2026', flag: 'Arrives late' },
    { id: '4', product: 'Basmati Rice 5kg', from: 'W2', to: 'S2', cartons: 35, cost: 3850, arrives: '26 Oct 2026', flag: 'None' },
  ];

  const columns = [
    { key: 'product', header: 'Product' },
    { key: 'from', header: 'From' },
    { key: 'to', header: 'To' },
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
    { key: 'arrives', header: 'Arrives' },
    {
      key: 'flag',
      header: 'Flags',
      render: (r: any) =>
        r.flag !== 'None' ? (
          <Badge
            variant={r.flag === 'Arrives late' ? 'madder' : 'turmeric'}
            icon={<AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />}
          >
            {r.flag}
          </Badge>
        ) : (
          <Badge variant="ok" icon={<Check className="w-3.5 h-3.5" strokeWidth={1.5} />}>
            Standard
          </Badge>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-10">
      {/* Intro Header */}
      <section className="flex flex-col gap-2 pb-6 border-b border-line">
        <h2 className="text-page-title font-serif font-bold text-ink">
          VyaparMitra Design System
        </h2>
        <p className="text-body text-ink-2 max-w-2xl leading-relaxed">
          Inspired by regional Indian FMCG distribution ledgers and godown slips: ruled rows, right-aligned tabular figures, calm tones, and disciplined contrast.
        </p>
      </section>

      {/* Tabs */}
      <Tabs
        items={[
          { id: 'components', label: 'Component Kit' },
          { id: 'tokens', label: 'Color Tokens & Contrast' },
          { id: 'typography', label: 'Typography Scale' },
          { id: 'helpers', label: 'Indian Formatters' },
        ]}
        activeId={activeTab}
        onChange={setActiveTab}
      />

      {/* 1. COMPONENTS TAB */}
      {activeTab === 'components' && (
        <div className="flex flex-col gap-10">
          {/* Buttons Section */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">Buttons</h3>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="primary">Primary action</Button>
              <Button variant="secondary">Secondary action</Button>
              <Button variant="quiet">Quiet action</Button>
              <Button variant="danger">Danger action</Button>
              <Button variant="primary" loading>Loading state</Button>
              <Button variant="secondary" disabled>Disabled state</Button>
              <Button
                variant="primary"
                icon={<Package className="w-4 h-4" strokeWidth={1.5} />}
              >
                With icon
              </Button>
            </div>
          </section>

          {/* Form Fields Section */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">Form Fields & Inputs</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl">
              <Field label="Planning horizon (days)" hint="Default horizon is 7 calendar days">
                <Input type="number" defaultValue={7} />
              </Field>
              <Field label="Warehouse origin" error="Warehouse W1 has insufficient stock">
                <Select error defaultValue="W1">
                  <option value="W1">W1, Gurgaon Godown</option>
                  <option value="W2">W2, Bhiwandi Godown</option>
                </Select>
              </Field>
              <Field label="Read-only parameter">
                <Input disabled defaultValue="Fixed constraint" />
              </Field>
            </div>
          </section>

          {/* Badges Section */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">
              Badges (Always Icon + Text)
            </h3>
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant="neutral" icon={<Layers className="w-3.5 h-3.5" strokeWidth={1.5} />}>
                Neutral batch
              </Badge>
              <Badge variant="brand" icon={<Truck className="w-3.5 h-3.5" strokeWidth={1.5} />}>
                VyaparMitra route
              </Badge>
              <Badge variant="turmeric" icon={<AlertTriangle className="w-3.5 h-3.5" strokeWidth={1.5} />}>
                Uneconomic lane
              </Badge>
              <Badge variant="madder" icon={<AlertCircle className="w-3.5 h-3.5" strokeWidth={1.5} />}>
                Arrives late
              </Badge>
              <Badge variant="ok" icon={<Check className="w-3.5 h-3.5" strokeWidth={1.5} />}>
                Optimal allocation
              </Badge>
            </div>
          </section>

          {/* Inline Messages Section */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">Inline Messages</h3>
            <div className="flex flex-col gap-3 max-w-3xl">
              <InlineMessage severity="info">
                This plan was generated using rolling 7-day sales cross-validation.
              </InlineMessage>
              <InlineMessage severity="warning">
                Lane W1 to D2 capacity reached. 15 cartons rerouted to W2.
              </InlineMessage>
              <InlineMessage
                severity="error"
                action={
                  <Button size="sm" variant="danger">
                    Correct
                  </Button>
                }
              >
                Warehouse W1 holds 90 cartons. Edit requested 95 cartons.
              </InlineMessage>
              <InlineMessage severity="success">
                All 60 critical and warning constraints satisfied.
              </InlineMessage>
            </div>
          </section>

          {/* Data Table Section */}
          <section className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="text-section font-serif font-semibold text-ink">
                Ledger Data Table
              </h3>
              <div className="flex items-center gap-2 text-meta text-ink-2">
                <span>Row density:</span>
                <button
                  type="button"
                  onClick={() => setDensity(density === 'comfortable' ? 'compact' : 'comfortable')}
                  className="px-2.5 py-1 border border-line-strong rounded-control bg-surface text-ink font-medium hover:bg-paper"
                >
                  {density === 'comfortable' ? 'Comfortable (44px)' : 'Compact (36px)'}
                </button>
              </div>
            </div>
            <DataTable
              columns={columns}
              data={sampleData}
              keyExtractor={(r) => r.id}
              density={density}
              onRowClick={() => setDrawerOpen(true)}
            />
          </section>

          {/* Overlays Section */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">Overlays & Notifications</h3>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
                Open dispatch slip drawer
              </Button>
              <Button variant="secondary" onClick={() => setModalOpen(true)}>
                Open confirmation modal
              </Button>
              <Button
                variant="secondary"
                onClick={() =>
                  toast({
                    type: 'success',
                    message: 'Line approved: 45 cartons to D1',
                    undoAction: () =>
                      toast({ type: 'info', message: 'Action undone for D1' }),
                    undoLabel: 'Undo',
                  })
                }
              >
                Trigger toast with Undo
              </Button>
              <Tooltip content="Tooltip explaining that this role cannot approve lines">
                <Button variant="quiet">Hover for tooltip</Button>
              </Tooltip>
            </div>
          </section>

          {/* Empty & Skeleton States */}
          <section className="flex flex-col gap-4">
            <h3 className="text-section font-serif font-semibold text-ink">Empty & Skeleton States</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <EmptyState
                title="No plan yet"
                description="Generate one to see what moves where."
                action={<Button variant="primary">Generate plan</Button>}
              />
              <div className="p-6 border border-line bg-surface rounded-control flex flex-col gap-3">
                <span className="text-meta font-medium text-ink-2">Table-shaped skeletons</span>
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          </section>
        </div>
      )}

      {/* 2. TOKENS TAB */}
      {activeTab === 'tokens' && (
        <div className="flex flex-col gap-6">
          <h3 className="text-section font-serif font-semibold text-ink">Color Palette & Role</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 border border-line rounded-control bg-paper">
              <div className="h-10 bg-paper border border-line rounded-chip mb-2" />
              <div className="font-semibold text-body">Paper (#F5F6F4)</div>
              <div className="text-meta text-ink-2">Base page background</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-surface border border-line rounded-chip mb-2" />
              <div className="font-semibold text-body">Surface (#FFFFFF)</div>
              <div className="text-meta text-ink-2">Cards, tables, modals</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-ink rounded-chip mb-2" />
              <div className="font-semibold text-body">Ink (#16202A)</div>
              <div className="text-meta text-ink-2">Primary text & headers (16:1)</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-brand rounded-chip mb-2" />
              <div className="font-semibold text-body">Brand (#0F5C4D)</div>
              <div className="text-meta text-ink-2">Actions & focus states (7.9:1)</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-turmeric rounded-chip mb-2" />
              <div className="font-semibold text-body">Turmeric (#B37400)</div>
              <div className="text-meta text-ink-2">Flags & attention (3.9:1 border)</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-madder rounded-chip mb-2" />
              <div className="font-semibold text-body">Madder (#A3344F)</div>
              <div className="text-meta text-ink-2">Shortfall & errors (6.6:1)</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-ok rounded-chip mb-2" />
              <div className="font-semibold text-body">OK (#2E7D4F)</div>
              <div className="text-meta text-ink-2">Pass & fulfillment (5.0:1)</div>
            </div>
            <div className="p-4 border border-line rounded-control bg-surface">
              <div className="h-10 bg-line-strong rounded-chip mb-2" />
              <div className="font-semibold text-body">Line Strong (#7E8E9E)</div>
              <div className="text-meta text-ink-2">UI control borders (3.3:1)</div>
            </div>
          </div>
        </div>
      )}

      {/* 3. TYPOGRAPHY TAB */}
      {activeTab === 'typography' && (
        <div className="flex flex-col gap-6 max-w-3xl">
          <h3 className="text-section font-serif font-semibold text-ink">Type Hierarchy</h3>
          <div className="flex flex-col gap-4 border border-line p-6 bg-surface rounded-control">
            <div>
              <div className="text-meta text-ink-3">Display 40px (Source Serif 4, only on Evaluate)</div>
              <div className="text-display font-serif font-bold tabular-nums">98.4%</div>
            </div>
            <div className="border-t border-line pt-4">
              <div className="text-meta text-ink-3">Page Title 28px (Source Serif 4)</div>
              <div className="text-page-title font-serif font-semibold">Distribution Plan</div>
            </div>
            <div className="border-t border-line pt-4">
              <div className="text-meta text-ink-3">Section Title 20px (Source Serif 4)</div>
              <div className="text-section font-serif font-semibold">Dispatch Register</div>
            </div>
            <div className="border-t border-line pt-4">
              <div className="text-meta text-ink-3">Body 14px (Public Sans)</div>
              <div className="text-body text-ink">
                Every carton is routed according to shelf-life eligibility, lead time gaps, and warehouse inventory positions.
              </div>
            </div>
            <div className="border-t border-line pt-4">
              <div className="text-meta text-ink-3">Meta 12px (Public Sans)</div>
              <div className="text-meta text-ink-2 tabular-nums">
                Data as of 24 Oct 2026, 24 products, 6 locations
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 4. HELPERS TAB */}
      {activeTab === 'helpers' && (
        <div className="flex flex-col gap-6 max-w-2xl">
          <h3 className="text-section font-serif font-semibold text-ink">Formatters (en-IN)</h3>
          <div className="border border-line rounded-control bg-surface p-6 flex flex-col gap-4">
            <div className="flex justify-between items-center py-2 border-b border-line">
              <span className="text-body font-medium">formatINR(105000)</span>
              <span className="tabular-nums font-semibold">{formatINR(105000)}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-line">
              <span className="text-body font-medium">formatCartons(45)</span>
              <span className="tabular-nums font-semibold">{formatCartons(45)}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-line">
              <span className="text-body font-medium">formatDate('2026-10-24')</span>
              <span className="tabular-nums font-semibold">{formatDate('2026-10-24')}</span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-body font-medium">formatDays(3)</span>
              <span className="tabular-nums font-semibold">{formatDays(3)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Drawer Demo */}
      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="W1 to D2, 20 cartons"
        subtitle="Mustard Oil 1L, standard dispatch"
        footer={
          <>
            <Button variant="secondary" onClick={() => setDrawerOpen(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setDrawerOpen(false);
                toast({ type: 'success', message: 'Line approved' });
              }}
            >
              Approve line
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <h4 className="text-body font-semibold text-ink">Sources considered</h4>
          <p className="text-meta text-ink-2">
            W1 selected (cost ₹ 2,400, lead time 1 day). W2 excluded: lead time gap 2 days exceeds limit.
          </p>
        </div>
      </Drawer>

      {/* Modal Demo */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Discard current plan?"
        description="This will clear the active plan and require re-running optimization."
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Keep plan
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setModalOpen(false);
                toast({ type: 'info', message: 'Plan discarded' });
              }}
            >
              Discard plan
            </Button>
          </>
        }
      >
        <p className="text-body text-ink-2 leading-relaxed">
          Unsaved adjustments to cartons will be lost.
        </p>
      </Modal>
    </div>
  );
}
