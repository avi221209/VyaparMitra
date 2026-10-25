import React, { useState, useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  Home,
  Database,
  CalendarCheck,
  CheckSquare,
  BarChart2,
  FileText,
  Sliders,
  AlertTriangle,
  RotateCw,
  HelpCircle,
} from 'lucide-react';
import {
  DemoRole,
  getStoredRole,
  setStoredRole,
  apiFetch,
  getBackendBaseUrl,
} from '../../lib/api';
import { SettingsDrawer } from './SettingsDrawer';
import { GuideDrawer } from './GuideDrawer';
import { TopBarSearch } from './TopBarSearch';
import { NotificationBell } from './NotificationBell';
import { ProfileChip } from './ProfileChip';
import { Button } from '../ui';

interface AppShellProps {
  children: React.ReactNode;
  pageTitle: string;
}

export function AppShell({ children, pageTitle }: AppShellProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const [backendHealthy, setBackendHealthy] = useState<boolean>(true);
  const [checkingHealth, setCheckingHealth] = useState<boolean>(false);
  const [settingsOpen, setSettingsOpen] = useState<boolean>(false);
  const [guideOpen, setGuideOpen] = useState<boolean>(false);
  const [isSampleData, setIsSampleData] = useState<boolean>(true);

  // Health check and sample data status
  const checkHealth = async () => {
    setCheckingHealth(true);
    try {
      const res = await apiFetch<any>('/api/v1/health');
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

  const loadSampleDataStatus = async () => {
    try {
      const res = await apiFetch<any>('/api/v1/dashboard/summary');
      if (res && typeof res.data_is_sample === 'boolean') {
        setIsSampleData(res.data_is_sample);
      }
    } catch {
      // quiet fallback
    }
  };

  useEffect(() => {
    checkHealth();
    loadSampleDataStatus();
    const interval = setInterval(() => {
      checkHealth();
    }, 20000);

    const handleUnreachable = () => setBackendHealthy(false);
    const handleReachable = () => setBackendHealthy(true);
    const handleUrlChange = () => {
      checkHealth();
      loadSampleDataStatus();
    };

    window.addEventListener('backend-unreachable', handleUnreachable);
    window.addEventListener('backend-reachable', handleReachable);
    window.addEventListener('backend-url-changed', handleUrlChange);

    return () => {
      clearInterval(interval);
      window.removeEventListener('backend-unreachable', handleUnreachable);
      window.removeEventListener('backend-reachable', handleReachable);
      window.removeEventListener('backend-url-changed', handleUrlChange);
    };
  }, []);

  const navItems = [
    {
      to: '/',
      label: 'Home',
      shortLabel: 'Home',
      icon: <Home className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
    },
    {
      to: '/data',
      label: 'Data & Network',
      shortLabel: 'Data',
      icon: <Database className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
    },
    {
      to: '/plan',
      label: 'Distribution Plan',
      shortLabel: 'Plan',
      icon: <CalendarCheck className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
    },
    {
      to: '/review',
      label: 'Review & Approval',
      shortLabel: 'Review',
      icon: <CheckSquare className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
    },
    {
      to: '/evaluate',
      label: 'Evaluation & Insights',
      shortLabel: 'Insights',
      icon: <BarChart2 className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
    },
    {
      to: '/audit',
      label: 'Audit Trail',
      shortLabel: 'Audit',
      icon: <FileText className="w-4 h-4 shrink-0" strokeWidth={1.5} />,
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
            <span>
              {getBackendBaseUrl()
                ? `Cannot connect to backend at ${getBackendBaseUrl()}. Please verify your service is running.`
                : 'Backend unreachable. Click Configure URL to connect to your Render service or local server.'}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-surface/20 hover:bg-surface/30 text-surface text-meta font-medium rounded-control active:scale-95 transition-all cursor-pointer"
            >
              <Sliders className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Configure URL</span>
            </button>
            <button
              type="button"
              onClick={checkHealth}
              disabled={checkingHealth}
              className="inline-flex items-center gap-1.5 px-3 py-1 bg-surface text-madder text-meta font-semibold rounded-control hover:bg-paper active:scale-95 transition-transform cursor-pointer"
            >
              <RotateCw className={`w-3.5 h-3.5 ${checkingHealth ? 'animate-spin' : ''}`} strokeWidth={1.5} />
              <span>Retry</span>
            </button>
          </div>
        </div>
      )}

      {/* Top Bar: white, 1px bottom rule, ~72px height */}
      <header className="h-[72px] px-6 max-[720px]:px-4 bg-surface border-b border-line flex items-center justify-between shrink-0 select-none z-30">
        {/* Brand Leaf Logo Mark + Wordmark + Tagline */}
        <div className="flex items-center gap-3 shrink-0">
          <NavLink
            to="/"
            title="VyaparMitra Home"
            className="flex items-center gap-2.5 hover:opacity-95 transition-opacity"
          >
            {/* Simple Elegant SVG Leaf in Brand Green */}
            <div className="w-9 h-9 rounded-control bg-brand-wash flex items-center justify-center shrink-0 border border-brand/20">
              <svg
                viewBox="0 0 24 24"
                className="w-5 h-5 text-brand"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
                <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
              </svg>
            </div>
            <div className="flex flex-col">
              <span className="font-serif text-[22px] font-bold text-ink leading-none tracking-tight">
                VyaparMitra
              </span>
              <span className="text-[11px] text-ink-3 leading-tight mt-1 font-normal tracking-normal hidden sm:inline">
                Smarter Distribution. Stronger Bharat.
              </span>
            </div>
          </NavLink>
        </div>

        {/* Centre: Wide Search */}
        <TopBarSearch />

        {/* Right Section: Notifications + Sample data badge + Profile Chip */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Notification Bell with Red Badge */}
          <NotificationBell />

          {/* Sample Data Badge: Small, tasteful, non-rotated */}
          {isSampleData && (
            <span
              title="Viewing bundled FMCG sample dataset"
              className="inline-flex items-center px-2 py-0.5 rounded-chip text-[11px] font-medium bg-turmeric-wash text-turmeric border border-turmeric/30 select-none shrink-0"
            >
              Sample data
            </span>
          )}

          {/* Profile Chip with Role Dropdown */}
          <ProfileChip
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenGuide={() => setGuideOpen(true)}
          />
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: 232px desktop, mint-tinted, collapses below 1100px, hidden below 720px */}
        <aside
          aria-label="Sidebar navigation"
          className="w-[232px] max-[1100px]:w-16 max-[720px]:hidden bg-[#F2F7F5] border-r border-line flex flex-col justify-between shrink-0 select-none"
        >
          {/* Nav Items */}
          <nav className="py-4 px-3 flex flex-col gap-1">
            {navItems.map((item) => {
              const isItemActive =
                item.to === '/'
                  ? location.pathname === '/'
                  : location.pathname.startsWith(item.to);

              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={`relative flex items-center gap-3 px-3.5 py-2.5 rounded-control text-body transition-colors ${
                    isItemActive
                      ? 'bg-brand-wash text-brand font-semibold before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-brand before:rounded-r'
                      : 'text-ink-2 hover:bg-white/80 hover:text-ink font-normal'
                  }`}
                >
                  {item.icon}
                  <span className="max-[1100px]:hidden text-[13.5px]">{item.label}</span>
                </NavLink>
              );
            })}
          </nav>

          {/* Bottom Area: Need Help Card + Settings */}
          <div className="p-3 flex flex-col gap-2">
            {/* Soft Beige Need Help Card */}
            <div className="max-[1100px]:hidden bg-[#F7F4EC] border border-[#E8E2D5] rounded-control p-3.5 shadow-sm">
              <div className="font-serif font-semibold text-ink text-[13.5px]">Need Help?</div>
              <p className="text-[11.5px] text-ink-3 mt-0.5 leading-snug">
                Our step-by-step guide to get started.
              </p>
              <div className="mt-2.5">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setGuideOpen(true)}
                  className="w-full text-[12px] py-1 bg-surface border-line hover:border-brand/40"
                >
                  Open Guide
                </Button>
              </div>
            </div>

            {/* Settings nav button at bottom */}
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
              className="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-control text-meta text-ink-2 hover:bg-white/80 hover:text-ink transition-colors"
            >
              <Sliders className="w-4 h-4 shrink-0" strokeWidth={1.5} />
              <span className="max-[1100px]:hidden text-[13.5px]">Settings</span>
            </button>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
          <main className="flex-1 p-8 max-[720px]:p-4 max-w-page w-full mx-auto pb-20 sm:pb-8">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile Bottom Bar (Below 720px) */}
      <nav
        aria-label="Mobile navigation"
        className="hidden max-[720px]:flex fixed bottom-0 left-0 right-0 h-14 bg-surface border-t border-line items-center justify-around z-40 select-none safe-area-bottom"
      >
        {navItems.map((item) => {
          const isItemActive =
            item.to === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex flex-col items-center justify-center py-1 px-2 text-[11px] ${
                isItemActive ? 'text-brand font-semibold' : 'text-ink-2 font-normal'
              }`}
            >
              {item.icon}
              <span className="mt-0.5">{item.shortLabel}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Settings Drawer */}
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {/* 5-Step Operator Guide Drawer */}
      <GuideDrawer open={guideOpen} onClose={() => setGuideOpen(false)} />
    </div>
  );
}

export default AppShell;
