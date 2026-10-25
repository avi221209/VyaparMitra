import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckSquare, AlertTriangle, AlertCircle, ArrowRight } from 'lucide-react';
import { apiFetch } from '../../lib/api';

interface NotificationItem {
  type: string;
  label: string;
  href: string;
}

interface NotificationsData {
  count: number;
  items: NotificationItem[];
}

export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<NotificationsData>({ count: 0, items: [] });
  const containerRef = useRef<HTMLDivElement>(null);

  const loadNotifications = async () => {
    try {
      const res = await apiFetch<NotificationsData>('/api/v1/notifications');
      setData(res);
    } catch {
      // quiet fallback
    }
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 20000);
    return () => clearInterval(interval);
  }, []);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getIcon = (type: string) => {
    switch (type) {
      case 'approval':
        return <CheckSquare className="w-4 h-4 text-brand shrink-0" strokeWidth={1.5} />;
      case 'data_issue':
        return <AlertCircle className="w-4 h-4 text-madder shrink-0" strokeWidth={1.5} />;
      case 'unmet_demand':
      case 'low_stock':
      case 'critical_stock':
        return <AlertTriangle className="w-4 h-4 text-turmeric shrink-0" strokeWidth={1.5} />;
      default:
        return <Bell className="w-4 h-4 text-ink-3 shrink-0" strokeWidth={1.5} />;
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        title="Notifications"
        aria-label="View notifications"
        className="relative p-2 text-ink-2 hover:text-ink hover:bg-paper rounded-control transition-colors"
      >
        <Bell className="w-5 h-5 text-ink-2" strokeWidth={1.5} />
        {data.count > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 bg-madder text-white text-[10px] font-bold rounded-full flex items-center justify-center leading-none">
            {data.count > 99 ? '99+' : data.count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-surface border border-line rounded-control shadow-overlay z-50 overflow-hidden">
          <div className="px-4 py-3 border-b border-line flex items-center justify-between bg-paper/50">
            <div className="font-serif font-semibold text-body text-ink">Notifications</div>
            <span className="text-[11px] font-semibold text-ink-3 bg-surface px-2 py-0.5 rounded-chip border border-line">
              {data.count} pending
            </span>
          </div>

          <div className="max-h-80 overflow-y-auto divide-y divide-line/40">
            {data.items.length === 0 ? (
              <div className="p-6 text-center text-meta text-ink-3">
                No active notifications or blocking issues.
              </div>
            ) : (
              data.items.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    navigate(item.href);
                    setOpen(false);
                  }}
                  className="w-full p-3 flex items-start gap-3 text-left hover:bg-brand-wash/40 transition-colors"
                >
                  <div className="mt-0.5">{getIcon(item.type)}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-meta text-ink leading-snug">{item.label}</p>
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-brand mt-1 hover:underline">
                      View details
                      <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
