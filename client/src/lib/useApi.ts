import { useCallback, useEffect, useRef, useState } from 'react';

import { api, ApiError } from '@/api/client';

export type Resource<T> = {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
};

/** Basit veri kancası: ``path`` null ise istek atmaz; ``pollMs`` verilirse periyodik yeniler. */
export function useApi<T = any>(path: string | null, pollMs?: number): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const current = useRef(path);
  current.current = path;

  const reload = useCallback(async () => {
    if (!path) return;
    try {
      const res = await api<T>(path);
      if (current.current === path) {
        setData(res);
        setError(null);
      }
    } catch (e) {
      if (current.current === path) setError(e as ApiError);
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(path !== null);
    reload();
    if (!pollMs || !path) return;
    const id = setInterval(reload, pollMs);
    return () => clearInterval(id);
  }, [path, pollMs, reload]);

  return { data, error, loading, reload };
}
