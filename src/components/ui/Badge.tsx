import React from 'react';

export type BadgeVariant = 'neutral' | 'brand' | 'turmeric' | 'madder' | 'ok';

export interface BadgeProps {
  variant?: BadgeVariant;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Badge({
  variant = 'neutral',
  icon,
  children,
  className = '',
}: BadgeProps) {
  const variantStyles = {
    neutral: 'bg-paper text-ink-2 border-line',
    brand: 'bg-brand-wash text-brand border-brand/20',
    turmeric: 'bg-turmeric-wash text-ink border-turmeric/40',
    madder: 'bg-madder-wash text-madder border-madder/40',
    ok: 'bg-brand-wash text-ok border-ok/40',
  }[variant];


  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-chip border text-meta font-medium select-none ${variantStyles} ${className}`}
    >
      {icon && <span className="inline-flex shrink-0 w-3.5 h-3.5 items-center justify-center">{icon}</span>}
      <span>{children}</span>
    </span>
  );
}
