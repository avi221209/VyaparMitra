import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}

export function Drawer({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  width = 'w-[480px]',
}: DrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close on Escape & trap focus
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && open) {
        onClose();
      }
    }
    if (open) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex justify-end"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ink/20 transition-opacity duration-180"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer surface: 12px radius on left edges, shadow overlay, 180ms slide */}
      <div
        ref={drawerRef}
        className={`relative z-10 flex flex-col h-full bg-surface text-ink border-l border-line shadow-overlay rounded-l-overlay max-w-full ${width} transition-transform duration-180 ease-out`}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-line bg-surface rounded-tl-overlay">
          <div className="flex flex-col gap-1 pr-4">
            {title && (
              <h2 className="text-section font-serif font-semibold text-ink leading-tight">
                {title}
              </h2>
            )}
            {subtitle && (
              <div className="text-meta text-ink-2">{subtitle}</div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close drawer"
            className="p-1 text-ink-2 hover:text-ink hover:bg-paper rounded-control transition-colors duration-100"
          >
            <X className="w-5 h-5" strokeWidth={1.5} />
          </button>
        </div>

        {/* Content body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          {children}
        </div>

        {/* Sticky footer */}
        {footer && (
          <div className="px-6 py-4 border-t border-line bg-paper rounded-bl-overlay flex items-center justify-end gap-3 sticky bottom-0 z-10">
            {footer}
          </div>
        )}

      </div>
    </div>
  );
}
