import React, { useState, useRef, useEffect } from 'react';
import { HelpCircle, X } from 'lucide-react';

export interface PopoverProps {
  title: string;
  triggerLabel?: string;
  children: React.ReactNode;
  align?: 'left' | 'right';
  className?: string;
}

export function Popover({
  title,
  triggerLabel = 'How this was calculated',
  children,
  align = 'left',
  className = '',
}: PopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && isOpen) {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className={`relative inline-block ${className}`}>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex items-center gap-1 text-meta text-ink-3 hover:text-brand font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand focus-visible:outline-offset-2 select-none"
      >
        <HelpCircle className="w-3.5 h-3.5 text-current shrink-0" strokeWidth={1.5} />
        <span>{triggerLabel}</span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label={title}
          className={`absolute z-40 top-full mt-2 w-80 max-w-sm bg-surface text-ink border border-line-strong rounded-control shadow-overlay p-4 text-left select-none animate-fadeIn ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-line">
            <h4 className="text-body font-semibold text-ink font-serif">{title}</h4>
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                triggerRef.current?.focus();
              }}
              aria-label="Close calculation explanation"
              className="p-1 text-ink-3 hover:text-ink rounded focus-visible:outline-2 focus-visible:outline-brand"
            >
              <X className="w-3.5 h-3.5" strokeWidth={1.5} />
            </button>
          </div>
          <div className="text-body text-ink-2 space-y-2">{children}</div>
        </div>
      )}
    </div>
  );
}
