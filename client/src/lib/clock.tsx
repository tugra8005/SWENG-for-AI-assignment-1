import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from 'react';

import { api } from '@/api/client';

/** Sunucunun sahte saatiyle eşitlenmiş saat. Geri sayımlar bu saate göre işler. */
type ClockState = {
  offsetMs: number;
  status: any | null;
  now: () => number;
  sync: () => Promise<void>;
};

const ClockContext = createContext<ClockState | null>(null);

export function ClockProvider({ children }: { children: ReactNode }) {
  const [offsetMs, setOffset] = useState(0);
  const [frozenAt, setFrozenAt] = useState<number | null>(null);
  const [status, setStatus] = useState<any | null>(null);

  const sync = useCallback(async () => {
    try {
      const before = Date.now();
      const st = await api('/decision-hour');
      const after = Date.now();
      setOffset(new Date(st.now).getTime() - (before + after) / 2);
      // Demo modunda sunucunun saati durur; istemci de o anda durur.
      setFrozenAt(st.frozen ? new Date(st.now).getTime() : null);
      setStatus(st);
    } catch {
      /* sunucu yoksa yerel saat kullanılır */
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(sync, 0);
    const id = setInterval(sync, 30_000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [sync]);

  const now = useCallback(() => frozenAt ?? Date.now() + offsetMs, [frozenAt, offsetMs]);
  return (
    <ClockContext.Provider value={{ offsetMs, status, now, sync }}>{children}</ClockContext.Provider>
  );
}

export function useClock(): ClockState {
  const ctx = useContext(ClockContext);
  if (!ctx) throw new Error('ClockProvider eksik');
  return ctx;
}

/** Saniyede bir yeniden çizim için. */
export function useTick(ms = 1000): number {
  const [t, setT] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setT((x) => x + 1), ms);
    return () => clearInterval(id);
  }, [ms]);
  return t;
}
