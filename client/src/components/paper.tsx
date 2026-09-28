/**
 * Meydan bileşenleri: resmî gazete / arşiv estetiği.
 * Kâğıt zemin, mürekkep, tek vurgu mühür bordosu; serif metin, mono hash ve sayılar.
 */
import { Link, router, usePathname } from 'expo-router';
import { type ReactNode, useState } from 'react';
import {
  ActivityIndicator,
  ImageBackground,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  type TextStyle,
  TextInput,
  type TextInputProps,
  View,
  type ViewStyle,
  useWindowDimensions,
} from 'react-native';

import { ApiError } from '@/api/client';
import { useAuth } from '@/lib/auth';
import { useClock, useTick } from '@/lib/clock';
import { fmtCountdown, fmtLong, shortHash } from '@/lib/format';
import { fonts, layout, paper } from '@/theme/tokens';

const grain = require('@/assets/images/paper-grain.png');

// --- metin ---------------------------------------------------------------------------------------

type TP = { children: ReactNode; style?: TextStyle | TextStyle[]; numberOfLines?: number };

export const Display = ({ children, style }: TP) => (
  <Text accessibilityRole="header" style={[s.display, style]}>{children}</Text>
);
export const H1 = ({ children, style }: TP) => (
  <Text accessibilityRole="header" style={[s.h1, style]}>{children}</Text>
);
export const H2 = ({ children, style }: TP) => (
  <Text accessibilityRole="header" style={[s.h2, style]}>{children}</Text>
);
export const Body = ({ children, style, numberOfLines }: TP) => (
  <Text style={[s.body, style]} numberOfLines={numberOfLines}>{children}</Text>
);
export const Muted = ({ children, style, numberOfLines }: TP) => (
  <Text style={[s.muted, style]} numberOfLines={numberOfLines}>{children}</Text>
);
export const Mono = ({ children, style, numberOfLines }: TP) => (
  <Text style={[s.mono, style]} numberOfLines={numberOfLines}>{children}</Text>
);
/** Küçük, harf aralıklı, mono etiket (bölüm başlıkları, alan adları). */
export const Kicker = ({ children, style }: TP) => <Text style={[s.kicker, style]}>{children}</Text>;

// --- çizgiler -------------------------------------------------------------------------------------

export function Rule({ double, faint, style }: { double?: boolean; faint?: boolean; style?: ViewStyle }) {
  if (double) {
    return (
      <View style={[{ marginVertical: 10 }, style]}>
        <View style={[s.rule, { height: 2 }]} />
        <View style={[s.rule, { marginTop: 2 }]} />
      </View>
    );
  }
  return <View style={[s.rule, faint && { backgroundColor: paper.hairline }, { marginVertical: 10 }, style]} />;
}

// --- sayfa --------------------------------------------------------------------------------------

const NAV = [
  { href: '/', label: 'Meydan' },
  { href: '/karar-saati', label: 'Karar Saati' },
  { href: '/havale', label: 'Havale' },
  { href: '/yonetmelik', label: 'Yönetmelik' },
  { href: '/defter', label: 'Defter' },
] as const;

function issueNumber(d: Date): number {
  return Math.floor((d.getTime() - Date.UTC(2025, 0, 1)) / 86_400_000) + 1;
}

export function Masthead() {
  const { now } = useClock();
  const { me, logout } = useAuth();
  const path = usePathname();
  const { width } = useWindowDimensions();
  const narrow = width < 560;
  const today = new Date(now());
  return (
    <View style={{ marginBottom: 18 }}>
      <View style={s.mastTop}>
        <Kicker>Resmî kayıt · Sayı {issueNumber(today)}</Kicker>
        <Kicker style={{ textAlign: 'right' }}>{fmtLong(today)}</Kicker>
      </View>
      <Rule double style={{ marginTop: 6 }} />
      <Pressable
        onPress={() => router.push('/')}
        accessibilityRole="link"
        accessibilityLabel="Meşveret ana sayfa"
        style={{ alignItems: 'center', paddingVertical: narrow ? 4 : 8 }}
      >
        <Text style={[s.mastTitle, narrow && { fontSize: 40, lineHeight: 46, letterSpacing: 2 }]}>
          MEŞVERET
        </Text>
        <Text style={s.mastSub}>Oylamayla yönetilen forum — her karar kayda geçer</Text>
      </Pressable>
      <Rule style={{ marginBottom: 0 }} />
      <View style={s.nav}>
        {NAV.map((n) => {
          const active = n.href === '/' ? path === '/' : path.startsWith(n.href);
          return (
            <Link key={n.href} href={n.href} style={[s.navItem, active && s.navActive]}>
              {n.label}
            </Link>
          );
        })}
        <View style={{ flex: 1 }} />
        {me ? (
          <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center' }}>
            <Link href={`/profil/${encodeURIComponent(me.nickname)}`} style={s.navItem}>
              {me.nickname}
            </Link>
            <Pressable onPress={logout} accessibilityRole="button">
              <Text style={[s.navItem, { color: paper.muted }]}>çıkış</Text>
            </Pressable>
          </View>
        ) : (
          <Link href="/giris" style={[s.navItem, { color: paper.seal }]}>Giriş</Link>
        )}
      </View>
      <Rule double style={{ marginTop: 0 }} />
    </View>
  );
}

export function Footer() {
  return (
    <View style={{ marginTop: 48, alignItems: 'center', gap: 10 }}>
      <Rule faint style={{ alignSelf: 'stretch' }} />
      <Muted style={{ fontSize: 13 }}>Meşveret · kararlar ve silinen içerikler defterde kalır</Muted>
      {/* Mahzen teşvik edilmez: sade bir bağlantı, sayaç ya da bildirim yok. */}
      <Link href="/mahzen" style={s.cellarLink} accessibilityLabel="Mahzen">
        mahzen
      </Link>
    </View>
  );
}

export function Page({ children, bare }: { children: ReactNode; bare?: boolean }) {
  return (
    <ImageBackground
      source={grain}
      resizeMode="repeat"
      style={s.page}
      imageStyle={{ width: '100%', height: '100%' }}
    >
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={s.column}>
          {!bare && <Masthead />}
          {children}
          {!bare && <Footer />}
        </View>
      </ScrollView>
    </ImageBackground>
  );
}

export function Loading() {
  return (
    <View style={{ padding: 40, alignItems: 'center' }}>
      <ActivityIndicator color={paper.seal} />
      <Muted style={{ marginTop: 8 }}>Kayıtlar getiriliyor…</Muted>
    </View>
  );
}

/** Bağlantı gibi davranan dokunulabilir alan (satır, kart). */
export function PressLink({
  href,
  style,
  children,
  label,
}: {
  href: string;
  style?: ViewStyle | (ViewStyle | false | null | undefined)[];
  children: ReactNode;
  label?: string;
}) {
  return (
    <Pressable
      onPress={() => router.push(href as any)}
      accessibilityRole="link"
      accessibilityLabel={label}
      style={({ pressed, hovered }: any) => [
        StyleSheet.flatten(style),
        (pressed || hovered) && { backgroundColor: paper.sealWash },
        Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : null,
      ]}
    >
      {children}
    </Pressable>
  );
}

// --- mühür ve sansür şeridi ------------------------------------------------------------------------

/** Defter hash'i: mühür gibi durur, dokununca defter kaydını açar. */
export function Seal({ hash, label }: { hash?: string | null; label?: string }) {
  const pending = !hash;
  return (
    <Pressable
      disabled={pending}
      onPress={() => hash && router.push({ pathname: '/defter', params: { h: hash } })}
      accessibilityRole="link"
      accessibilityLabel={pending ? 'Defter kaydı bekleniyor' : `Defter kaydı ${shortHash(hash)}`}
      style={({ pressed }) => [s.seal, pending && { opacity: 0.5 }, pressed && { backgroundColor: paper.sealWash }]}
    >
      <Text style={s.sealText}>
        {label ? `${label} ` : ''}⌗ {pending ? 'mühürleniyor' : shortHash(hash)}
      </Text>
    </Pressable>
  );
}

/** Oylamayla silinmiş içeriğin yerine konan şerit. */
export function CensorStrip({ proposalId, hash }: { proposalId: number; hash?: string | null }) {
  return (
    <View style={s.strip} accessibilityLabel={`${proposalId} numaralı oylamayla silindi`}>
      <Link href={`/oneri/${proposalId}`}>
        <Text style={s.stripText}>
          ████ #{proposalId} NUMARALI OYLAMAYLA SİLİNDİ ████
        </Text>
      </Link>
      {hash ? (
        <Pressable onPress={() => router.push({ pathname: '/defter', params: { h: hash } })}>
          <Text style={[s.stripText, { opacity: 0.85, fontSize: 11 }]}>defterde: ⌗ {shortHash(hash)}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// --- küçük parçalar ---------------------------------------------------------------------------------

export function Tag({ children, tone = 'ink' }: { children: ReactNode; tone?: 'ink' | 'seal' | 'muted' }) {
  const color = tone === 'seal' ? paper.seal : tone === 'muted' ? paper.muted : paper.ink;
  return (
    <View style={[s.tag, { borderColor: color }]}>
      <Text style={[s.tagText, { color }]}>{children}</Text>
    </View>
  );
}

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  return (
    <View style={s.notice} accessibilityRole="alert">
      <Text style={[s.body, { color: paper.seal, fontFamily: fonts.serifMedium }]}>{e.message}</Text>
      {(e.violations ?? []).map((v, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 8, marginTop: 6 }}>
          <Text style={[s.mono, { color: paper.seal, fontSize: 12 }]}>{v.rule}</Text>
          <Text style={[s.body, { flex: 1, fontSize: 15 }]}>{v.message}</Text>
        </View>
      ))}
    </View>
  );
}

const isTextChild = (c: ReactNode) =>
  typeof c === 'string' || typeof c === 'number' || typeof c === 'boolean' || c == null;

export function InfoNotice({ children }: { children: ReactNode }) {
  // "Bu öneri {tarih} oylanacak." gibi araya değer giren metin bir dizi olarak gelir; View içinde
  // çıplak metin Android'de çöker, bu yüzden yalnızca metinden oluşan içerik Body'ye sarılır.
  const textual = Array.isArray(children) ? children.every(isTextChild) : isTextChild(children);
  return (
    <View style={[s.notice, { borderLeftColor: paper.ink }]}>
      {textual ? <Body style={{ fontSize: 15 }}>{children}</Body> : children}
    </View>
  );
}

type ButtonProps = {
  label: string;
  onPress: () => void | Promise<void>;
  variant?: 'primary' | 'secondary' | 'quiet';
  disabled?: boolean;
  small?: boolean;
  /** Aç/kapa düğmesi (ör. ilgi alanı): verilirse düğme onay kutusu olarak duyurulur. */
  checked?: boolean;
};

export function Button({ label, onPress, variant = 'primary', disabled, small, checked }: ButtonProps) {
  const [busy, setBusy] = useState(false);
  const press = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onPress();
    } finally {
      setBusy(false);
    }
  };
  const isDisabled = disabled || busy;
  if (variant === 'quiet') {
    return (
      <Pressable onPress={press} disabled={isDisabled} accessibilityRole="button" hitSlop={6}>
        <Text style={[s.quiet, isDisabled && { opacity: 0.5 }]}>{label}</Text>
      </Pressable>
    );
  }
  const primary = variant === 'primary';
  return (
    <Pressable
      onPress={press}
      disabled={isDisabled}
      accessibilityRole={checked === undefined ? 'button' : 'checkbox'}
      aria-checked={checked}
      aria-disabled={isDisabled}
      aria-busy={busy}
      style={({ pressed }) => [
        s.button,
        small && { paddingVertical: 6, paddingHorizontal: 10 },
        primary ? { backgroundColor: paper.seal, borderColor: paper.seal } : { borderColor: paper.ink },
        pressed && { transform: [{ translateY: 1 }] },
        isDisabled && { opacity: 0.45 },
      ]}
    >
      <Text style={[s.buttonText, { color: primary ? paper.sheet : paper.ink }, small && { fontSize: 11 }]}>
        {busy ? '…' : label}
      </Text>
    </Pressable>
  );
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ marginBottom: 14 }}>
      <Kicker style={{ marginBottom: 4 }}>{label}</Kicker>
      <TextInput
        placeholderTextColor={paper.muted}
        aria-label={label}
        {...props}
        onFocus={(e) => {
          setFocused(true);
          props.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          props.onBlur?.(e);
        }}
        style={[
          s.input,
          props.multiline && { minHeight: 110, textAlignVertical: 'top' },
          focused && { borderBottomColor: paper.seal, backgroundColor: paper.sheet },
          props.style,
        ]}
      />
      {hint ? <Muted style={{ fontSize: 13, marginTop: 4 }}>{hint}</Muted> : null}
    </View>
  );
}

/** Seçenekler arasından tek seçim (sade radyo listesi). */
export function Choice<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string; note?: string; disabled?: boolean }[];
  value: T | null;
  onChange: (v: T) => void;
}) {
  return (
    <View style={{ marginBottom: 14 }} accessibilityRole="radiogroup" accessibilityLabel={label}>
      <Kicker style={{ marginBottom: 6 }}>{label}</Kicker>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {options.map((o) => {
          const on = o.value === value;
          return (
            <Pressable
              key={o.value}
              disabled={o.disabled}
              onPress={() => onChange(o.value)}
              accessibilityRole="radio"
              aria-checked={on}
              aria-disabled={o.disabled}
              style={[s.choice, on && s.choiceOn, o.disabled && { opacity: 0.4 }]}
            >
              <Text style={[s.choiceText, on && { color: paper.sheet }]}>{o.label}</Text>
              {o.note ? <Text style={[s.choiceNote, on && { color: paper.bgDeep }]}>{o.note}</Text> : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function Countdown({ target, big }: { target: string | null; big?: boolean }) {
  const { now } = useClock();
  useTick(1000);
  if (!target) return <Mono>—</Mono>;
  const ms = new Date(target).getTime() - now();
  return (
    <Text
      style={[s.mono, big ? s.countBig : { fontSize: 16 }]}
      accessibilityLabel={`Kalan süre ${fmtCountdown(ms)}`}
    >
      {fmtCountdown(ms)}
    </Text>
  );
}

/** Başlık + sağda küçük not; gazete bölüm başlığı. */
export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <View style={{ marginTop: 22 }}>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
        <H2>{title}</H2>
        {aside}
      </View>
      <Rule style={{ marginTop: 4 }} />
      {children}
    </View>
  );
}

export const paperStyles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderColor: paper.hairline,
    backgroundColor: paper.sheet,
    padding: 14,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
});

const s = StyleSheet.create({
  page: { flex: 1, backgroundColor: paper.bg },
  scroll: { paddingHorizontal: layout.gutter, paddingTop: 18, paddingBottom: 40 },
  column: { width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center' },
  display: { fontFamily: fonts.serifDisplay, fontSize: 40, lineHeight: 44, color: paper.ink },
  h1: { fontFamily: fonts.serifBold, fontSize: 30, lineHeight: 36, color: paper.ink },
  h2: { fontFamily: fonts.serifBold, fontSize: 21, lineHeight: 26, color: paper.ink },
  body: { fontFamily: fonts.serif, fontSize: 17, lineHeight: 25, color: paper.ink },
  muted: { fontFamily: fonts.serifItalic, fontSize: 15, lineHeight: 21, color: paper.muted },
  mono: { fontFamily: fonts.mono, fontSize: 13, color: paper.ink },
  kicker: {
    fontFamily: fonts.monoMedium,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    color: paper.inkSoft,
  },
  rule: { height: 1, backgroundColor: paper.rule },
  mastTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  mastTitle: {
    fontFamily: fonts.serifDisplay,
    fontSize: 64,
    lineHeight: 70,
    letterSpacing: 6,
    color: paper.ink,
    textAlign: 'center',
  },
  mastSub: { fontFamily: fonts.serifItalic, fontSize: 15, color: paper.inkSoft, textAlign: 'center' },
  nav: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    columnGap: 18,
    rowGap: 6,
    paddingVertical: 8,
  },
  navItem: {
    fontFamily: fonts.monoMedium,
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: paper.ink,
  },
  navActive: { color: paper.seal, textDecorationLine: 'underline' },
  cellarLink: {
    fontFamily: fonts.mono,
    fontSize: 12,
    color: paper.muted,
    letterSpacing: 3,
    paddingVertical: 6,
  },
  seal: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: paper.seal,
    paddingHorizontal: 6,
    paddingVertical: 1,
    transform: [{ rotate: '-0.6deg' }],
  },
  sealText: { fontFamily: fonts.mono, fontSize: 11, color: paper.seal, letterSpacing: 0.5 },
  strip: {
    backgroundColor: paper.strip,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 8,
    alignItems: 'center',
    gap: 2,
  },
  stripText: {
    fontFamily: fonts.monoMedium,
    fontSize: 12,
    letterSpacing: 1.5,
    color: paper.stripText,
    textAlign: 'center',
  },
  tag: { borderWidth: 1, paddingHorizontal: 6, paddingVertical: 1, alignSelf: 'flex-start' },
  tagText: { fontFamily: fonts.monoMedium, fontSize: 10, letterSpacing: 1.2, textTransform: 'uppercase' },
  notice: {
    borderLeftWidth: 3,
    borderLeftColor: paper.seal,
    backgroundColor: paper.sheet,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 10,
  },
  button: {
    borderWidth: 1.5,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    alignSelf: 'flex-start',
    ...(Platform.OS === 'web' ? { cursor: 'pointer' as any } : null),
  },
  buttonText: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.5, textTransform: 'uppercase' },
  quiet: {
    fontFamily: fonts.monoMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    color: paper.seal,
    textDecorationLine: 'underline',
  },
  input: {
    fontFamily: fonts.serif,
    fontSize: 17,
    color: paper.ink,
    borderBottomWidth: 1.5,
    borderBottomColor: paper.ink,
    paddingVertical: 8,
    paddingHorizontal: 4,
    ...(Platform.OS === 'web' ? { outlineStyle: 'none' as any } : null),
  },
  choice: { borderWidth: 1, borderColor: paper.ink, paddingVertical: 6, paddingHorizontal: 10 },
  choiceOn: { backgroundColor: paper.ink },
  choiceText: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.ink, letterSpacing: 0.5 },
  choiceNote: { fontFamily: fonts.serifItalic, fontSize: 12, color: paper.muted },
  countBig: { fontSize: 44, letterSpacing: 2, fontFamily: fonts.monoMedium, color: paper.ink },
});
