import React, { useState, useEffect, useRef } from 'react';
import { ChevronDown, Sliders, HelpCircle, User, Check, Edit2 } from 'lucide-react';
import {
  DemoRole,
  getStoredRole,
  setStoredRole,
} from '../../lib/api';

export const USER_NAME_KEY = 'vyaparmitra_user_name';

export function getStoredUserName(): string {
  if (typeof window === 'undefined') return 'Planner';
  return localStorage.getItem(USER_NAME_KEY) || 'Planner';
}

export function setStoredUserName(name: string): void {
  localStorage.setItem(USER_NAME_KEY, name);
  window.dispatchEvent(new CustomEvent('username-changed', { detail: name }));
}

interface ProfileChipProps {
  onOpenSettings: () => void;
  onOpenGuide: () => void;
}

export function ProfileChip({ onOpenSettings, onOpenGuide }: ProfileChipProps) {
  const [role, setRole] = useState<DemoRole>(getStoredRole());
  const [userName, setUserName] = useState<string>(getStoredUserName());
  const [open, setOpen] = useState<boolean>(false);
  const [editingName, setEditingName] = useState<boolean>(false);
  const [tempName, setTempName] = useState<string>(userName);

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleRoleChanged = () => setRole(getStoredRole());
    const handleUserChanged = () => setUserName(getStoredUserName());

    window.addEventListener('role-changed', handleRoleChanged);
    window.addEventListener('username-changed', handleUserChanged);

    return () => {
      window.removeEventListener('role-changed', handleRoleChanged);
      window.removeEventListener('username-changed', handleUserChanged);
    };
  }, []);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setEditingName(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleRoleSelect = (newRole: DemoRole) => {
    setRole(newRole);
    setStoredRole(newRole);
    window.dispatchEvent(new Event('role-changed'));
  };

  const handleSaveName = () => {
    const clean = tempName.trim() || 'Planner';
    setUserName(clean);
    setStoredUserName(clean);
    setEditingName(false);
  };

  const initial = (userName[0] || 'P').toUpperCase();

  const roleLabels: Record<DemoRole, string> = {
    planner: 'Planner',
    warehouse: 'Warehouse Manager',
    reviewer: 'Plan Reviewer',
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-2 p-1.5 pl-2 pr-2.5 bg-paper/60 hover:bg-paper border border-line rounded-control transition-colors select-none"
      >
        <div className="w-7 h-7 rounded-full bg-brand text-white font-semibold text-meta flex items-center justify-center shrink-0">
          {initial}
        </div>
        <div className="text-left hidden md:block">
          <div className="text-meta font-medium text-ink leading-tight">{userName}</div>
          <div className="text-[11px] text-ink-3 leading-tight capitalize">{role}</div>
        </div>
        <ChevronDown className="w-3.5 h-3.5 text-ink-3 ml-0.5" strokeWidth={1.5} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-64 bg-surface border border-line rounded-control shadow-overlay z-50 overflow-hidden divide-y divide-line/40">
          {/* User Name & Quick Edit */}
          <div className="p-3 bg-paper/50">
            {editingName ? (
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={tempName}
                  onChange={(e) => setTempName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveName();
                    if (e.key === 'Escape') setEditingName(false);
                  }}
                  autoFocus
                  placeholder="Your Name"
                  className="px-2 py-1 text-meta bg-surface border border-line rounded-control w-full focus:outline-brand text-ink"
                />
                <button
                  type="button"
                  onClick={handleSaveName}
                  className="px-2 py-1 bg-brand text-white text-meta rounded-control font-medium hover:bg-brand/90"
                >
                  Save
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-body font-semibold text-ink">{userName}</div>
                  <div className="text-[11px] text-ink-3">{roleLabels[role]}</div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setTempName(userName);
                    setEditingName(true);
                  }}
                  title="Edit name"
                  className="p-1 text-ink-3 hover:text-ink hover:bg-surface rounded-control"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          {/* Role Switcher */}
          <div className="p-2">
            <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-ink-3">
              Switch Role
            </div>
            {(['planner', 'reviewer', 'warehouse'] as DemoRole[]).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => handleRoleSelect(r)}
                className={`w-full px-2.5 py-1.5 rounded-control text-meta flex items-center justify-between hover:bg-paper transition-colors capitalize ${
                  role === r ? 'font-semibold text-brand' : 'text-ink-2'
                }`}
              >
                <span>{roleLabels[r]}</span>
                {role === r && <Check className="w-4 h-4 text-brand" />}
              </button>
            ))}
          </div>

          {/* Actions: Settings & Guide */}
          <div className="p-2 flex flex-col gap-0.5">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onOpenSettings();
              }}
              className="w-full px-2.5 py-2 rounded-control text-meta text-left text-ink hover:bg-paper flex items-center gap-2.5 transition-colors"
            >
              <Sliders className="w-4 h-4 text-ink-3" strokeWidth={1.5} />
              <span>Planning Settings</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onOpenGuide();
              }}
              className="w-full px-2.5 py-2 rounded-control text-meta text-left text-ink hover:bg-paper flex items-center gap-2.5 transition-colors"
            >
              <HelpCircle className="w-4 h-4 text-ink-3" strokeWidth={1.5} />
              <span>Step-by-Step Guide</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
