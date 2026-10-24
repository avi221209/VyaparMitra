import React, { useId } from 'react';

export interface LaneFlow {
  sourceId: string;
  sourceName: string;
  destinationId: string;
  destinationName: string;
  cartons: number;
}

export interface NodeUnmet {
  destinationId: string;
  unmetCartons: number;
}

export interface NetworkStripProps {
  flows: LaneFlow[];
  unmetMap: Record<string, number>;
  hoveredLaneKey: string | null;
  onHoverLane: (laneKey: string | null) => void;
  isOrchestrating?: boolean;
}

export function NetworkStrip({
  flows,
  unmetMap,
  hoveredLaneKey,
  onHoverLane,
  isOrchestrating = false,
}: NetworkStripProps) {
  const maskId = useId();

  // Network topology coordinates
  const warehouseCoords: Record<string, { x: number; y: number; label: string }> = {
    W1: { x: 70, y: 65, label: 'W1 Gurgaon' },
    W2: { x: 70, y: 155, label: 'W2 Bhiwandi' },
  };

  const destinationCoords: Record<string, { x: number; y: number; label: string }> = {
    D1: { x: 530, y: 40, label: 'D1 Kolkata' },
    D2: { x: 530, y: 90, label: 'D2 Ahmedabad' },
    S1: { x: 530, y: 140, label: 'S1 Bengaluru' },
    S2: { x: 530, y: 190, label: 'S2 Pune' },
  };

  // Group cartons by lane
  const laneTotals: Record<string, { sourceId: string; destinationId: string; cartons: number }> = {};
  flows.forEach((f) => {
    const key = `${f.sourceId}-${f.destinationId}`;
    if (!laneTotals[key]) {
      laneTotals[key] = { sourceId: f.sourceId, destinationId: f.destinationId, cartons: 0 };
    }
    laneTotals[key].cartons += f.cartons;
  });

  const totalCartons = Object.values(laneTotals).reduce((sum, l) => sum + l.cartons, 0);

  return (
    <div className="w-full bg-surface border-y border-line py-3 px-4 flex flex-col gap-2">
      <div className="flex items-center justify-between text-meta text-ink-2 select-none border-b border-line pb-2">
        <span className="font-medium text-ink">Network dispatch flow</span>
        <span className="tabular-nums">
          {Object.keys(laneTotals).length} active lanes, {totalCartons} total cartons
        </span>
      </div>

      <div className="relative w-full overflow-hidden">
        <svg
          viewBox="0 0 620 230"
          className="w-full h-auto max-h-[220px]"
          aria-label="FMCG distribution network flow diagram"
          role="img"
        >
          <title>FMCG Distribution Network Flow</title>
          <desc>
            Visual flow of cartons from warehouse origins W1 and W2 to destinations D1, D2, S1, and S2.
          </desc>

          <style>
            {`
              @media (prefers-reduced-motion: no-preference) {
                .orchestrated-flow {
                  stroke-dasharray: 600;
                  stroke-dashoffset: 600;
                  animation: drawLane 600ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
                }
                @keyframes drawLane {
                  to {
                    stroke-dashoffset: 0;
                  }
                }
              }
            `}
          </style>

          {/* Lane Curves */}
          {Object.entries(laneTotals).map(([laneKey, lane]) => {
            const start = warehouseCoords[lane.sourceId] || { x: 70, y: 100 };
            const end = destinationCoords[lane.destinationId] || { x: 530, y: 100 };
            const isHovered = hoveredLaneKey === laneKey;
            const strokeWidth = Math.max(1.5, Math.min(8, (lane.cartons / 20) * 1.5));
            const pathData = `M ${start.x} ${start.y} C ${(start.x + end.x) / 2} ${start.y}, ${
              (start.x + end.x) / 2
            } ${end.y}, ${end.x} ${end.y}`;

            return (
              <g
                key={laneKey}
                onMouseEnter={() => onHoverLane(laneKey)}
                onMouseLeave={() => onHoverLane(null)}
                className="cursor-pointer transition-opacity"
              >
                {/* Invisible hover hitbox */}
                <path
                  d={pathData}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={Math.max(16, strokeWidth + 8)}
                />
                {/* Visible curve */}
                <path
                  d={pathData}
                  fill="none"
                  stroke={isHovered ? 'var(--color-ink)' : 'var(--color-brand)'}
                  strokeWidth={isHovered ? strokeWidth + 2 : strokeWidth}
                  strokeOpacity={isHovered ? 1.0 : 0.65}
                  className={isOrchestrating ? 'orchestrated-flow' : ''}
                />
              </g>
            );
          })}

          {/* Warehouse Nodes (Left) */}
          {Object.entries(warehouseCoords).map(([id, node]) => (
            <g key={id} transform={`translate(${node.x}, ${node.y})`}>
              <rect
                x="-45"
                y="-16"
                width="90"
                height="32"
                rx="3"
                className="fill-surface stroke-line-strong"
                strokeWidth="1.5"
              />
              <text
                x="0"
                y="4"
                textAnchor="middle"
                className="text-[12px] font-sans font-semibold fill-ink select-none"
              >
                {id}
              </text>
              <text
                x="-52"
                y="4"
                textAnchor="end"
                className="text-[11px] font-sans fill-ink-2 select-none"
              >
                {node.label.replace(id + ' ', '')}
              </text>
            </g>
          ))}

          {/* Destination Nodes (Right) */}
          {Object.entries(destinationCoords).map(([id, node]) => {
            const unmet = unmetMap[id] || 0;
            const hasUnmet = unmet > 0;

            return (
              <g key={id} transform={`translate(${node.x}, ${node.y})`}>
                <rect
                  x="-45"
                  y="-16"
                  width="90"
                  height="32"
                  rx="3"
                  className={`fill-surface ${
                    hasUnmet ? 'stroke-madder' : 'stroke-line-strong'
                  }`}
                  strokeWidth={hasUnmet ? '2' : '1.5'}
                />
                <text
                  x="0"
                  y="4"
                  textAnchor="middle"
                  className="text-[12px] font-sans font-semibold fill-ink select-none"
                >
                  {id}
                </text>
                <text
                  x="52"
                  y="4"
                  textAnchor="start"
                  className="text-[11px] font-sans fill-ink-2 select-none"
                >
                  {node.label.replace(id + ' ', '')}
                </text>

                {/* Hollow ring for unmet demand */}
                {hasUnmet && (
                  <g transform="translate(18, -12)">
                    <circle
                      r="9"
                      className="fill-madder-wash stroke-madder"
                      strokeWidth="1.5"
                    />
                    <text
                      x="0"
                      y="3.5"
                      textAnchor="middle"
                      className="text-[10px] font-sans font-bold fill-madder tabular-nums select-none"
                    >
                      {unmet}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="sr-only">
        {flows.map((f, i) => (
          <p key={i}>
            Lane {f.sourceName} to {f.destinationName}: {f.cartons} cartons dispatched.
          </p>
        ))}
      </div>
    </div>
  );
}
