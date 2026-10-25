import React, { useState, useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Database,
  CalendarCheck,
  CheckSquare,
  BarChart2,
  FileText,
  AlertTriangle,
  RotateCw,
  Check,
  Palette,
  Sliders,
  Command,
  HelpCircle,
} from 'lucide-react';
import {
  DemoRole,
  getStoredRole,
  setStoredRole,
  apiFetch,
} from '../../lib/api';
import { SettingsDrawer } from './SettingsDrawer';
import { CommandPalette } from './CommandPalette';
import { DemoGuideDrawer } from './DemoGuideDrawer';
import { Modal, Button } from '../ui';
import { Play } from 'lucide-react';

interface AppShellProps {
  children: React.ReactNode;
  pageTitle: string;
}

export function AppShell({ children, pageTitle }: AppShellProps) {
  const navigate = useNavigate();
  const [role, setRole] = useState<DemoRole>(getStoredRole());
  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [checkingHealth, setCheckingHealth] = useState<boolean>(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [demoGuideOpen, setDemoGuideOpen] = useState<boolean>(false);
  const [shortcutsModalOpen, setShortcutsModalOpen] = useState<boolean>(false);

  const [counts, setCounts] = useState<{
    lines?: number;
    pending?: number;
    hasData?: boolean;
    hasIssues?: boolean;
  }>({});

  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const res = await apiFetch<any>('/api/health');
      if (res && res.status === 'healthy') {
        setBackendHealthy(true);
      } else {
        setBackendHealthy(false);
      }
    } catch {
      setBackendHealthy(false);
    } finally {
      setCheckingHealth(false);
    }
  };

  const loadWorkflowStatus = async () => {
    try {
      const statusRes = await apiFetch<any>('/api/status');
      if (statusRes && statusRes.counts) {
        setCounts((prev) => ({
          ...prev,
          hasData: statusRes.counts.products > 0,
          hasIssues: statusRes.counts.validation_issues > 0,
        }));
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    checkHealth();
    loadWorkflowStatus();
    const interval = setInterval(() => {
      checkHealth();
    }, 15000);

    const handleUnreachable = () => setBackendHealthy(false);
    const handleReachable = () => setBackendHealthy(true);

    window.addEventListener('backend-unreachable', handleUnreachable);
    window.addEventListener('backend-reachable', handleReachable);

    return () => {
      clearInterval(interval);
      window.removeEventListener('backend-unreachable', handleUnreachable);
      window.removeEventListener('backend-reachable', handleReachable);
    };
  }, []);

  // Keyboard shortcut listener (Cmd+K for palette, ? for shortcuts)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const activeEl = document.activeElement;
      const isInput = activeEl instanceof HTMLInputElement || activeEl instanceof HTMLTextAreaElement;

      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      } else if (e.key === '?' && !isInput && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setShortcutsModalOpen(true);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newRole = e.target.value as DemoRole;
    setRole(newRole);
    setStoredRole(newRole);
    window.dispatchEvent(new Event('role-changed'));
  };

  const navItems = [
    {
      to: '/data',
      label: 'Data',
      icon: <Database className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
      stateMark: counts.hasData ? (
        <span className="inline-flex items-center text-ok text-[11px] gap-0.5" title="Data loaded">
          <Check className="w-3 h-3" strokeWidth={2} />
          <span className="hidden md:inline">Loaded</span>
        </span>
      ) : (
        <span className="text-meta text-ink-3">Empty</span>
      ),
    },
    {
      to: '/plan',
      label: 'Plan',
      icon: <CalendarCheck className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
      stateMark: <span className="text-meta text-ink-3">Active</span>,
    },
    {
      to: '/review',
      label: 'Review',
      icon: <CheckSquare className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
      stateMark: <span className="text-meta text-ink-3">Pending</span>,
    },
    {
      to: '/evaluate',
      label: 'Evaluate',
      icon: <BarChart2 className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
      stateMark: <span className="text-meta text-ink-3">Cached</span>,
    },
    {
      to: '/audit',
      label: 'Audit',
      icon: <FileText className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
      stateMark: <span className="text-meta text-ink-3">Logged</span>,
    },
    {
      to: '/design',
      label: 'Design system',
      icon: <Palette className="w-4 h-4 shrink-0 text-ink-3" strokeWidth={1.5} />,
      stateMark: <span className="text-[11px] text-ink-3">Dev</span>,
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-paper text-ink font-sans">
      {/* Unreachable backend banner */}
      {!backendHealthy && (
        <div
          role="alert"
          className="w-full bg-madder text-surface px-4 py-2.5 flex items-center justify-between text-body font-medium z-50 border-b border-madder"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-surface shrink-0" strokeWidth={1.5} />
            <span>Cannot reach backend at 127.0.0.1:8000. Start the server and click Retry.</span>
          </div>
          <button
            type="button"
            onClick={checkHealth}
            disabled={checkingHealth}
            className="inline-flex items-center gap-1.5 px-3 py-1 bg-surface text-madder text-meta font-semibold rounded-control hover:bg-paper active:scale-95 transition-transform"

          >
            <RotateCw className={`w-3.5 h-3.5 ${checkingHealth ? 'animate-spin' : ''}`} strokeWidth={1.5} />
            <span>Retry</span>
          </button>
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Left rail: 232px desktop, icons only below 1100px, hidden below 720px */}
        <aside
          aria-label="Sidebar navigation"
          className="w-[232px] max-[1100px]:w-16 max-[720px]:hidden bg-surface border-r border-line flex flex-col shrink-0 select-none"
        >
          {/* Rail Header with Wordmark linking to / */}
          <div className="h-16 flex items-center px-6 max-[1100px]:px-0 max-[1100px]:justify-center border-b border-line">
            <NavLink
              to="/"
              title="Return to landing overview"
              className="font-serif text-[20px] font-bold text-ink tracking-tight hover:text-brand transition-colors max-[1100px]:hidden"
            >
              VyaparMitra
            </NavLink>
            <NavLink
              to="/"
              title="Return to landing overview"
              className="font-serif text-[20px] font-bold text-ink tracking-tight hover:text-brand transition-colors hidden max-[1100px]:inline"
            >
              VM
            </NavLink>
          </div>

          {/* Workflow Navigation */}
          <nav className="flex-1 py-4 px-3 flex flex-col gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center justify-between px-3 py-2.5 rounded-control text-body transition-colors ${
                    isActive
                      ? 'bg-brand-wash text-brand font-semibold'
                      : 'text-ink-2 hover:bg-paper hover:text-ink font-normal'
                  }`
                }
              >
                <div className="flex items-center gap-3">
                  {item.icon}
                  <span className="max-[1100px]:hidden">{item.label}</span>
                </div>
                <div className="max-[1100px]:hidden">{item.stateMark}</div>
              </NavLink>
            ))}
          </nav>

          {/* Rail Footer */}
          <div className="p-4 border-t border-line text-meta text-ink-3 max-[1100px]:hidden flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <span className="leading-snug font-medium text-ink">Triwizathon 2026</span>
              <button
                type="button"
                onClick={() => setShortcutsModalOpen(true)}
                title="Keyboard Shortcuts (?)"
                className="p-1 text-ink-3 hover:text-ink hover:bg-paper rounded-control"
              >
                <HelpCircle className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
            </div>
            <div className="text-ink-3 text-[11px]">PS2: Distribution Intelligence</div>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
          {/* Top Bar */}
          <header className="h-16 px-8 max-[720px]:px-4 bg-surface border-b border-line flex items-center justify-between shrink-0 select-none">
            <h1 className="font-serif text-[20px] md:text-page-title font-semibold text-ink leading-tight truncate">
              {pageTitle}
            </h1>

            <div className="flex items-center gap-3 sm:gap-4">
              {/* Command Palette Button */}
              <button
                type="button"
                onClick={() => setCommandPaletteOpen(true)}
                className="hidden sm:flex items-center gap-2 px-2.5 py-1 text-meta text-ink-3 bg-paper border border-line rounded-control hover:text-ink hover:border-line-strong transition-colors"
              >
                <Command className="w-3.5 h-3.5" strokeWidth={1.5} />
                <span>Quick jump</span>
                <kbd className="px-1 py-0.2 bg-surface border border-line rounded-chip text-[10px] font-semibold text-ink-2">
                  ⌘K
                </kbd>
              </button>

              {/* Dataset Name */}
              <span className="text-meta text-ink-2 hidden xl:inline tabular-nums">
                FMCG Network (24 SKUs, 6 nodes)
              </span>

              {/* Simulated Data Stamp: Outlined rectangle, 2px radius, turmeric border, rotated about -1.5 degrees */}
              <div
                title="All data is synthetic and explicitly simulated for evaluation"
                className="px-2 py-0.5 border border-turmeric text-turmeric bg-turmeric-wash text-meta font-medium rounded-chip rotate-[-1.5deg] select-none shrink-0"
              >
                Simulated data
              </div>

              {/* Demo Guide Button */}
              <button
                type="button"
                onClick={() => setDemoGuideOpen(true)}
                title="Open timed 3-minute pitch demo guide"
                className="hidden md:flex items-center gap-1.5 px-2.5 py-1 text-meta font-medium text-brand bg-brand-wash/60 border border-brand/30 rounded-control hover:bg-brand-wash transition-colors"
              >
                <Play className="w-3.5 h-3.5 fill-brand text-brand" strokeWidth={1.5} />
                <span>Demo guide</span>
              </button>

              {/* Settings button */}
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                title="Settings"
                className="p-1.5 text-ink-2 hover:text-ink hover:bg-paper rounded-control transition-colors"
              >
                <Sliders className="w-4 h-4" strokeWidth={1.5} />
              </button>

              {/* Quiet Role Select */}
              <div className="flex items-center gap-1.5 text-meta text-ink-2 pl-2 border-l border-line">
                <label htmlFor="role-select" className="hidden sm:inline text-ink-3">
                  Role:
                </label>
                <select
                  id="role-select"
                  value={role}
                  onChange={handleRoleChange}
                  className="bg-transparent text-ink font-medium text-meta focus-visible:outline-brand cursor-pointer py-1"
                >
                  <option value="planner">Planner</option>
                  <option value="warehouse">Warehouse</option>
                  <option value="reviewer">Reviewer</option>
                </select>
              </div>
            </div>
          </header>

          {/* Page Body */}
          <main className="flex-1 p-8 max-[720px]:p-4 max-w-page w-full mx-auto pb-20 sm:pb-8">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile Bottom Bar (Below 720px) */}
      <nav
        aria-label="Mobile navigation"
        className="hidden max-[720px]:flex fixed bottom-0 left-0 right-0 h-14 bg-surface border-t border-line items-center justify-around z-40 select-none"
      >
        {navItems.slice(0, 5).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center py-1 px-2 text-[11px] ${
                isActive ? 'text-brand font-semibold' : 'text-ink-2 font-normal'
              }`
            }
          >
            {item.icon}
            <span className="mt-0.5">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Settings Drawer */}
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* Demo Guide Drawer */}
      <DemoGuideDrawer open={demoGuideOpen} onClose={() => setDemoGuideOpen(false)} />

      {/* Command Palette */}
      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      {/* Keyboard Shortcuts Sheet */}
      <Modal
        open={shortcutsModalOpen}
        onClose={() => setShortcutsModalOpen(false)}
        title="Keyboard Shortcuts"
        description="Global and table keyboard operations"
        footer={
          <Button variant="secondary" onClick={() => setShortcutsModalOpen(false)}>
            Close
          </Button>
        }
      >
        <div className="flex flex-col gap-3 text-body">
          <div className="flex items-center justify-between py-2 border-b border-line">
            <span>Open command palette</span>
            <kbd className="px-2 py-0.5 bg-paper border border-line-strong rounded-control text-meta font-semibold">
              Cmd + K / Ctrl + K
            </kbd>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-line">
            <span>Navigate table rows</span>
            <kbd className="px-2 py-0.5 bg-paper border border-line-strong rounded-control text-meta font-semibold">
              j / k or Arrow keys
            </kbd>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-line">
            <span>Open dispatch slip</span>
            <kbd className="px-2 py-0.5 bg-paper border border-line-strong rounded-control text-meta font-semibold">
              Enter
            </kbd>
          </div>
          <div className="flex items-center justify-between py-2 border-b border-line">
            <span>Close overlay / drawer</span>
            <kbd className="px-2 py-0.5 bg-paper border border-line-strong rounded-control text-meta font-semibold">
              Esc
            </kbd>
          </div>
          <div className="flex items-center justify-between py-2">
            <span>Show this shortcut sheet</span>
            <kbd className="px-2 py-0.5 bg-paper border border-line-strong rounded-control text-meta font-semibold">
              ?
            </kbd>
          </div>
        </div>
      </Modal>
    </div>
  );
}
