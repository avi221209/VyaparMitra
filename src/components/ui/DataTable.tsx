import React, { useState, useEffect } from 'react';

export type TableDensity = 'comfortable' | 'compact';

export interface Column<T> {
  key: string;
  header: string;
  align?: 'left' | 'right' | 'center';
  isNumeric?: boolean;
  width?: string;
  render?: (row: T, index: number) => React.ReactNode;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T, index: number) => string;
  density?: TableDensity;
  onDensityChange?: (density: TableDensity) => void;
  onRowClick?: (row: T, index: number) => void;
  selectedRowKey?: string | null;
  loading?: boolean;
  skeletonRowCount?: number;
  emptyMessage?: React.ReactNode;
  stickyFirstColumn?: boolean;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  density = 'comfortable',
  onRowClick,
  selectedRowKey,
  loading = false,
  skeletonRowCount = 6,
  emptyMessage = 'No records found.',
  stickyFirstColumn = true,
  className = '',
}: DataTableProps<T>) {
  const rowHeightClass = density === 'comfortable' ? 'h-[44px]' : 'h-[36px]';
  const pyClass = density === 'comfortable' ? 'py-2.5' : 'py-1.5';

  return (
    <div className={`w-full overflow-x-auto border border-line bg-surface ${className}`}>
      <table className="w-full text-left border-collapse text-body font-sans">
        <thead>
          <tr className="border-b border-line bg-paper text-meta font-medium text-ink-2 select-none sticky top-0 z-10">
            {columns.map((col, colIdx) => {
              const alignClass =
                col.align === 'right' || col.isNumeric
                  ? 'text-right'
                  : col.align === 'center'
                  ? 'text-center'
                  : 'text-left';
              const stickyClass =
                stickyFirstColumn && colIdx === 0
                  ? 'sticky left-0 bg-paper z-20 shadow-[1px_0_0_0_var(--color-line)]'
                  : '';


              return (
                <th
                  key={col.key}
                  style={col.width ? { width: col.width } : undefined}
                  className={`px-3.5 py-2.5 ${alignClass} ${stickyClass}`}
                >
                  {col.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: skeletonRowCount }).map((_, rIdx) => (
              <tr
                key={`skeleton-${rIdx}`}
                className={`border-b border-line ${rowHeightClass} animate-pulse`}
              >
                {columns.map((col, colIdx) => (
                  <td
                    key={`skel-cell-${colIdx}`}
                    className={`px-3.5 ${pyClass} ${
                      stickyFirstColumn && colIdx === 0
                        ? 'sticky left-0 bg-surface z-10 shadow-[1px_0_0_0_var(--color-line)]'
                        : ''
                    }`}
                  >
                    <div
                      className={`h-4 bg-paper rounded-chip ${
                        col.isNumeric ? 'ml-auto w-16' : 'w-24'
                      }`}
                    />
                  </td>
                ))}
              </tr>
            ))
          ) : data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-6 py-12 text-center text-ink-2 text-body"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, rIdx) => {
              const rowKey = keyExtractor(row, rIdx);
              const isSelected = selectedRowKey === rowKey;
              const isInteractive = Boolean(onRowClick);

              return (
                <tr
                  key={rowKey}
                  tabIndex={isInteractive ? 0 : undefined}
                  onClick={() => onRowClick && onRowClick(row, rIdx)}
                  onKeyDown={(e) => {
                    if (onRowClick && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault();
                      onRowClick(row, rIdx);
                    }
                  }}
                  className={`border-b border-line transition-colors duration-75 ${rowHeightClass} ${
                    isSelected
                      ? 'bg-brand-wash'
                      : isInteractive
                      ? 'hover:bg-paper/70 cursor-pointer focus-visible:bg-paper/70'
                      : ''
                  }`}
                >
                  {columns.map((col, colIdx) => {
                    const alignClass =
                      col.align === 'right' || col.isNumeric
                        ? 'text-right tabular-nums'
                        : col.align === 'center'
                        ? 'text-center'
                        : 'text-left';
                    const stickyClass =
                      stickyFirstColumn && colIdx === 0
                        ? `sticky left-0 z-10 shadow-[1px_0_0_0_var(--color-line)] ${
                            isSelected ? 'bg-brand-wash' : 'bg-surface'
                          }`
                        : '';


                    const content = col.render
                      ? col.render(row, rIdx)
                      : (row as any)[col.key] ?? '—';

                    return (
                      <td
                        key={col.key}
                        className={`px-3.5 ${pyClass} ${alignClass} ${stickyClass}`}
                      >
                        {content}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
