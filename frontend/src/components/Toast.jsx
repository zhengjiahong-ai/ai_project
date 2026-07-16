import React, { createContext, useCallback, useContext, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

const ToastContext = createContext(null);

const TYPE_ICON = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
};

const TYPE_STYLE = {
  success: 'bg-green-50 border-green-400 text-green-800',
  error: 'bg-red-50 border-red-400 text-red-800',
  warning: 'bg-amber-50 border-amber-400 text-amber-800',
  info: 'bg-blue-50 border-blue-400 text-blue-800',
};

let _nextId = 1;
function _uid() {
  return `toast-${Date.now()}-${_nextId++}`;
}

/**
 * Wrap a portion of the app to make `useToast()` available.
 * Renders a fixed toast container in the bottom-right corner.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.map((t) => (t.id === id ? { ...t, exiting: true } : t)));
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 220);
  }, []);

  const addToast = useCallback(
    (type, message) => {
      const id = _uid();
      setToasts((prev) => [...prev, { id, type, message, exiting: false }]);
      setTimeout(() => removeToast(id), 5000);
    },
    [removeToast],
  );

  const value = { toasts, addToast, removeToast };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-label="通知"
        className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2"
      >
        {toasts.map((toast) => {
          const Icon = TYPE_ICON[toast.type] || Info;
          return (
            <div
              key={toast.id}
              className={`flex items-center gap-3 rounded-lg border px-4 py-3 shadow-lg min-w-[320px] max-w-[480px] transition-all duration-200 ${
                TYPE_STYLE[toast.type] || TYPE_STYLE.info
              } ${toast.exiting ? 'opacity-0 translate-x-4' : 'opacity-100 translate-x-0'}`}
            >
              <Icon size={18} className="shrink-0" />
              <span className="flex-1 text-sm font-medium">{toast.message}</span>
              <button
                type="button"
                onClick={() => removeToast(toast.id)}
                className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100 transition-opacity"
                aria-label="关闭通知"
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

/**
 * Access the toast API from any descendant of `<ToastProvider>`.
 *
 * @returns {{ addToast: (type: string, message: string) => void,
 *             removeToast: (id: string) => void }}
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a <ToastProvider>');
  }
  return ctx;
}

export default ToastProvider;
