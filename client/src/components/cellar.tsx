/**
 * Mahzen bileşenleri: tam siyah, fosfor amberi, mono yazı; CRT tarama çizgileri, çürüme.
 * Çürüyen metin 4,5:1 kontrastın altına inmez; erişilebilir etiket özgün metni taşır.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';
import {
  Animated,
  ImageBackground,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  type TextStyle,
  TextInput,
  type TextInputProps,
  View,
} from 'react-native';

import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { cellar, fonts, layout, paper } from '@/theme/tokens';

const scanlines = require('@/assets/images/scanlines.png');
const CRT_KEY = 'mesveret.crt';

// --- CRT ----------------------------------------------------------------------------------------

type CrtState = { on: boolean; toggle: () => void };
const CrtContext = createContext<CrtState>({ on: true, toggle: () => {} });

export function CrtProvider({ children }: { children: ReactNode }) {
  const [on, setOn] = useState(true);
  useEffect(() => {
    AsyncStorage.getItem(CRT_KEY).then((v) => v === 'off' && setOn(false));
  }, []);
  const toggle = () =>
    setOn((x) => {
      AsyncStorage.setItem(CRT_KEY, x ? 'off' : 'on');
      return !x;
    });
  return <CrtContext.Provider value={{ on, toggle }}>{children}</CrtContext.Provider>;
}

export const useCrt = () => useContext(CrtContext);

function CrtOverlay() {
  const { on } = useCrt();
  if (!on) return null;
  return (
    <View
      style={[StyleSheet.absoluteFill, { pointerEvents: 'none' }]}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <ImageBackground
        source={scanlines}
        resizeMode="repeat"
        style={StyleSheet.absoluteFill}
        imageStyle={{ width: '100%', height: '100%', opacity: 0.9 }}
      />
    </View>
  );
}

// --- metin --------------------------------------------------------------------------------------

type TP = { children: ReactNode; style?: TextStyle | TextStyle[]; numberOfLines?: number };

export const Term = ({ children, style, numberOfLines }: TP) => (
  <Text style={[s.term, style]} numberOfLines={numberOfLines}>{children}</Text>
);
export const TermDim = ({ children, style }: TP) => <Text style={[s.term, s.dimText, style]}>{children}</Text>;
export const Banner = ({ children, style }: TP) => (
  <Text accessibilityRole="header" style={[s.banner, style]}>{children}</Text>
);

function hexToRgb(h: string) {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** İki renk arası doğrusal karışım. */
export function mix(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const k = Math.max(0, Math.min(1, t));
  const c = (x: number, y: number) => Math.round(x + (y - x) * k).toString(16).padStart(2, '0');
  return `#${c(r1, r2)}${c(g1, g2)}${c(b1, b2)}`;
}

const GLITCH = ['░', '▒', '▓', '▚', '▞', '▙', '▟', '¦', '¤'];

function noise(i: number, seed: number): number {
  const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/** Çürüyen metin: ``decay`` 0 (taze) → 1 (silinmek üzere). */
export function DecayText({ text, decay, seed = 1, style, numberOfLines }: {
  text: string; decay: number; seed?: number; style?: TextStyle | TextStyle[]; numberOfLines?: number;
}) {
  const glitch = Math.max(0, (decay - 0.55) / 0.45) * 0.16;
  const color = mix(cellar.amber, cellar.amberDecayed, Math.max(0, (decay - 0.2) / 0.8));
  const shown = glitch
    ? Array.from(text)
        .map((ch, i) => (ch !== ' ' && noise(i, seed) < glitch ? GLITCH[Math.floor(noise(i + 7, seed) * GLITCH.length)] : ch))
        .join('')
    : text;
  return (
    <Text accessibilityLabel={text} numberOfLines={numberOfLines} style={[s.term, { color }, style]}>
      {shown}
    </Text>
  );
}

export function LifeBar({ lifetime }: { lifetime: number }) {
  const pct = Math.round(lifetime * 100);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} accessibilityLabel={`Ömür yüzde ${pct}`}>
      <View style={s.bar}>
        <View style={[s.barFill, { width: `${pct}%`, backgroundColor: mix(cellar.amber, cellar.amberDim, 1 - lifetime) }]} />
      </View>
      <Text style={[s.term, s.dimText, { fontSize: 11 }]}>{pct}%</Text>
    </View>
  );
}

// --- form ---------------------------------------------------------------------------------------

export function AmberButton({ label, onPress, disabled, subtle, selected }: {
  label: string; onPress: () => void | Promise<void>; disabled?: boolean; subtle?: boolean;
  /** Tarafsız seçenek düğmesi seçiliyse dolu amber. */
  selected?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Pressable
      accessibilityRole="button"
      aria-pressed={selected}
      disabled={disabled || busy}
      onPress={async () => {
        setBusy(true);
        try {
          await onPress();
        } finally {
          setBusy(false);
        }
      }}
      style={({ pressed, hovered }: any) => [
        s.button,
        subtle && { borderColor: cellar.amberDim },
        (pressed || hovered) && { backgroundColor: cellar.amberGlow },
        selected && { backgroundColor: cellar.amber },
        (disabled || busy) && { opacity: 0.45 },
      ]}
    >
      <Text style={[s.term, { fontSize: 13 }, selected && { color: cellar.bg }]}>[ {busy ? '…' : label} ]</Text>
    </Pressable>
  );
}

export function AmberField({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ marginBottom: 10 }}>
      <Text style={[s.term, s.dimText, { fontSize: 12, marginBottom: 4 }]}>&gt; {label}</Text>
      <TextInput
        placeholderTextColor={cellar.amberDecayed}
        {...props}
        style={[s.input, props.multiline && { minHeight: 90, textAlignVertical: 'top' }, props.style]}
      />
    </View>
  );
}

export function AmberError({ error }: { error: unknown }) {
  if (!error) return null;
  return <Term style={{ color: cellar.amber, marginVertical: 6 }}>!! {(error as Error).message}</Term>;
}

// --- uyarı --------------------------------------------------------------------------------------

export function WarningModal({ visible, text, onAccept, onCancel }: {
  visible: boolean; text: string; onAccept: () => void; onCancel: () => void;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <View style={s.modalBack}>
        <View style={s.modal} accessibilityRole="alert">
          <Banner style={{ fontSize: 30 }}>UYARI</Banner>
          <Term style={{ fontSize: 16, lineHeight: 24, marginVertical: 12 }}>{text}</Term>
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <AmberButton label="anladım, devam" onPress={onAccept} />
            <AmberButton label="geri dön" subtle onPress={onCancel} />
          </View>
        </View>
      </View>
    </Modal>
  );
}

// --- sayfa --------------------------------------------------------------------------------------

/** Mahzen sayfası: girişte kâğıt rengi karanlığa çekilir (kararma geçişi). */
export function CellarPage({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  const fade = useAnimatedValue(reduced ? 0 : 1);
  const { on, toggle } = useCrt();
  useEffect(() => {
    if (reduced) return;
    Animated.timing(fade, { toValue: 0, duration: 900, useNativeDriver: false }).start();
  }, [fade, reduced]);
  return (
    <View style={s.page}>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={s.column}>
          <View style={s.topbar}>
            <Pressable onPress={() => router.push('/')} accessibilityRole="link">
              <Text style={[s.term, s.dimText, { fontSize: 12 }]}>&lt; meydan</Text>
            </Pressable>
            <Pressable onPress={toggle} accessibilityRole="switch" aria-checked={on}>
              <Text style={[s.term, s.dimText, { fontSize: 12 }]}>crt: {on ? 'açık' : 'kapalı'}</Text>
            </Pressable>
          </View>
          {children}
        </View>
      </ScrollView>
      <CrtOverlay />
      <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: paper.bg, opacity: fade, pointerEvents: 'none' }]} />
    </View>
  );
}

export const cellarStyles = StyleSheet.create({
  rule: { height: 1, backgroundColor: cellar.amberDim, marginVertical: 10 },
});

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: cellar.bg },
  scroll: { paddingHorizontal: layout.gutter, paddingTop: 14, paddingBottom: 48 },
  column: { width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center' },
  topbar: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  term: { fontFamily: fonts.mono, fontSize: 14, lineHeight: 21, color: cellar.amber },
  dimText: { color: cellar.amberDecayed },
  banner: { fontFamily: fonts.terminal, fontSize: 64, lineHeight: 64, color: cellar.amber, letterSpacing: 4 },
  bar: { width: 70, height: 6, borderWidth: 1, borderColor: cellar.amberDim },
  barFill: { height: '100%' },
  button: {
    borderWidth: 1,
    borderColor: cellar.amber,
    paddingHorizontal: 8,
    paddingVertical: 5,
    alignSelf: 'flex-start',
    ...(Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : null),
  },
  input: {
    fontFamily: fonts.mono,
    fontSize: 14,
    color: cellar.amber,
    borderWidth: 1,
    borderColor: cellar.amberDim,
    padding: 8,
    backgroundColor: '#0A0700',
    ...(Platform.OS === 'web' ? ({ outlineColor: cellar.amber } as any) : null),
  },
  modalBack: { flex: 1, backgroundColor: 'rgba(0,0,0,0.88)', justifyContent: 'center', padding: 16 },
  modal: {
    borderWidth: 2,
    borderColor: cellar.amber,
    backgroundColor: cellar.bg,
    padding: 18,
    maxWidth: 520,
    alignSelf: 'center',
    width: '100%',
  },
});
