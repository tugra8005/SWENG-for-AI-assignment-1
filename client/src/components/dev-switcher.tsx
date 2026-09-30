/**
 * Geliştirme menüsü (sağ alt köşe): sınıf gösteriminde hesap değiştirmek ve demo adımının
 * sayfalarını açmak için. Yalnızca geliştirme derlemesinde (__DEV__) ve API geliştirme
 * ortamındayken (ENV=dev: /_dev uç noktaları var) görünür; üretim derlemesinde bileşen hiçbir şey
 * çizmez, üretim API'sinde /_dev uç noktaları hiç yoktur.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '@/api/client';
import { useAuth } from '@/lib/auth';
import { fonts } from '@/theme/tokens';

const HIDE_KEY = 'mesveret.devmenu';
/** Projenin sahibinin tohum hesabı (api/src/mesveret/services/seed.py, OWNER). */
export const OWNER = 'MostlyHarmless';
const USERS = [OWNER, 'aylin', 'ceren', 'ayse', 'baris', 'zeynep', 'hale', 'emre', 'elif', 'selin'];

type Screen = { user: string; path: string; show: string };
type DemoView = { step: string | null; index?: number; total?: number; title?: string; screens?: Screen[] };

export function DevSwitcher() {
  if (!__DEV__) return null;
  return <DevSwitcherInner />;
}

/** Giriş sayfasında tek tıkla giriş: yalnızca geliştirme derlemesinde ve /_dev varken. */
export function QuickLogin() {
  if (!__DEV__) return null;
  return <QuickLoginInner />;
}

function QuickLoginInner() {
  const { loginWithToken } = useAuth();
  const [available, setAvailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    api('/_dev/demo')
      .then(() => alive && setAvailable(true))
      .catch(() => undefined); // üretim API'si: /_dev yok, düğme görünmez
    return () => {
      alive = false;
    };
  }, []);
  if (!available) return null;
  const enter = async () => {
    setError(null);
    try {
      const r = await api<{ token: string }>('/_dev/login-as', { method: 'POST', body: { nickname: OWNER } });
      await loginWithToken(r.token);
      router.replace('/');
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  };
  return (
    <View style={st.quick}>
      <Pressable onPress={enter} accessibilityRole="button" style={st.quickButton}>
        <Text style={st.quickLabel}>{OWNER} olarak gir</Text>
      </Pressable>
      <Text style={st.quickNote}>Geliştirme ortamı: şifresiz giriş. Üretimde bu düğme yoktur.</Text>
      {error ? <Text style={[st.quickNote, { color: '#7A1E2B' }]}>{error}</Text> : null}
    </View>
  );
}

function DevSwitcherInner() {
  const { me, loginWithToken } = useAuth();
  const [demo, setDemo] = useState<DemoView | null>(null);
  const [available, setAvailable] = useState(false);
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [nick, setNick] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDemo(await api<DemoView>('/_dev/demo'));
      setAvailable(true);
    } catch {
      setAvailable(false); // üretim API'si: /_dev yok
    }
  }, []);

  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(HIDE_KEY).then((v) => alive && setHidden(v === 'gizli')).catch(() => undefined);
    api<DemoView>('/_dev/demo')
      .then((d) => {
        if (!alive) return;
        setDemo(d);
        setAvailable(true);
      })
      .catch(() => undefined); // üretim API'si: /_dev yok, menü görünmez
    return () => {
      alive = false;
    };
  }, []);

  const go = async (user: string, path?: string) => {
    setError(null);
    try {
      const r = await api<{ token: string }>('/_dev/login-as', { method: 'POST', body: { nickname: user } });
      // Sayfa yeniden yüklenmez: veri kancaları kimlik değişince kendiliğinden yeniden okur.
      await loginWithToken(r.token);
      setOpen(false);
      if (path) router.replace(path as any);
    } catch (e: any) {
      setError(e?.message ?? String(e));
    }
  };

  if (!available || hidden) return null;
  return (
    <View style={st.root} pointerEvents="box-none">
      {open ? (
        <View style={st.panel}>
          <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ gap: 8 }}>
            <View style={st.row}>
              <Text style={st.kicker}>geliştirme · yalnızca ENV=dev</Text>
              <Pressable onPress={() => setOpen(false)} accessibilityRole="button" accessibilityLabel="Menüyü kapat">
                <Text style={st.link}>×</Text>
              </Pressable>
            </View>
            {demo?.step ? (
              <View style={{ gap: 6 }}>
                <Text style={st.title}>
                  Adım {demo.step} ({demo.index}/{demo.total}) · {demo.title}
                </Text>
                {demo.screens?.map((sc, i) => (
                  <Pressable key={i} onPress={() => go(sc.user, sc.path)} accessibilityRole="button" style={st.screen}>
                    <Text style={st.screenHead}>
                      {i + 1}) {sc.user} → {sc.path}
                    </Text>
                    <Text style={st.screenShow}>{sc.show}</Text>
                  </Pressable>
                ))}
              </View>
            ) : (
              <Text style={st.muted}>Demo başlamadı (meşveret-dev demo goto 1).</Text>
            )}
            <Text style={st.kicker}>hesap</Text>
            <View style={st.chips}>
              {USERS.map((u) => (
                <Pressable key={u} onPress={() => go(u)} style={[st.chip, me?.nickname === u && st.chipOn]}>
                  <Text style={[st.chipText, me?.nickname === u && st.chipTextOn]}>{u}</Text>
                </Pressable>
              ))}
            </View>
            <View style={st.row}>
              <TextInput
                value={nick}
                onChangeText={setNick}
                placeholder="takma ad"
                placeholderTextColor="#9A958A"
                autoCapitalize="none"
                style={st.input}
                onSubmitEditing={() => nick.trim() && go(nick.trim())}
              />
              <Pressable onPress={() => nick.trim() && go(nick.trim())}>
                <Text style={st.link}>geç</Text>
              </Pressable>
            </View>
            {error ? <Text style={st.error}>{error}</Text> : null}
            <Pressable
              onPress={() => {
                AsyncStorage.setItem(HIDE_KEY, 'gizli').catch(() => undefined);
                setHidden(true);
              }}
            >
              <Text style={st.muted}>menüyü gizle (tarayıcı depolamasından geri açılır)</Text>
            </Pressable>
          </ScrollView>
        </View>
      ) : null}
      <Pressable
        onPress={() => {
          if (!open) load();
          setOpen(!open);
        }}
        accessibilityRole="button"
        accessibilityLabel="Geliştirme menüsü"
        style={st.pill}
      >
        <Text style={st.pillText}>
          {demo?.step ? `adım ${demo.step} · ` : ''}
          {me?.nickname ?? 'oturum yok'} ▾
        </Text>
      </Pressable>
    </View>
  );
}

const INK = '#1B1A17';
const SHEET = '#F8F4EB';
const st = StyleSheet.create({
  root: {
    position: Platform.OS === 'web' ? ('fixed' as any) : 'absolute',
    right: 12,
    bottom: 12,
    alignItems: 'flex-end',
    gap: 8,
    zIndex: 1000,
  },
  pill: { backgroundColor: INK, paddingHorizontal: 10, paddingVertical: 6, opacity: 0.92 },
  pillText: { fontFamily: fonts.monoMedium, fontSize: 11, color: SHEET, letterSpacing: 0.3 },
  panel: { width: 320, backgroundColor: INK, padding: 12, opacity: 0.97 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  kicker: { fontFamily: fonts.monoMedium, fontSize: 10, letterSpacing: 1.2, color: '#B5AE9F', textTransform: 'uppercase' },
  title: { fontFamily: fonts.serifBold, fontSize: 15, color: SHEET },
  screen: { borderWidth: 1, borderColor: '#4A463E', padding: 8, gap: 2 },
  screenHead: { fontFamily: fonts.monoMedium, fontSize: 11, color: SHEET },
  screenShow: { fontFamily: fonts.serif, fontSize: 12, lineHeight: 16, color: '#D8D2C4' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { borderWidth: 1, borderColor: '#6B6558', paddingHorizontal: 8, paddingVertical: 3 },
  chipOn: { backgroundColor: SHEET, borderColor: SHEET },
  chipText: { fontFamily: fonts.mono, fontSize: 11, color: SHEET },
  chipTextOn: { color: INK },
  input: { flex: 1, borderBottomWidth: 1, borderBottomColor: '#6B6558', color: SHEET, fontFamily: fonts.mono, fontSize: 12, paddingVertical: 4 },
  link: { fontFamily: fonts.monoBold, fontSize: 13, color: SHEET, paddingHorizontal: 4 },
  muted: { fontFamily: fonts.serifItalic, fontSize: 12, color: '#B5AE9F' },
  error: { fontFamily: fonts.mono, fontSize: 11, color: '#E59AA6' },
  // Giriş sayfasındaki geliştirme düğmesi: kesikli çerçeve, sayfanın asıl formundan ayrı dursun.
  quick: { borderWidth: 1, borderStyle: 'dashed', borderColor: '#6B6558', padding: 12, gap: 8, marginBottom: 16 },
  quickButton: { alignSelf: 'flex-start', backgroundColor: INK, paddingHorizontal: 14, paddingVertical: 9 },
  quickLabel: { fontFamily: fonts.monoBold, fontSize: 13, letterSpacing: 0.4, color: SHEET },
  quickNote: { fontFamily: fonts.serifItalic, fontSize: 14, color: '#4A463E' },
});
