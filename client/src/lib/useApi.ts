import { useCallback, useEffect, useState } from 'react';

import { api, ApiError } from '@/api/client';

export type Resource<T> = {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
};

type State<T> = { path: string | null; data: T | null; error: ApiError | null; done: boolean };

/** Basit veri kancası: ``path`` null ise istek atmaz; ``pollMs`` verilirse periyodik yeniler. */
export function useApi<T = any>(path: string | null, pollMs?: number): Resource<T> {
  const [state, setState] = useState<State<T>>({ path, data: null, error: null, done: false });

  const fetchInto = useCallback(
    async (isAlive: () => boolean) => {
      if (!path) return;
      try {
        const data = await api<T>(path);
        if (isAlive()) setState({ path, data, error: null, done: true });
      } catch (e) {
        if (isAlive()) setState((s) => ({ ...s, path, error: e as ApiError, done: true }));
      }
    },
    [path],
  );

  useEffect(() => {
    let alive = true;
    const isAlive = () => alive;
    const first = setTimeout(() => fetchInto(isAlive), 0);
    const id = pollMs && path ? setInterval(() => fetchInto(isAlive), pollMs) : undefined;
    return () => {
      alive = false;
      clearTimeout(first);
      if (id) clearInterval(id);
    };
  }, [fetchInto, path, pollMs]);

  const reload = useCallback(() => fetchInto(() => true), [fetchInto]);

  const fresh = state.path === path;
  return {
    data: fresh ? state.data : null,
    error: fresh ? state.error : null,
    loading: path !== null && !(fresh && state.done),
    reload,
  };
}
