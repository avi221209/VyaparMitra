import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';

export type InlineMessageSeverity = 'info' | 'warning' | 'error' | 'success';

export interface InlineMessageProps {
  severity?: InlineMessageSeverity;
  children: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function InlineMessage({
  severity = 'info',
  children,
  action,
  className = '',
}: InlineMessageProps) {
  const styles = {
    info: 'bg-brand-wash/40 border-line text-ink',
    warning: 'bg-turmeric-wash border-turmeric/40 text-ink',
    error: 'bg-madder-wash border-madder/40 text-madder',
    success: 'bg-brand-wash border-ok/40 text-ink',
  }[severity];


  const icon = {
    info: <Info className="w-4 h-4 text-ink-2 shrink-0 mt-0.5" strokeWidth={1.5} />,
    warning: <AlertTriangle className="w-4 h-4 text-turmeric shrink-0 mt-0.5" strokeWidth={1.5} />,
    error: <AlertCircle className="w-4 h-4 text-madder shrink-0 mt-0.5" strokeWidth={1.5} />,
    success: <CheckCircle2 className="w-4 h-4 text-ok shrink-0 mt-0.5" strokeWidth={1.5} />,
  }[severity];

  return (
    <div
      role={severity === 'error' ? 'alert' : 'status'}
      className={`flex items-start justify-between gap-3 p-3.5 border rounded-control text-body ${styles} ${className}`}
    >
      <div className="flex items-start gap-2.5">
        {icon}
        <div className="flex-1 leading-normal">{children}</div>
      </div>
      {action && <div className="shrink-0 ml-3">{action}</div>}
    </div>
  );
}
