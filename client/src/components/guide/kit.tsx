/**
 * Kılavuz şekillerinin ortak parçaları (bkz. app/nasil-isler.tsx).
 *
 * Her şekil tek bir zaman değeri üzerinden çizilir: ``t`` 0'dan 1'e doğrusal ilerler, sonda bir süre
 * bekler ve baştan başlar. Şekildeki her hareket ``t``'nin bir aralığına bağlıdır (anahtar kare).
 * Azaltılmış harekette ``t`` 1'de durur; son kare hikâyenin tamamını gösterecek biçimde kurulur,
 * altındaki açıklama metni de aynı şeyi söyler.
 */
import { type ReactNode, useEffect } from 'react';
import { Animated, Easing, StyleSheet, Text, type TextStyle, View, type ViewStyle } from 'react-native';

import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { fonts, paper } from '@/theme/tokens';

export type T = Animated.Value;

/** Döngüsel zaman çizelgesi: ``duration`` ms'de 0 → 1, ``hold`` ms son hâlde bekler. */
export function useTimeline(duration: number, hold = 2600): T {
  const reduced = useReducedMotion();
  const t = useAnimatedValue(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) {
      t.stopAnimation();
      t.setValue(1);
      return;
    }
    t.setValue(0);
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(t, { toValue: 1, duration, easing: Easing.linear, useNativeDriver: false }),
        Animated.delay(hold),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [t, reduced, duration, hold]);
  return t;
}

/** ``t``'nin [a, b] aralığını çıktıya eşler; aralık dışında uçlarda sabit kalır. */
export function k(t: T, input: number[], output: (number | string)[]) {
  return t.interpolate({ inputRange: input, outputRange: output as any, extrapolate: 'clamp' });
}

/** ``from`` anında belirir, ``to`` anında (verilmişse) kaybolur. */
export function shown(t: T, from: number, to?: number, fade = 0.025) {
  if (to === undefined) return k(t, [from - fade, from], [0, 1]);
  return k(t, [from - fade, from, to - fade, to], [0, 1, 1, 0]);
}

/** ``from`` anına kadar görünür, sonra kaybolur. */
export function hidden(t: T, from: number, fade = 0.025) {
  return k(t, [from - fade, from], [1, 0]);
}

/** Aynı yerde sırayla değişen metinler: her biri kendi anından bir sonrakinin anına kadar. */
export function Swap({
  t,
  steps,
  style,
  box,
}: {
  t: T;
  steps: [number, string][];
  style?: TextStyle | TextStyle[];
  box?: ViewStyle;
}) {
  // En uzun metin görünmez olarak yer tutar; kutu hiçbir adımda metni kırpmaz.
  const longest = steps.reduce((a, [, s]) => (s.length > a.length ? s : a), '');
  return (
    <View style={box}>
      <Text style={[style, { opacity: 0 }]} aria-hidden>
        {longest}
      </Text>
      {steps.map(([at, text], i) => {
        const next = steps[i + 1]?.[0];
        const opacity = i === 0 && next !== undefined ? hidden(t, next) : shown(t, at, next);
        return (
          <Animated.Text key={i} style={[style, StyleSheet.absoluteFill, { opacity }]}>
            {text}
          </Animated.Text>
        );
      })}
    </View>
  );
}

/** Şekil çerçevesi: numara, başlık, çizim alanı ve açıklama. Çizim ekran okuyucuya tek bir
 * görsel olarak ``label`` ile okunur; açıklama metni de görünür durur. */
export function Figure({
  no,
  title,
  label,
  caption,
  height,
  dark,
  children,
}: {
  no: number;
  title: string;
  label: string;
  caption?: ReactNode;
  /** Mutlak konumlu çizimlerde sabit yükseklik; verilmezse içerik kadar. */
  height?: number;
  dark?: boolean;
  children: ReactNode;
}) {
  return (
    <View style={[st.figure, dark && st.figureDark]}>
      <View style={st.head}>
        <Text style={[st.no, dark && { color: '#B88000' }]}>Şekil {no}</Text>
        <Text style={[st.title, dark && { color: '#FFB000', fontFamily: fonts.mono, fontSize: 13 }]}>{title}</Text>
      </View>
      <View accessible accessibilityRole="image" accessibilityLabel={label} style={{ height, overflow: 'hidden' }}>
        {children}
      </View>
      {caption ? <Text style={[st.caption, dark && { color: '#B88000' }]}>{caption}</Text> : null}
    </View>
  );
}

/** İki nokta arasında çizgi (merkezde döndürülür; transformOrigin'e gerek yok). */
export function Segment({
  x1,
  y1,
  x2,
  y2,
  color = paper.ink,
  width = 1,
  style,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
  width?: number;
  style?: any;
}) {
  const len = Math.hypot(x2 - x1, y2 - y1);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  return (
    <Animated.View
      style={[
        {
          position: 'absolute',
          left: (x1 + x2) / 2 - len / 2,
          top: (y1 + y2) / 2 - width / 2,
          width: len,
          height: width,
          backgroundColor: color,
          transform: [{ rotate: `${angle}rad` }],
        },
        style,
      ]}
    />
  );
}

/** Küçük mühür: şekillerde "KABUL", "KARAR" gibi sonuçlar. */
export function MiniStamp({ text, style }: { text: string; style?: any }) {
  return (
    <Animated.View style={[st.stamp, style]}>
      <Text style={st.stampText}>{text}</Text>
    </Animated.View>
  );
}

export const guide = StyleSheet.create({
  lane: { fontFamily: fonts.monoMedium, fontSize: 10, letterSpacing: 0.8, textTransform: 'uppercase', color: paper.inkSoft },
  mono: { fontFamily: fonts.mono, fontSize: 11, color: paper.ink },
  monoBold: { fontFamily: fonts.monoBold, fontSize: 11, color: paper.ink },
  serif: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 20, color: paper.ink },
  small: { fontFamily: fonts.serifItalic, fontSize: 13, lineHeight: 17, color: paper.inkSoft },
  card: {
    position: 'absolute',
    borderWidth: 1,
    borderColor: paper.ink,
    backgroundColor: paper.sheet,
    paddingHorizontal: 6,
    paddingVertical: 3,
    alignItems: 'center',
  },
  track: { position: 'absolute', left: 0, right: 0, height: 1, backgroundColor: paper.hairline },
});

const st = StyleSheet.create({
  figure: {
    borderWidth: 1,
    borderColor: paper.ink,
    backgroundColor: paper.sheet,
    padding: 12,
    gap: 10,
    marginVertical: 14,
  },
  figureDark: { backgroundColor: '#000', borderColor: '#000' },
  head: { flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' },
  no: { fontFamily: fonts.monoBold, fontSize: 11, letterSpacing: 1.4, textTransform: 'uppercase', color: paper.seal },
  title: { fontFamily: fonts.serifMedium, fontSize: 16, color: paper.ink, flexShrink: 1 },
  caption: { fontFamily: fonts.serifItalic, fontSize: 14, lineHeight: 20, color: paper.inkSoft },
  stamp: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: paper.seal,
    paddingHorizontal: 6,
    paddingVertical: 1,
    transform: [{ rotate: '-6deg' }],
    backgroundColor: 'rgba(248, 244, 235, 0.9)',
  },
  stampText: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.5, color: paper.seal },
});
