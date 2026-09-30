import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';

import { api } from '@/api/client';
import { useAuth } from '@/lib/auth';

/** Zildeki okunmamış bildirim sayısı. Başlık ve bildirim sayfası aynı sayıyı paylaşır. */
type NotificationsState = {
  unread: number;
  refresh: () => Promise<void>;
  markAllRead: () => Promise<void>;
};

const POLL_MS = 30_000;
const NotificationsContext = createContext<NotificationsState | null>(null);

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const [unread, setUnread] = useState(0);
  // Hesap değişince eski hesabın geç gelen cevabı sayıyı ezmesin.
  const who = useRef<string | null>(null);
  useEffect(() => {
    who.current = me?.user_id ?? null;
  }, [me]);

  const refresh = useCallback(async () => {
    const asked = who.current;
    if (!asked) {
      setUnread(0);
      return;
    }
    try {
      const r = await api<{ unread: number }>('/notifications/unread');
      if (who.current === asked) setUnread(r.unread);
    } catch {
      /* sunucu yoksa sayı olduğu gibi kalır */
    }
  }, []);

  const markAllRead = useCallback(async () => {
    if (!who.current) return;
    await api('/notifications/read', { method: 'POST', body: {} });
    setUnread(0);
  }, []);

  useEffect(() => {
    const first = setTimeout(refresh, 0);
    if (!me) return () => clearTimeout(first);
    const id = setInterval(refresh, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [me, refresh]);

  return (
    <NotificationsContext.Provider value={{ unread, refresh, markAllRead }}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsState {
  const ctx = useContext(NotificationsContext);
  if (!ctx) throw new Error('NotificationsProvider eksik');
  return ctx;
}
