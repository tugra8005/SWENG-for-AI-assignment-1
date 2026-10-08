/**
 * Meydan bileşenleri: resmî gazete / arşiv estetiği.
 * Kâğıt zemin, mürekkep, tek vurgu mühür bordosu; serif metin, mono hash ve sayılar.
 */
import { Link, router, usePathname } from 'expo-router';
import { Children, createContext, type ReactNode, type Ref, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  Animated,
  Image,
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
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError } from '@/api/client';
import { useAuth } from '@/lib/auth';
import { useClock, useTick } from '@/lib/clock';
import { fmtCountdown, fmtLong, fmtWeekdayTime, shortHash } from '@/lib/format';
import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { useNotifications } from '@/lib/notifications';
import { useApi } from '@/lib/useApi';
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
/** Takma ad kimliktir: büyük harfli bir etiketin içinde bile dönüştürülmez ("baris" "BARİS" olmaz). */
export const Nick = ({ children }: { children: ReactNode }) => (
  <Text style={{ textTransform: 'none', letterSpacing: 0.3 }}>{children}</Text>
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
  { href: '/takvim', label: 'Takvim' },
  { href: '/havale', label: 'Havale' },
  { href: '/yonetmelik', label: 'Yönetmelik' },
  { href: '/defter', label: 'Defter' },
] as const;

function issueNumber(d: Date): number {
  return Math.floor((d.getTime() - Date.UTC(2025, 0, 1)) / 86_400_000) + 1;
}

function NavLinks({ narrow }: { narrow?: boolean }) {
  const path = usePathname();
  const links = NAV.map((n) => {
    const active = n.href === '/' ? path === '/' : path.startsWith(n.href);
    return (
      <Link key={n.href} href={n.href} style={[s.navItem, narrow && s.navItemNarrow, active && s.navActive]}>
        {n.label}
      </Link>
    );
  });
  if (!narrow) return <>{links}</>;
  // Telefonda altı bölümün hepsi görünür: satıra yayılır, sığmazsa alta kırılır.
  // Önceki sürüm yatay kaydırıyordu; 375 px'te Havale, Yönetmelik ve Defter ekran dışında kalıyordu.
  return <View style={s.navNarrow}>{links}</View>;
}

/** Zil: View'larla çizilir (bkz. LockIcon); gövde, ağız ve tokmak. */
function BellGlyph({ color }: { color: string }) {
  return (
    <View style={{ width: 18, height: 18, alignItems: 'center' }}>
      <View style={{ width: 2.5, height: 2, backgroundColor: color, borderRadius: 1 }} />
      <View
        style={{
          width: 12,
          height: 10,
          borderWidth: 1.6,
          borderBottomWidth: 0,
          borderColor: color,
          borderTopLeftRadius: 6,
          borderTopRightRadius: 6,
        }}
      />
      <View style={{ width: 16, height: 1.6, backgroundColor: color, borderRadius: 1 }} />
      <View
        style={{
          width: 5,
          height: 2.5,
          marginTop: 1,
          backgroundColor: color,
          borderBottomLeftRadius: 2.5,
          borderBottomRightRadius: 2.5,
        }}
      />
    </View>
  );
}

/** Bildirimler: okunmamış sayısı rozetle; sayfa değişince sayı tazelenir. */
function Bell() {
  const { unread, refresh } = useNotifications();
  const path = usePathname();
  useEffect(() => {
    refresh();
  }, [path, refresh]);
  const label = unread ? `Bildirimler: ${unread} okunmamış` : 'Bildirimler';
  return (
    <Pressable
      onPress={() => router.push('/bildirimler')}
      accessibilityRole="link"
      accessibilityLabel={label}
      hitSlop={8}
      style={Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : null}
    >
      <BellGlyph color={path === '/bildirimler' ? paper.seal : paper.ink} />
      {unread ? (
        <View style={s.badge}>
          <Text style={s.badgeText}>{unread > 9 ? '9+' : unread}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

/** Arama: büyüteç View'larla çizilir (cam halka ve sap); web'de "/" tuşu da aramayı açar. */
function SearchButton() {
  const path = usePathname();
  const color = path === '/ara' ? paper.seal : paper.ink;
  return (
    <Pressable
      onPress={() => router.push('/ara')}
      accessibilityRole="link"
      accessibilityLabel="Ara"
      hitSlop={8}
      style={[{ width: 18, height: 18 }, Platform.OS === 'web' ? ({ cursor: 'pointer' } as any) : null]}
    >
      <View style={{ width: 13, height: 13, borderRadius: 7, borderWidth: 2, borderColor: color }} />
      <View
        style={{
          position: 'absolute', width: 7, height: 2.5, backgroundColor: color, right: 0, bottom: 2,
          transform: [{ rotate: '45deg' }],
        }}
      />
    </Pressable>
  );
}

/** Oturum bağlantıları. Takma ad kimliktir: büyük harfe çevrilmez. */
function Account({ small }: { small?: boolean }) {
  const { me, logout } = useAuth();
  const text = small ? s.accountSmall : s.account;
  if (!me) {
    return (
      <View style={{ flexDirection: 'row', gap: small ? 12 : 14, alignItems: 'center' }}>
        <SearchButton />
        <Link href="/giris" style={[text, { color: paper.seal }]}>
          giriş
        </Link>
      </View>
    );
  }
  return (
    // Dar ekranda uzun takma ad kısalır ("MostlyHarm…"); zil ve çıkış her zaman görünür.
    <View style={{ flexDirection: 'row', gap: small ? 12 : 14, alignItems: 'center', flexShrink: 1, minWidth: 0 }}>
      <SearchButton />
      <Bell />
      <Link
        href={`/profil/${encodeURIComponent(me.nickname)}`}
        numberOfLines={1}
        style={[text, { color: paper.ink, flexShrink: 1 }]}
      >
        {me.nickname}
      </Link>
      <Pressable onPress={logout} accessibilityRole="button">
        <Text style={text}>çıkış</Text>
      </Pressable>
    </View>
  );
}

/** Bölüm adı: iç sayfaların ince künyesinde ve künye satırında. */
function sectionOf(path: string): string {
  const map: [string, string][] = [
    ['/karar-saati', 'Karar Saati'],
    ['/takvim', 'Takvim'],
    ['/etkinlik', 'Takvim · Etkinlik'],
    ['/dilekce', 'Meydan · Dilekçe'],
    ['/ara', 'Arama'],
    ['/havale', 'Havale'],
    ['/yonetmelik', 'Yönetmelik'],
    ['/defter', 'Defter'],
    ['/profil', 'Profil'],
    ['/bildirimler', 'Bildirimler'],
    ['/nasil-isler', 'Kılavuz'],
    ['/konu', 'Meydan · Konu'],
    ['/oneri', 'Meydan · Öneri'],
    ['/alan', 'Meydan · Alan'],
    ['/mesaj', 'Meydan · Mesaj'],
    ['/ifsa', 'Mahzen · İfşa'],
    ['/giris', 'Kimlik'],
    ['/kayit', 'Kimlik'],
    ['/dogrula', 'Kimlik'],
  ];
  return map.find(([p]) => path.startsWith(p))?.[1] ?? 'Meydan';
}

const sealMark = require('@/assets/images/seal-mark.png');

/** Defterin son kaydı (künye kulağı, alt bilgi). */
type LedgerRecent = { seq: number; hash: string | null; records: { seq: number; type: string; label: string; ts: string; hash: string }[] };

/** Gazetenin başlık kulakları: solda Karar Saati, sağda defterin son mührü. */
function Ear({ side, children }: { side: 'left' | 'right'; children: ReactNode }) {
  return <View style={[s.ear, side === 'right' && { alignItems: 'flex-end' }]}>{children}</View>;
}

function DecisionEar() {
  const { status } = useClock();
  const open = status?.open_session;
  return (
    <Ear side="left">
      <Kicker style={open ? { color: paper.seal } : undefined}>{open ? 'Karar Saati açık' : "Karar Saati'ne"}</Kicker>
      {status ? (
        <Countdown target={open ? open.closes_at : status.next_scheduled_at} color={open ? paper.seal : paper.ink} />
      ) : (
        <Text style={s.earValue}>…</Text>
      )}
      <Text style={s.earNote}>{open ? 'pencerenin kapanmasına' : fmtWeekdayTime(status?.next_scheduled_at)}</Text>
    </Ear>
  );
}

function LedgerEar() {
  const { data } = useApi<LedgerRecent>('/ledger/recent?limit=1', 30_000);
  return (
    <Ear side="right">
      <Kicker>Defter</Kicker>
      <Text style={s.earValue}>{data ? `${data.seq} kayıt` : '…'}</Text>
      {data?.hash ? <Seal hash={data.hash} label="son" /> : null}
    </Ear>
  );
}

export function Masthead() {
  const { now } = useClock();
  const { width } = useWindowDimensions();
  const path = usePathname();
  const narrow = width < 560;
  const today = new Date(now());
  // Gazetelerde iç sayfalar ince başlık taşır; tam künye yalnızca ön sayfadadır.
  if (!narrow && path !== '/') return <SlimMasthead today={today} path={path} />;
  const ears = width >= 900;
  const title = (
    <Pressable
      onPress={() => router.push('/')}
      accessibilityRole="link"
      accessibilityLabel="Meşveret ana sayfa"
      style={{ alignItems: 'center', paddingVertical: narrow ? 4 : 8, flex: ears ? 1 : undefined }}
    >
      <Text style={[s.mastTitle, narrow && { fontSize: 40, lineHeight: 46, letterSpacing: 2 }]}>
        MEŞVERET
      </Text>
      <Text style={s.mastSub}>Oylamayla yönetilen forum — her karar kayda geçer</Text>
    </Pressable>
  );
  return (
    <View style={{ marginBottom: 18 }}>
      <View style={s.mastTop}>
        {narrow ? (
          <>
            <Kicker style={{ flexShrink: 1 }}>{fmtLong(today)}</Kicker>
            <Account small />
          </>
        ) : (
          <>
            <Kicker>Resmî kayıt · Sayı {issueNumber(today)}</Kicker>
            <Kicker style={{ textAlign: 'right' }}>{fmtLong(today)}</Kicker>
          </>
        )}
      </View>
      <Rule double style={{ marginTop: 6 }} />
      {ears ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 16 }}>
          <DecisionEar />
          {title}
          <LedgerEar />
        </View>
      ) : (
        title
      )}
      <Rule style={{ marginBottom: 0 }} />
      <View style={s.nav}>
        {narrow ? (
          <NavLinks narrow />
        ) : (
          <>
            <NavLinks />
            <View style={{ flex: 1 }} />
            <Account />
          </>
        )}
      </View>
      <Rule double style={{ marginTop: 0 }} />
    </View>
  );
}

/** İç sayfaların ince künyesi (560 px ve üstü): künye satırı, mühür, MEŞVERET, menü ve hesap. */
function SlimMasthead({ today, path }: { today: Date; path: string }) {
  // Tablette (560–899 px) mühür süsü gizlenir, başlık küçülür: satır tek sıraya sığar.
  const roomy = useWindowDimensions().width >= 900;
  return (
    <View style={{ marginBottom: 18 }}>
      <View style={s.mastTop}>
        <Kicker>
          Sayı {issueNumber(today)} · {sectionOf(path)}
        </Kicker>
        <Kicker style={{ textAlign: 'right' }}>{fmtLong(today)}</Kicker>
      </View>
      <Rule double style={{ marginTop: 6, marginBottom: 0 }} />
      <View style={[s.slim, !roomy && { gap: 14 }]}>
        <Pressable
          onPress={() => router.push('/')}
          accessibilityRole="link"
          accessibilityLabel="Meşveret ana sayfa"
          style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}
        >
          {roomy ? <Image source={sealMark} style={{ width: 30, height: 30 }} accessibilityIgnoresInvertColors /> : null}
          <Text style={[s.slimTitle, !roomy && { fontSize: 21, letterSpacing: 1.5 }]}>MEŞVERET</Text>
        </Pressable>
        <View style={[s.slimNav, !roomy && { columnGap: 12 }]}>
          <NavLinks />
        </View>
        <View style={{ flex: 1 }} />
        <Account />
      </View>
      <Rule double style={{ marginTop: 0 }} />
    </View>
  );
}

/** Telefonda ana sayfa dışındaki başlık: ince, yapışkan çubuk. Üstte küçük MEŞVERET ve hesap
 * (zil, takma ad, çıkış), altta beş bölümün tamamı. Tarih ana sayfanın başlığında durur. */
function CompactBar() {
  return (
    <View style={s.compact}>
      <View style={s.compactTop}>
        <Pressable onPress={() => router.push('/')} accessibilityRole="link" accessibilityLabel="Meşveret ana sayfa">
          <Text style={s.compactTitle}>MEŞVERET</Text>
        </Pressable>
        <Account small />
      </View>
      <View style={s.compactRow}>
        <NavLinks narrow />
      </View>
      <View style={[s.rule, { height: 2 }]} />
      <View style={[s.rule, { marginTop: 2 }]} />
    </View>
  );
}

export function Footer() {
  const { now } = useClock();
  const tip = useApi<LedgerRecent>('/ledger/recent?limit=1').data;
  return (
    <View style={{ marginTop: 48, alignItems: 'center', gap: 10 }}>
      <Rule double style={{ alignSelf: 'stretch' }} />
      <Image source={sealMark} style={{ width: 44, height: 44, opacity: 0.85 }} accessibilityIgnoresInvertColors />
      <Muted style={{ fontSize: 13 }}>Meşveret · kararlar ve silinen içerikler defterde kalır</Muted>
      {/* Künye: gazetenin arka sayfasındaki yayın bilgisi. */}
      <Text style={s.colophon}>
        Sayı {issueNumber(new Date(now()))}
        {tip ? ` · defter ${tip.seq} kayıt, son mühür ⌗ ${shortHash(tip.hash ?? '')}` : ''} · dizgi: Newsreader ve IBM Plex Mono
      </Text>
      <Link href="/nasil-isler" style={s.guideLink}>
        Nasıl işler? Kılavuz →
      </Link>
      {/* Mahzen teşvik edilmez: sade bir bağlantı, sayaç ya da bildirim yok. */}
      <Link href="/mahzen" style={s.cellarLink} accessibilityLabel="Mahzen">
        mahzen
      </Link>
    </View>
  );
}

type ScrollApi = { register: (id: string, node: View | null) => void; scrollTo: (id: string) => void };
const ScrollCtx = createContext<ScrollApi | null>(null);

/** Sayfa içi bağlantı hedefi (ör. içindekiler). */
export function Anchor({ id, children }: { id: string; children: ReactNode }) {
  const ctx = useContext(ScrollCtx);
  return (
    <View nativeID={id} ref={(node) => ctx?.register(id, node)}>
      {children}
    </View>
  );
}

/** Sayfanın kendi kaydırma alanında bir Anchor'a kaydırır. */
export function useScrollTo(): (id: string) => void {
  return useContext(ScrollCtx)?.scrollTo ?? (() => undefined);
}

/** İfşa geçişi için: zemin rengi, kâğıt dokusu ve künye (başlık, alt bilgi) canlandırılır. */
export type PageReveal = {
  background: Animated.AnimatedInterpolation<string>;
  paper: Animated.AnimatedInterpolation<number>;
  chrome: Animated.AnimatedInterpolation<number>;
};

export function Page({
  children,
  bare,
  reveal,
  reading,
}: {
  children: ReactNode;
  bare?: boolean;
  reveal?: PageReveal;
  /** Uzun metin ya da form: geniş ekranda da okuma sütununda kalır (başlık geniş durur). */
  reading?: boolean;
}) {
  const path = usePathname();
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const compact = !bare && width < 560 && path !== '/';
  const wide = width >= layout.wideMin;
  const scrollRef = useRef<ScrollView>(null);
  const columnRef = useRef<View>(null);
  const anchors = useRef(new Map<string, View>());
  const scrollApi = useMemo<ScrollApi>(
    () => ({
      register: (id, node) => {
        if (node) anchors.current.set(id, node);
        else anchors.current.delete(id);
      },
      scrollTo: (id) => {
        const target = anchors.current.get(id);
        const column = columnRef.current;
        if (!target || !column) return;
        target.measureLayout(column, (_x, y) => scrollRef.current?.scrollTo({ y: Math.max(0, y + 6), animated: true }));
      },
    }),
    [],
  );
  const chrome = reveal ? { opacity: reveal.chrome } : null;
  return (
    <Animated.View style={[s.page, { paddingTop: insets.top }, reveal && { backgroundColor: reveal.background }]}>
      {/* Kâğıt dokusu; ifşa geçişinde siyahtan kâğıda dönerken belirir. */}
      <Animated.Image
        source={grain}
        resizeMode="repeat"
        style={[StyleSheet.absoluteFill, { width: '100%', height: '100%' }, reveal && { opacity: reveal.paper }]}
      />
      {compact ? (
        <Animated.View style={chrome}>
          <CompactBar />
        </Animated.View>
      ) : null}
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={[
          s.scroll,
          wide && { paddingHorizontal: layout.wideGutter },
          compact && { paddingTop: 14 },
          { paddingBottom: 40 + insets.bottom },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <ScrollCtx.Provider value={scrollApi}>
          <View ref={columnRef} style={[s.column, wide && { maxWidth: layout.wideMaxWidth }]}>
            {!bare && !compact && (
              <Animated.View style={chrome}>
                <Masthead />
              </Animated.View>
            )}
            {wide && reading ? <View style={s.reading}>{children}</View> : children}
            {!bare && (
              <Animated.View style={chrome}>
                <Footer />
              </Animated.View>
            )}
          </View>
        </ScrollCtx.Provider>
      </ScrollView>
    </Animated.View>
  );
}

/** Yükleniyor: dizgi provası gibi gri satırlar, hafif nabız. Azaltılmış harekette sabit. */
export function Loading() {
  const reduced = useReducedMotion();
  const pulse = useAnimatedValue(reduced ? 0.75 : 0.45);
  useEffect(() => {
    if (reduced) return;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.95, duration: 700, useNativeDriver: false }),
        Animated.timing(pulse, { toValue: 0.45, duration: 700, useNativeDriver: false }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse, reduced]);
  return (
    <Animated.View
      accessibilityRole="progressbar"
      accessibilityLabel="Kayıtlar getiriliyor"
      style={{ paddingVertical: 24, gap: 10, opacity: pulse }}
    >
      <View style={[s.proof, { width: '38%', height: 14, backgroundColor: paper.hairline }]} />
      {['96%', '88%', '92%', '61%'].map((w, i) => (
        <View key={i} style={[s.proof, { width: w as any }]} />
      ))}
      <Muted style={{ fontSize: 13, marginTop: 2 }}>dizgi provası · kayıtlar getiriliyor…</Muted>
    </Animated.View>
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

/** Büyük baş harf: paragrafın ilk harfi büyük ve bordo, satırın üstüne yükselir. React Native metni
 * harfin etrafından akıtamadığı için gerçek "düşen" baş harf değildir. Harfle başlamayan metin olduğu
 * gibi kalır. */
export function InitialText({ text, style }: { text: string; style?: TextStyle | TextStyle[] }) {
  const body = text.trimStart();
  const first = body.charAt(0);
  if (!/\p{L}/u.test(first)) return <Text style={style}>{text}</Text>;
  return (
    <Text style={style}>
      <Text style={s.initial}>{first}</Text>
      {body.slice(1)}
    </Text>
  );
}

// --- mühür ve sansür şeridi ------------------------------------------------------------------------

/** Defter hash'i: mühür gibi durur, dokununca defter kaydını açar. */
/** Mührün eğimi hash'ten çıkar: her mühür biraz farklı basılmış gibi durur, ama hep aynı açıyla. */
function sealTilt(hash?: string | null): string {
  if (!hash) return '0deg';
  const n = parseInt(hash.slice(-2), 16);
  return `${((n % 7) - 3) * 0.6}deg`;
}

export function Seal({ hash, label }: { hash?: string | null; label?: string }) {
  const pending = !hash;
  return (
    <Pressable
      disabled={pending}
      onPress={() => hash && router.push({ pathname: '/defter', params: { h: hash } })}
      accessibilityRole="link"
      accessibilityLabel={pending ? 'Defter kaydı bekleniyor' : `Defter kaydı ${shortHash(hash)}`}
      style={({ pressed, hovered }: any) => [
        s.seal,
        { transform: [{ rotate: sealTilt(hash) }] },
        pending && { opacity: 0.5, borderStyle: 'dashed' },
        (pressed || hovered) && { backgroundColor: paper.sealWash },
      ]}
    >
      {/* Islak mühür: dış çerçeve kalın, içte ince ikinci çizgi. */}
      <View style={s.sealInner}>
        <Text style={s.sealText}>
          {label ? `${label} ` : ''}⌗ {pending ? 'mühürleniyor' : shortHash(hash)}
        </Text>
      </View>
    </Pressable>
  );
}

/** Oylamayla silinmiş içeriğin yerine konan şerit. */
/** Değiştirilemez madde işareti: bordo gövde ve açık kilit halkası. */
export function LockIcon({ size = 14, color = paper.seal }: { size?: number; color?: string }) {
  const w = size * 0.8;
  return (
    <View
      accessibilityRole="image"
      aria-label="değiştirilemez"
      style={{ width: w, height: size, alignItems: 'center', justifyContent: 'flex-end' }}
    >
      <View
        style={{
          width: w * 0.62,
          height: size * 0.5,
          borderWidth: Math.max(1.5, size / 9),
          borderBottomWidth: 0,
          borderColor: color,
          borderTopLeftRadius: w,
          borderTopRightRadius: w,
          marginBottom: -1,
        }}
      />
      <View style={{ width: w, height: size * 0.56, backgroundColor: color, borderRadius: 1.5 }} />
    </View>
  );
}

export type DeletionBasis = { rules: string[]; own: boolean };

/** "#214 · IK-2 gereğince silindi" — silmenin dayandığı içerik kuralı ya da yazarın isteği. */
export function deletionLabel(proposalId: number, basis?: DeletionBasis | null): string {
  if (basis?.own) return `#${proposalId} · yazarının isteğiyle silindi`;
  if (basis?.rules.length) return `#${proposalId} · ${basis.rules.join(', ')} gereğince silindi`;
  return `#${proposalId} numaralı oylamayla silindi`;
}

export function CensorStrip({
  proposalId,
  hash,
  basis,
}: {
  proposalId: number;
  hash?: string | null;
  basis?: DeletionBasis | null;
}) {
  const label = deletionLabel(proposalId, basis);
  const { width } = useWindowDimensions();
  // Telefonda süs blokları gizlenir; metin tek satırda ve ortada kalır.
  const blocks = width >= 560;
  return (
    <View style={s.strip} aria-label={label}>
      <Link href={`/oneri/${proposalId}`}>
        <Text style={s.stripText} numberOfLines={1}>
          {blocks ? `████ ${label} ████` : label}
        </Text>
      </Link>
      {hash ? (
        <Pressable onPress={() => router.push({ pathname: '/defter', params: { h: hash } })}>
          <Text style={[s.stripText, { fontSize: 12 }]} numberOfLines={1}>
            defterde: ⌗ {shortHash(hash)}
          </Text>
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
  /** quiet: bordo bağlantı; minor: küçük gri, istisnai eylemler için (silme öner gibi). */
  variant?: 'primary' | 'secondary' | 'quiet' | 'minor';
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
  if (variant === 'quiet' || variant === 'minor') {
    return (
      <Pressable onPress={press} disabled={isDisabled} accessibilityRole="button" hitSlop={6}>
        {({ hovered }: any) => (
          <Text
            style={[
              variant === 'quiet' ? s.quiet : s.minor,
              variant === 'minor' && hovered && !isDisabled && { textDecorationLine: 'underline' },
              isDisabled && s.quietOff,
            ]}
          >
            {label}
          </Text>
        )}
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
        pressed && !isDisabled && { transform: [{ translateY: 1 }] },
        // Devre dışı her düğme aynı görünür: gri çerçeve, gri yazı (soluk bordo yok).
        isDisabled && !busy && s.buttonOff,
      ]}
    >
      <Text
        style={[
          s.buttonText,
          { color: primary ? paper.sheet : paper.ink },
          small && { fontSize: 11 },
          isDisabled && !busy && { color: paper.muted },
        ]}
      >
        {busy ? '…' : label}
      </Text>
    </Pressable>
  );
}

export function Field({
  label,
  hint,
  error,
  inputRef,
  ...props
}: TextInputProps & { label: string; hint?: string; error?: string; inputRef?: Ref<TextInput> }) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ marginBottom: 14 }}>
      <Kicker style={{ marginBottom: 4 }}>{label}</Kicker>
      <TextInput
        ref={inputRef}
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
          error ? { borderBottomColor: paper.seal, borderBottomWidth: 2 } : null,
          props.style,
        ]}
      />
      {/* Yazarken değişen uyarı ekran okuyucuya kibarca okunur; kutu hep yerinde durur. */}
      <View aria-live="polite">
        {error ? (
          <Text style={[s.body, { fontSize: 13, lineHeight: 19, marginTop: 4, color: paper.seal, fontFamily: fonts.serifMedium }]}>
            {error}
          </Text>
        ) : hint ? (
          <Muted style={{ fontSize: 13, marginTop: 4 }}>{hint}</Muted>
        ) : null}
      </View>
    </View>
  );
}

/** Tek seçimlik listenin bir seçeneği (radyo). */
export function ChoiceChip({
  label,
  note,
  on,
  disabled,
  onPress,
}: {
  label: string;
  note?: string;
  on: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      accessibilityRole="radio"
      aria-checked={on}
      aria-disabled={disabled}
      style={[s.choice, on && s.choiceOn, disabled && !on && s.buttonOff]}
    >
      <Text style={[s.choiceText, on && { color: paper.sheet }, disabled && !on && { color: paper.muted }]}>
        {label}
      </Text>
      {note ? <Text style={[s.choiceNote, on && { color: paper.bgDeep }]}>{note}</Text> : null}
    </Pressable>
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
        {options.map((o) => (
          <ChoiceChip
            key={o.value}
            label={o.label}
            note={o.note}
            on={o.value === value}
            disabled={o.disabled}
            onPress={() => onChange(o.value)}
          />
        ))}
      </View>
    </View>
  );
}

export function Countdown({
  target,
  big,
  color = paper.ink,
  prefix,
}: {
  target: string | null;
  big?: boolean;
  /** Koyu zeminde açık renk verilir; aksi hâlde sayı zeminle kaybolur. */
  color?: string;
  /** "kapanışa" gibi küçük önek. */
  prefix?: string;
}) {
  const { now } = useClock();
  useTick(1000);
  if (!target) return <Mono style={{ color }}>—</Mono>;
  const ms = new Date(target).getTime() - now();
  return (
    <Text
      style={[s.mono, big ? s.countBig : { fontSize: 16 }, { color }]}
      accessibilityLabel={`${prefix ? `${prefix} ` : 'Kalan süre '}${fmtCountdown(ms)}`}
    >
      {prefix ? <Text style={s.countPrefix}>{prefix} </Text> : null}
      {fmtCountdown(ms)}
    </Text>
  );
}

/** Başlık + sağda küçük not; gazete bölüm başlığı. */
export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <View style={{ marginTop: 22 }}>
      {/* Not sığmazsa alt satıra iner; Android'de satırdan taşmaz. */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', columnGap: 8 }}>
        <H2 style={{ flexShrink: 1 }}>{title}</H2>
        {aside ? <View style={{ flexShrink: 1, marginLeft: 'auto' }}>{aside}</View> : null}
      </View>
      <Rule style={{ marginTop: 4 }} />
      {children}
    </View>
  );
}

// --- geniş ekran düzeni ---------------------------------------------------------------------------
//
// Telefon (< 560 px) ve tablet tek sütundur. Geniş ekranda (≥ layout.wideMin) sayfa gazete sayfası gibi
// sütunlara bölünür: ana sütun, ince sütun çizgisiyle ayrılmış yan sütun, eşit sütunlu ızgaralar.
// Bileşenler yalnızca geniş ekranda çağrılır; dar ekranda sayfa kendi tek sütunlu sırasını çizer.

export function useWide(): boolean {
  const { width } = useWindowDimensions();
  return width >= layout.wideMin;
}

/** Web'de kaydırırken üstte kalır (yan sütun, içindekiler). */
const stickyTop = Platform.OS === 'web' ? ({ position: 'sticky', top: 12 } as any) : null;

/** Ana sütun ve sütun çizgisiyle ayrılmış yan sütun. */
export function Columns({
  main,
  side,
  sideWidth = 340,
  sideLeft,
  stickySide,
  ruleColor = paper.hairline,
}: {
  main: ReactNode;
  side: ReactNode;
  sideWidth?: number;
  sideLeft?: boolean;
  stickySide?: boolean;
  /** Mahzen'de sütun çizgisi amberdir. */
  ruleColor?: string;
}) {
  const gap = layout.columnGap;
  const rail = (
    <View
      style={[
        { width: sideWidth },
        sideLeft
          ? { paddingRight: gap, borderRightWidth: 1, borderRightColor: ruleColor }
          : { paddingLeft: gap, borderLeftWidth: 1, borderLeftColor: ruleColor },
      ]}
    >
      <View style={stickySide ? stickyTop : null}>{side}</View>
    </View>
  );
  return (
    <View style={{ flexDirection: 'row', alignItems: 'stretch' }}>
      {sideLeft ? rail : null}
      <View style={[{ flex: 1, minWidth: 0 }, sideLeft ? { paddingLeft: gap } : { paddingRight: gap }]}>{main}</View>
      {sideLeft ? null : rail}
    </View>
  );
}

/** Eşit iki sütun; arada sütun çizgisi. */
export function Split({ left, right }: { left: ReactNode; right: ReactNode }) {
  const gap = layout.columnGap;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'stretch' }}>
      <View style={{ flex: 1, minWidth: 0, paddingRight: gap }}>{left}</View>
      <View style={{ flex: 1, minWidth: 0, paddingLeft: gap, borderLeftWidth: 1, borderLeftColor: paper.hairline }}>
        {right}
      </View>
    </View>
  );
}

/** Eşit sütunlu ızgara: sütun sayısı genişlikten çıkar (her sütun en az ``min``). Dar alanda tek sütun.
 * ``ruled``: sütunlar arasında gazete sütun çizgisi. */
export function Grid({
  min = 300,
  gap = layout.columnGap,
  rowGap = gap,
  ruled,
  children,
}: {
  min?: number;
  gap?: number;
  rowGap?: number;
  ruled?: boolean;
  children: ReactNode;
}) {
  const [w, setW] = useState(0);
  const cols = w ? Math.max(1, Math.floor((w + gap) / (min + gap))) : 1;
  const items = Children.toArray(children);
  const cell = (i: number): ViewStyle => {
    if (cols === 1) return { width: '100%' };
    if (!ruled) return { width: (w - gap * (cols - 1)) / cols };
    const col = i % cols;
    return {
      width: w / cols,
      paddingLeft: col ? gap / 2 : 0,
      paddingRight: col < cols - 1 ? gap / 2 : 0,
      borderLeftWidth: col ? 1 : 0,
      borderLeftColor: paper.hairline,
    };
  };
  return (
    <View
      onLayout={(e) => setW(e.nativeEvent.layout.width)}
      style={{ flexDirection: 'row', flexWrap: 'wrap', columnGap: ruled ? 0 : gap, rowGap }}
    >
      {items.map((child, i) => (
        <View key={i} style={cell(i)}>
          {child}
        </View>
      ))}
    </View>
  );
}

/** Sayfa başlığı: geniş ekranda başlık solda, açıklama sağda (gazete başlığı ve spotu); dar ekranda alt alta. */
export function PageHead({ kicker, title, children }: { kicker: ReactNode; title: string; children?: ReactNode }) {
  const wide = useWide();
  const head = (
    <View style={wide ? { width: '36%', paddingRight: layout.columnGap } : undefined}>
      <Kicker>{kicker}</Kicker>
      <H1>{title}</H1>
    </View>
  );
  if (!wide) {
    return (
      <View>
        {head}
        {children}
        <Rule double />
      </View>
    );
  }
  return (
    <View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-start' }}>
        {head}
        <View style={{ flex: 1, gap: 6, paddingLeft: layout.columnGap, borderLeftWidth: 1, borderLeftColor: paper.hairline }}>
          {children}
        </View>
      </View>
      <Rule double />
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
  reading: { width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center' },
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
  ear: { width: 190, minHeight: 82, justifyContent: 'center', borderWidth: 1, borderColor: paper.ink, paddingHorizontal: 10, paddingVertical: 8, gap: 3, backgroundColor: paper.sheet },
  earValue: { fontFamily: fonts.monoBold, fontSize: 15, color: paper.ink },
  earNote: { fontFamily: fonts.serifItalic, fontSize: 12, color: paper.inkSoft },
  slim: { flexDirection: 'row', alignItems: 'center', gap: 22, paddingVertical: 8, flexWrap: 'wrap' },
  slimTitle: { fontFamily: fonts.serifDisplay, fontSize: 26, lineHeight: 30, letterSpacing: 2.5, color: paper.ink },
  slimNav: { flexDirection: 'row', alignItems: 'center', columnGap: 18, rowGap: 6, flexWrap: 'wrap' },
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
  navItemNarrow: { fontSize: 11, letterSpacing: 0.4 },
  navNarrow: {
    flex: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    columnGap: 10,
    rowGap: 4,
  },
  navActive: { color: paper.seal, textDecorationLine: 'underline' },
  badge: {
    position: 'absolute',
    top: -5,
    right: -8,
    minWidth: 15,
    height: 15,
    paddingHorizontal: 3,
    borderRadius: 8,
    backgroundColor: paper.seal,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { fontFamily: fonts.monoBold, fontSize: 9, lineHeight: 11, color: paper.bg },
  account: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 0.6, color: paper.muted },
  accountSmall: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 0.4, color: paper.muted },
  compact: { paddingHorizontal: layout.gutter, paddingTop: 6 },
  compactTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  compactRow: { flexDirection: 'row', alignItems: 'center', paddingTop: 6, paddingBottom: 7 },
  compactTitle: { fontFamily: fonts.serifDisplay, fontSize: 19, letterSpacing: 1.5, color: paper.ink },
  guideLink: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 0.6, color: paper.seal, textDecorationLine: 'underline' },
  cellarLink: {
    fontFamily: fonts.mono,
    fontSize: 12,
    color: paper.muted,
    letterSpacing: 3,
    paddingVertical: 6,
  },
  seal: {
    alignSelf: 'flex-start',
    borderWidth: 1.5,
    borderColor: paper.seal,
    padding: 1.5,
  },
  sealText: { fontFamily: fonts.monoMedium, fontSize: 11, color: paper.seal, letterSpacing: 0.6 },
  sealInner: { borderWidth: 0.75, borderColor: paper.seal, paddingHorizontal: 5, paddingVertical: 1 },
  proof: { height: 9, backgroundColor: paper.bgDeep },
  initial: { fontFamily: fonts.serifDisplay, fontSize: 46, color: paper.seal },
  colophon: { fontFamily: fonts.mono, fontSize: 10, letterSpacing: 0.6, color: paper.muted, textAlign: 'center', paddingHorizontal: 12 },
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
  buttonOff: { backgroundColor: 'transparent', borderColor: paper.disabled },
  quietOff: { color: paper.muted, textDecorationLine: 'none' },
  minor: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 0.4, color: paper.muted },
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
    lineHeight: 26,
    color: paper.ink,
    borderBottomWidth: 1.5,
    borderBottomColor: paper.ink,
    paddingVertical: 8,
    paddingHorizontal: 4,
    ...(Platform.OS === 'web' ? { outlineStyle: 'none' as any } : null),
  },
  choice: { borderWidth: 1, borderColor: paper.ink, paddingVertical: 6, paddingHorizontal: 10, alignSelf: 'flex-start' },
  choiceOn: { backgroundColor: paper.ink },
  choiceText: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.ink, letterSpacing: 0.5 },
  choiceNote: { fontFamily: fonts.serifItalic, fontSize: 12, color: paper.muted },
  countBig: { fontSize: 44, letterSpacing: 2, fontFamily: fonts.monoMedium, color: paper.ink },
  countPrefix: { fontSize: 15, letterSpacing: 0.5, fontFamily: fonts.monoMedium },
});
