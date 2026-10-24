import React from 'react';

export interface StatProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  size?: 'md' | 'lg' | 'display';
  className?: string;
}

export function Stat({
  label,
  value,
  hint,
  size = 'lg',
  className = '',
}: StatProps) {
  const valueSizeClass = {
    md: 'text-[20px] font-serif',
    lg: 'text-[28px] font-serif',
    display: 'text-[40px] font-serif',
  }[size];

  return (
    <div className={`flex flex-col gap-1 ${className}`}>
      <span className="text-meta font-medium text-ink-2 select-none">{label}</span>
      <span className={`${valueSizeClass} text-ink font-semibold tabular-nums leading-none tracking-tight`}>
        {value}
      </span>
      {hint && <span className="text-meta text-ink-3">{hint}</span>}
    </div>
  );
}
