import { createContext, type ReactNode, useCallback, useContext, useRef, useState } from "react";

import { CheckIcon, CloseIcon } from "./Icons";

type Tone = "success" | "error";
interface Toast { id: number; tone: Tone; text: string }

const TOAST_MS = 4000;
const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => {});

/** Short confirmations of what just happened ("Restart sent to SENSOR-001"), bottom right. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);
  const show = useCallback((text: string, tone: Tone = "success") => {
    const id = nextId.current++;
    setToasts((list) => [...list.slice(-3), { id, tone, text }]); // at most 4 on screen
    setTimeout(() => dismiss(id), TOAST_MS);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" role="status" aria-live="polite" data-testid="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} data-testid="toast">
            {t.tone === "success" ? <CheckIcon size={18} /> : <CloseIcon size={18} />}
            <span>{t.text}</span>
            <button type="button" className="icon-button" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <CloseIcon size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
