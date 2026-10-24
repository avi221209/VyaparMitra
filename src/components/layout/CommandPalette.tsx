import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal, Input, Badge } from '../ui';
import {
  Command,
  Database,
  CalendarCheck,
  CheckSquare,
  BarChart2,
  FileText,
  Sliders,
  User,
  LayoutGrid,
} from 'lucide-react';
import { DemoRole, setStoredRole, apiFetch } from '../../lib/api';

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onGeneratePlan?: () => void;
  onLoadSampleData?: () => void;
  onOpenSettings?: () => void;
  onToggleDensity?: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onGeneratePlan,
  onLoadSampleData,
  onOpenSettings,
  onToggleDensity,
}: CommandPaletteProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const actions = [
    {
      id: 'nav-data',
      label: 'Go to Data and Network Validation',
      category: 'Navigation',
      icon: <Database className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => navigate('/data'),
    },
    {
      id: 'nav-plan',
      label: 'Go to Distribution Plan',
      category: 'Navigation',
      icon: <CalendarCheck className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => navigate('/plan'),
    },
    {
      id: 'nav-review',
      label: 'Go to Review and Approvals',
      category: 'Navigation',
      icon: <CheckSquare className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => navigate('/review'),
    },
    {
      id: 'nav-evaluate',
      label: 'Go to Walk-Forward Evaluation',
      category: 'Navigation',
      icon: <BarChart2 className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => navigate('/evaluate'),
    },
    {
      id: 'nav-audit',
      label: 'Go to Decision Log and Audit Trail',
      category: 'Navigation',
      icon: <FileText className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => navigate('/audit'),
    },
    {
      id: 'action-generate',
      label: 'Generate plan (Optimize current horizon)',
      category: 'Planning',
      icon: <CalendarCheck className="w-4 h-4 text-brand" strokeWidth={1.5} />,
      perform: () => {
        navigate('/plan');
        onGeneratePlan?.();
      },
    },
    {
      id: 'action-seed',
      label: 'Load sample data (Clean FMCG network)',
      category: 'Data',
      icon: <Database className="w-4 h-4 text-turmeric" strokeWidth={1.5} />,
      perform: () => {
        navigate('/data');
        onLoadSampleData?.();
      },
    },
    {
      id: 'action-backup-state',
      label: 'Load backup demo state (Instant precomputed plan)',
      category: 'Demo',
      icon: <Database className="w-4 h-4 text-forest" strokeWidth={1.5} />,
      perform: async () => {
        try {
          await apiFetch('/api/demo/backup', { method: 'POST' });
          navigate('/plan');
          window.location.reload();
        } catch (e) {
          console.error('Failed to load backup demo state:', e);
        }
      },
    },
    {
      id: 'action-force-heuristic',
      label: 'Force solver fallback (Simulate solver timeout)',
      category: 'Demo',
      icon: <Database className="w-4 h-4 text-madder" strokeWidth={1.5} />,
      perform: async () => {
        try {
          await apiFetch('/api/plan?force_heuristic=true', { method: 'POST' });
          navigate('/plan');
          window.location.reload();
        } catch (e) {
          console.error('Failed to trigger fallback plan:', e);
        }
      },
    },
    {
      id: 'action-settings',
      label: 'Open system settings',
      category: 'Settings',
      icon: <Sliders className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => onOpenSettings?.(),
    },
    {
      id: 'action-density',
      label: 'Toggle row density (Comfortable / Compact)',
      category: 'Preferences',
      icon: <LayoutGrid className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => onToggleDensity?.(),
    },
    {
      id: 'role-planner',
      label: 'Switch role to Planner',
      category: 'Role',
      icon: <User className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => {
        setStoredRole('planner');
        window.dispatchEvent(new Event('role-changed'));
      },
    },
    {
      id: 'role-warehouse',
      label: 'Switch role to Warehouse',
      category: 'Role',
      icon: <User className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => {
        setStoredRole('warehouse');
        window.dispatchEvent(new Event('role-changed'));
      },
    },
    {
      id: 'role-reviewer',
      label: 'Switch role to Reviewer',
      category: 'Role',
      icon: <User className="w-4 h-4 text-ink-3" strokeWidth={1.5} />,
      perform: () => {
        setStoredRole('reviewer');
        window.dispatchEvent(new Event('role-changed'));
      },
    },
  ];

  const filtered = actions.filter((a) =>
    a.label.toLowerCase().includes(query.toLowerCase()) ||
    a.category.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filtered[selectedIndex]) {
          filtered[selectedIndex].perform();
          onClose();
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, filtered, selectedIndex, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 p-4"
    >
      <div
        className="fixed inset-0 bg-ink/25 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative z-10 w-full max-w-lg bg-surface text-ink border border-line shadow-overlay rounded-overlay flex flex-col overflow-hidden">
        {/* Search Input */}
        <div className="p-3 border-b border-line bg-surface flex items-center gap-2">
          <Command className="w-4 h-4 text-ink-3 ml-2 shrink-0" strokeWidth={1.5} />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or jump to screen..."
            className="w-full h-9 bg-transparent border-none text-body text-ink placeholder:text-ink-3 focus-visible:outline-none"
          />
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 flex flex-col gap-0.5">
          {filtered.length === 0 ? (
            <div className="p-6 text-center text-meta text-ink-3">
              No matching commands.
            </div>
          ) : (
            filtered.map((action, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <button
                  key={action.id}
                  type="button"
                  onClick={() => {
                    action.perform();
                    onClose();
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 text-left rounded-control text-body transition-colors ${
                    isSelected ? 'bg-brand-wash text-brand font-medium' : 'text-ink hover:bg-paper'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    {action.icon}
                    <span>{action.label}</span>
                  </div>
                  <span className="text-[11px] text-ink-3 font-medium capitalize">
                    {action.category}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="px-4 py-2 border-t border-line bg-paper flex items-center justify-between text-[11px] text-ink-3 select-none">

          <span>Navigate: ↑ / ↓</span>
          <span>Execute: Enter</span>
          <span>Close: Esc</span>
        </div>
      </div>
    </div>
  );
}
