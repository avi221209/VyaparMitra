import React from 'react';

export interface TabItem {
  id: string;
  label: string;
  badge?: React.ReactNode;
}

export interface TabsProps {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ items, activeId, onChange, className = '' }: TabsProps) {
  return (
    <div
      role="tablist"
      className={`flex items-center gap-6 border-b border-line ${className}`}
    >
      {items.map((tab) => {
        const isActive = tab.id === activeId;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={`flex items-center gap-2 pb-2.5 pt-1 text-body font-medium transition-colors select-none relative focus-visible:outline-brand ${
              isActive
                ? 'text-brand font-semibold'
                : 'text-ink-2 hover:text-ink'
            }`}
          >
            <span>{tab.label}</span>
            {tab.badge && <span>{tab.badge}</span>}
            {isActive && (
              <span className="absolute bottom-[-1px] left-0 right-0 h-[2px] bg-brand" />
            )}
          </button>
        );
      })}
    </div>
  );
}
