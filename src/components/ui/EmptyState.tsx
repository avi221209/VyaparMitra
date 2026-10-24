import React from 'react';

export interface EmptyStateProps {
  title?: string;
  description: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-8 sm:p-12 text-center border border-dashed border-line bg-surface rounded-control ${className}`}
    >
      {icon && (
        <div className="w-10 h-10 mb-3 text-ink-3 flex items-center justify-center">
          {icon}
        </div>
      )}
      {title && (
        <h3 className="text-section font-serif font-medium text-ink mb-1">
          {title}
        </h3>
      )}
      <p className="text-body text-ink-2 max-w-md mb-5 leading-normal">
        {description}
      </p>
      {action && <div>{action}</div>}
    </div>
  );
}
