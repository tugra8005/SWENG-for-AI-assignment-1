import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from 'react';

import { api, setAuthLostHandler, setToken } from '@/api/client';

const KEY = 'mesveret.token';

export type Me = { user_id: string; nickname: string; role: string; cellar_warned: boolean };

type AuthState = {
  me: Me | null;
  ready: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>('/auth/me'));
    } catch {
      setMe(null);
      setToken(null);
      await AsyncStorage.removeItem(KEY);
    }
  }, []);

  useEffect(() => {
    setAuthLostHandler(() => {
      setMe(null);
      AsyncStorage.removeItem(KEY).catch(() => undefined);
    });
    return () => setAuthLostHandler(null);
  }, []);

  useEffect(() => {
    (async () => {
      const saved = await AsyncStorage.getItem(KEY);
      if (saved) {
        setToken(saved);
        await refresh();
      }
      setReady(true);
    })();
  }, [refresh]);

  const login = useCallback(
    async (identifier: string, password: string) => {
      const res = await api<{ token: string }>('/auth/login', {
        method: 'POST',
        body: { identifier, password },
      });
      setToken(res.token);
      await AsyncStorage.setItem(KEY, res.token);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    setToken(null);
    setMe(null);
    await AsyncStorage.removeItem(KEY);
  }, []);

  return (
    <AuthContext.Provider value={{ me, ready, login, logout, refresh }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('AuthProvider eksik');
  return ctx;
}
