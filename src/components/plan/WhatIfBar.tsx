import React, { useState } from 'react';
import { Button, Select, Input, formatINR, formatCartons } from '../ui';
import { ArrowRight, Sliders, RefreshCw } from 'lucide-react';

export interface ChangeSummary {
  before: {
    transport_cost: number;
    unmet_demand_cartons: number;
    cost_to_serve?: number;
  };
  after: {
    transport_cost: number;
    unmet_demand_cartons: number;
    cost_to_serve?: number;
  };
  diff_unmet_cartons: number;
  diff_transport_cost: number;
  diff_cost_to_serve?: number;
}

export interface WhatIfBarProps {
  onRegenerate: (payload: any) => Promise<ChangeSummary | null>;
  isGenerating: boolean;
}

export function WhatIfBar({ onRegenerate, isGenerating }: WhatIfBarProps) {
  const [overrideType, setOverrideType] = useState<'source' | 'destination'>('source');
  const [sourceId, setSourceId] = useState('W1');
  const [sourcePct, setSourcePct] = useState(-20); // Default minus 20%
  const [destinationId, setDestinationId] = useState('D1');
  const [demandMultiplier, setDemandMultiplier] = useState(1.2);
  const [includeSurplus, setIncludeSurplus] = useState(false);
  const [changeSummary, setChangeSummary] = useState<ChangeSummary | null>(null);

  const handleApply = async () => {
    let payload: any = {
      include_surplus: includeSurplus,
    };
    if (overrideType === 'source') {
      const multiplier = (100 + sourcePct) / 100;
      payload.source_overrides = {
        [sourceId]: { mode: 'multiplier', value: multiplier },
      };
    } else {
      payload.destination_overrides = {
        [destinationId]: { mode: 'multiplier', value: demandMultiplier },
      };
    }

    const summary = await onRegenerate(payload);
    if (summary) {
      setChangeSummary(summary);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Control bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-surface border-y border-line text-body select-none">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-meta font-medium text-ink-2">
            <Sliders className="w-4 h-4 text-ink-3" strokeWidth={1.5} />
            <span>Scenario what-if:</span>
          </div>

          <Select
            value={overrideType}
            onChange={(e) => setOverrideType(e.target.value as any)}
            className="h-8 text-meta"
          >
            <option value="source">Warehouse stock adjustment</option>
            <option value="destination">Destination demand shift</option>
          </Select>

          {overrideType === 'source' ? (
            <div className="flex items-center gap-2">
              <Select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="h-8 text-meta"
              >
                <option value="W1">W1, Gurgaon Godown</option>
                <option value="W2">W2, Bhiwandi Godown</option>
              </Select>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  value={sourcePct}
                  onChange={(e) => setSourcePct(parseInt(e.target.value) || 0)}
                  className="w-16 h-8 text-meta"
                />
                <span className="text-meta text-ink-2">%</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Select
                value={destinationId}
                onChange={(e) => setDestinationId(e.target.value)}
                className="h-8 text-meta"
              >
                <option value="D1">D1, Kolkata Distributor</option>
                <option value="D2">D2, Ahmedabad Distributor</option>
                <option value="S1">S1, Bengaluru Flagship</option>
                <option value="S2">S2, Pune Mart</option>
              </Select>
              <div className="flex items-center gap-1">
                <Input
                  type="number"
                  step="0.1"
                  value={demandMultiplier}
                  onChange={(e) => setDemandMultiplier(parseFloat(e.target.value) || 1.0)}
                  className="w-16 h-8 text-meta"
                />
                <span className="text-meta text-ink-2">x</span>
              </div>
            </div>
          )}

          {/* Include verified surplus toggle */}
          <div className="h-4 w-px bg-line hidden sm:block" />
          <label className="flex items-center gap-2 text-meta font-medium text-ink cursor-pointer select-none">
            <input
              type="checkbox"
              id="toggle-include-surplus"
              checked={includeSurplus}
              onChange={(e) => setIncludeSurplus(e.target.checked)}
              className="h-4 w-4 rounded border-line text-brand accent-brand focus:ring-brand"
            />
            <span>Include verified surplus</span>
          </label>
        </div>

        <Button
          variant="secondary"
          size="sm"
          loading={isGenerating}
          onClick={handleApply}
        >
          Regenerate
        </Button>
      </div>

      {/* Change Summary Band: three aligned columns with differences written in words */}
      {changeSummary && (
        <div className="p-4 border-b border-line bg-surface flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 select-none">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 w-full sm:w-auto">

            {/* Unmet Units Column */}
            <div>
              <span className="text-meta text-ink-3 block">Unmet demand change</span>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="tabular-nums font-medium text-ink-2">
                  {formatCartons(changeSummary.before.unmet_demand_cartons)}
                </span>
                <span className="text-ink-3 text-meta">to</span>
                <span className="tabular-nums font-semibold text-ink">
                  {formatCartons(changeSummary.after.unmet_demand_cartons)}
                </span>
              </div>
              <span className="text-meta text-ink font-medium mt-1 block">
                {changeSummary.diff_unmet_cartons > 0
                  ? `${changeSummary.diff_unmet_cartons} more cartons unmet`
                  : changeSummary.diff_unmet_cartons < 0
                  ? `${Math.abs(changeSummary.diff_unmet_cartons)} fewer cartons unmet`
                  : 'Unmet cartons unchanged'}
              </span>
            </div>

            {/* Transport Cost Column */}
            <div>
              <span className="text-meta text-ink-3 block">Transport cost change</span>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="tabular-nums font-medium text-ink-2">
                  {formatINR(changeSummary.before.transport_cost)}
                </span>
                <span className="text-ink-3 text-meta">to</span>
                <span className="tabular-nums font-semibold text-ink">
                  {formatINR(changeSummary.after.transport_cost)}
                </span>
              </div>
              <span className="text-meta text-ink font-medium mt-1 block">
                {changeSummary.diff_transport_cost > 0
                  ? `${formatINR(changeSummary.diff_transport_cost)} extra transport cost`
                  : changeSummary.diff_transport_cost < 0
                  ? `${formatINR(Math.abs(changeSummary.diff_transport_cost))} transport cost saved`
                  : 'Transport cost unchanged'}
              </span>
            </div>

            {/* Cost-to-Serve Column */}
            <div>
              <span className="text-meta text-ink-3 block">Total cost-to-serve change</span>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="tabular-nums font-medium text-ink-2">
                  {formatINR(changeSummary.before.cost_to_serve || 0)}
                </span>
                <span className="text-ink-3 text-meta">to</span>
                <span className="tabular-nums font-semibold text-ink">
                  {formatINR(changeSummary.after.cost_to_serve || 0)}
                </span>
              </div>
              <span className="text-meta text-ink font-medium mt-1 block">
                {changeSummary.diff_cost_to_serve !== undefined
                  ? changeSummary.diff_cost_to_serve > 0
                    ? `${formatINR(changeSummary.diff_cost_to_serve)} higher cost-to-serve`
                    : changeSummary.diff_cost_to_serve < 0
                    ? `${formatINR(Math.abs(changeSummary.diff_cost_to_serve))} saved in cost-to-serve`
                    : 'Cost-to-serve unchanged'
                  : '—'}
              </span>
            </div>
          </div>

          <Button
            size="sm"
            variant="quiet"
            onClick={() => setChangeSummary(null)}
          >
            Dismiss
          </Button>
        </div>
      )}
    </div>
  );
}
