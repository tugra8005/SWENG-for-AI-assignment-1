/**
 * Yazılan önerinin taslağı bu cihazda saklanır: sayfa kapanır ya da bağlantı koparsa başlık ve
 * metin kaybolmaz. Öneri gönderilince silinir. Sunucuya gitmez; yalnızca bu tarayıcıda/telefonda.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useRef, useState } from 'react';

type Draft = { title: string; body: string; savedAt: number };

export function useLocalDraft(
  key: string,
  title: string,
  body: string,
  restore: (d: { title: string; body: string }) => void,
  enabled = true,
) {
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const loaded = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    AsyncStorage.getItem(key)
      .then((raw) => {
        if (!alive || !raw) return;
        const d = JSON.parse(raw) as Draft;
        if (d.title || d.body) {
          restore({ title: d.title, body: d.body });
          setSavedAt(d.savedAt);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        loaded.current = true;
      });
    return () => {
      alive = false;
    };
    // restore yalnızca ilk yüklemede çağrılır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  useEffect(() => {
    if (!enabled || !loaded.current) return;
    const id = setTimeout(() => {
      if (!title.trim() && !body.trim()) {
        AsyncStorage.removeItem(key).catch(() => undefined);
        setSavedAt(null);
        return;
      }
      const at = Date.now();
      AsyncStorage.setItem(key, JSON.stringify({ title, body, savedAt: at } satisfies Draft))
        .then(() => setSavedAt(at))
        .catch(() => undefined);
    }, 600);
    return () => clearTimeout(id);
  }, [key, title, body, enabled]);

  const clear = useCallback(() => {
    AsyncStorage.removeItem(key).catch(() => undefined);
    setSavedAt(null);
  }, [key]);

  return { savedAt, clear };
}
