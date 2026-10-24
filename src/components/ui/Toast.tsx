import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
  undoAction?: () => void;
  undoLabel?: string;
}

interface ToastContextType {
  toast: (item: Omit<ToastItem, 'id'>) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    ({ type = 'info', message, duration = 4000, undoAction, undoLabel = 'Undo' }: Omit<ToastItem, 'id'>) => {
      const id = Math.random().toString(36).substring(2, 9);
      const effectiveDuration = undoAction ? Math.max(duration, 8000) : duration;
      const newToast: ToastItem = { id, type, message, duration: effectiveDuration, undoAction, undoLabel };
      setToasts((prev) => [...prev, newToast]);

      if (effectiveDuration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, effectiveDuration);
      }
    },
    [removeToast]
  );

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 max-w-sm pointer-events-none"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex items-center justify-between gap-3 px-4 py-3 bg-ink text-surface rounded-control shadow-overlay text-body border border-line-strong select-none transition-all duration-180"
          >
            <div className="flex items-center gap-2.5">
              {t.type === 'success' && <CheckCircle2 className="w-4 h-4 text-ok shrink-0" strokeWidth={1.5} />}
              {t.type === 'error' && <AlertCircle className="w-4 h-4 text-madder shrink-0" strokeWidth={1.5} />}
              {t.type === 'info' && <Info className="w-4 h-4 text-line-strong shrink-0" strokeWidth={1.5} />}
              <span className="text-body font-normal">{t.message}</span>
            </div>
            <div className="flex items-center gap-2 ml-2">
              {t.undoAction && (
                <button
                  type="button"
                  onClick={() => {
                    t.undoAction?.();
                    removeToast(t.id);
                  }}
                  className="px-2 py-0.5 text-meta font-medium text-turmeric hover:underline focus-visible:outline-brand"
                >
                  {t.undoLabel || 'Undo'}
                </button>
              )}
              <button
                type="button"
                onClick={() => removeToast(t.id)}
                aria-label="Dismiss toast"
                className="p-0.5 text-ink-3 hover:text-surface"
              >
                <X className="w-3.5 h-3.5" strokeWidth={1.5} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
