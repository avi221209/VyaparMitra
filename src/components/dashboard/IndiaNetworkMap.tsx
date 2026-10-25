import React, { useState, useMemo } from 'react';
import { geoMercator, geoPath } from 'd3-geo';
import indiaGeoJson from '../../data/india-boundary.json';

export interface NetworkNode {
  id: string;
  name: string;
  type: string;
  city?: string | null;
  state?: string | null;
  lat?: number | null;
  lon?: number | null;
  stock_units: number;
  unmet_cartons: number;
  high_demand: boolean;
}

export interface NetworkFlow {
  from_id: string;
  to_id: string;
  cartons: number;
  line_count: number;
}

export interface IndiaNetworkMapProps {
  nodes: NetworkNode[];
  flows: NetworkFlow[];
  unmapped?: string[];
}

export function IndiaNetworkMap({ nodes, flows, unmapped = [] }: IndiaNetworkMapProps) {
  const [activeTooltip, setActiveTooltip] = useState<{
    x: number;
    y: number;
    content: React.ReactNode;
  } | null>(null);

  const width = 560;
  const height = 540;

  // Set up d3-geo projection fitted to the India GeoJSON boundary
  const { pathData, projection } = useMemo(() => {
    const proj = geoMercator();
    proj.fitExtent(
      [
        [20, 20],
        [width - 20, height - 20],
      ],
      indiaGeoJson as any
    );
    const pathGenerator = geoPath().projection(proj);
    const d = pathGenerator(indiaGeoJson as any) || '';
    return { pathData: d, projection: proj };
  }, [width, height]);

  // Project nodes to (x, y) coordinates
  const projectedNodes = useMemo(() => {
    return nodes
      .map((node) => {
        if (node.lat == null || node.lon == null) return null;
        const coords = projection([node.lon, node.lat]);
        if (!coords) return null;
        return {
          ...node,
          x: coords[0],
          y: coords[1],
        };
      })
      .filter((n): n is NetworkNode & { x: number; y: number } => n !== null);
  }, [nodes, projection]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, NetworkNode & { x: number; y: number }>();
    projectedNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [projectedNodes]);

  // Max cartons for proportional stroke calculation
  const maxCartons = useMemo(() => {
    if (flows.length === 0) return 1;
    return Math.max(...flows.map((f) => f.cartons), 1);
  }, [flows]);

  return (
    <div className="relative w-full h-[540px] bg-[#F7FAF8] rounded-control border border-line/80 overflow-hidden flex items-center justify-center select-none">
      {/* Legend Top-Right */}
      <div className="absolute top-3 right-3 bg-surface/95 backdrop-blur-sm p-3 rounded-control border border-line shadow-sm z-10 text-[11.5px] flex flex-col gap-2">
        <div className="font-semibold text-ink text-meta uppercase tracking-wider text-[10px] mb-0.5">
          Map Legend
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3.5 h-3.5 rounded-[2px] bg-brand border border-surface shadow-xs shrink-0" />
          <span className="text-ink-2">Warehouse</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-brand border border-surface shadow-xs shrink-0" />
          <span className="text-ink-2">Retailer / Depot</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-madder border border-surface shadow-xs shrink-0" />
          <span className="text-ink-2">High Demand / Shortage</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-0.5 bg-brand relative shrink-0">
            <div className="absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0 border-y-2 border-y-transparent border-l-[4px] border-l-brand" />
          </div>
          <span className="text-ink-2">Planned Dispatch</span>
        </div>
      </div>

      {/* Screen Reader Summary */}
      <div className="sr-only">
        Interactive distribution map of India showing {nodes.length} locations and {flows.length} planned shipment routes.
        {nodes.map((n) => `${n.name} in ${n.city || 'unmapped'} with ${n.stock_units} units stock.`).join(' ')}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full"
        aria-hidden="true"
        onMouseLeave={() => setActiveTooltip(null)}
      >
        <defs>
          {/* Arrowhead marker for planned dispatches */}
          <marker
            id="dispatch-arrow"
            viewBox="0 0 10 10"
            refX="6"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 1 L 9 5 L 0 9 z" fill="#0F5C4D" />
          </marker>
        </defs>

        {/* India Boundary SVG polygon */}
        <path
          d={pathData}
          fill="#EAF1ED"
          stroke="#9BB0A5"
          strokeWidth="1.2"
          className="transition-colors"
        />

        {/* Shipment Flows (Curved Bezier Lines with Arrowheads) */}
        {flows.map((flow, idx) => {
          const fromNode = nodeMap.get(flow.from_id);
          const toNode = nodeMap.get(flow.to_id);
          if (!fromNode || !toNode) return null;

          // Compute midpoint with curved control point
          const dx = toNode.x - fromNode.x;
          const dy = toNode.y - fromNode.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          // Perpendicular offset for curve
          const offset = Math.min(35, Math.max(15, dist * 0.15));
          const mx = (fromNode.x + toNode.x) / 2 - (dy / dist) * offset;
          const my = (fromNode.y + toNode.y) / 2 + (dx / dist) * offset;

          const strokeW = Math.max(1.5, Math.min(5.5, (flow.cartons / maxCartons) * 5.5));
          const pathD = `M ${fromNode.x} ${fromNode.y} Q ${mx} ${my} ${toNode.x} ${toNode.y}`;

          return (
            <g key={`flow-${idx}`} className="group cursor-pointer">
              {/* Invisible wider hover path */}
              <path
                d={pathD}
                fill="none"
                stroke="transparent"
                strokeWidth={14}
                onMouseEnter={(e) => {
                  const rect = e.currentTarget.ownerSVGElement?.getBoundingClientRect();
                  setActiveTooltip({
                    x: (fromNode.x + toNode.x) / 2,
                    y: (fromNode.y + toNode.y) / 2,
                    content: (
                      <div>
                        <div className="font-semibold text-ink">
                          {fromNode.name} → {toNode.name}
                        </div>
                        <div className="text-meta text-brand font-medium mt-0.5">
                          {flow.cartons.toLocaleString('en-IN')} cartons ({flow.line_count} SKUs)
                        </div>
                      </div>
                    ),
                  });
                }}
              />
              {/* Visible animated dispatch flow */}
              <path
                d={pathD}
                fill="none"
                stroke="#0F5C4D"
                strokeWidth={strokeW}
                strokeOpacity={0.65}
                markerEnd="url(#dispatch-arrow)"
                className="group-hover:stroke-opacity-100 group-hover:stroke-brand transition-all"
              />
            </g>
          );
        })}

        {/* Network Nodes (Warehouses & Retailers) */}
        {projectedNodes.map((node) => {
          const isWarehouse = node.type === 'warehouse';
          const isAlert = node.high_demand || node.unmet_cartons > 0;

          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={`${node.name}, ${node.city || ''}`}
              className="group cursor-pointer outline-none focus:scale-125 transition-transform"
              onMouseEnter={() => {
                setActiveTooltip({
                  x: node.x,
                  y: node.y,
                  content: (
                    <div>
                      <div className="font-semibold text-ink flex items-center gap-1.5">
                        <span>{node.name}</span>
                        <span className="text-[10px] text-ink-3 uppercase">({node.id})</span>
                      </div>
                      <div className="text-meta text-ink-2 mt-0.5">
                        City: <span className="font-medium text-ink">{node.city || '—'}</span> ({node.type})
                      </div>
                      <div className="text-meta text-ink-2 mt-0.5">
                        On-hand: <span className="font-medium text-ink tabular-nums">{node.stock_units.toLocaleString('en-IN')}</span> units
                      </div>
                      {node.unmet_cartons > 0 && (
                        <div className="text-meta text-madder font-semibold mt-0.5">
                          Shortfall: {node.unmet_cartons.toLocaleString('en-IN')} cartons
                        </div>
                      )}
                      {node.high_demand && (
                        <div className="text-meta text-turmeric font-semibold mt-0.5">
                          High demand forecast (&gt;20% above baseline)
                        </div>
                      )}
                    </div>
                  ),
                });
              }}
            >
              {/* Node Marker */}
              {isWarehouse ? (
                // Warehouse: Green rounded square
                <rect
                  x={node.x - 7}
                  y={node.y - 7}
                  width={14}
                  height={14}
                  rx={3}
                  fill="#0F5C4D"
                  stroke="#FFFFFF"
                  strokeWidth={2}
                  className="filter drop-shadow-sm group-hover:fill-[#0A3D33] transition-colors"
                />
              ) : (
                // Retailer: Green dot, or Red dot if high demand / unmet
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={isAlert ? 6 : 5}
                  fill={isAlert ? '#A3344F' : '#0F5C4D'}
                  stroke="#FFFFFF"
                  strokeWidth={2}
                  className="filter drop-shadow-sm group-hover:scale-125 transition-transform"
                />
              )}

              {/* City Label Beside Pin with Readable Background */}
              <text
                x={node.x + 9}
                y={node.y + 3.5}
                className="text-[11px] font-sans font-medium fill-ink select-none pointer-events-none"
                style={{
                  paintOrder: 'stroke fill',
                  stroke: '#F7FAF8',
                  strokeWidth: 3,
                  strokeLinejoin: 'round',
                }}
              >
                {node.city || node.id}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Interactive Tooltip Card */}
      {activeTooltip && (
        <div
          className="absolute pointer-events-none bg-surface/95 backdrop-blur-md px-3.5 py-2.5 rounded-control border border-line shadow-overlay z-20 text-body max-w-xs transition-opacity duration-150 animate-fade-in"
          style={{
            left: `${Math.min(activeTooltip.x + 12, width - 180)}px`,
            top: `${Math.max(activeTooltip.y - 45, 10)}px`,
          }}
        >
          {activeTooltip.content}
        </div>
      )}

      {/* Unmapped Nodes Note if Any */}
      {unmapped.length > 0 && (
        <div className="absolute bottom-3 left-3 bg-surface/90 text-[11px] text-ink-3 px-2 py-1 rounded border border-line z-10">
          Unmapped locations: {unmapped.join(', ')}
        </div>
      )}
    </div>
  );
}

export default IndiaNetworkMap;
