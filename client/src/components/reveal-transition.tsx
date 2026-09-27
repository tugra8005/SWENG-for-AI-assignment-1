/**
 * İfşa geçişi (~1,5 sn): siyah zemin kâğıda, amber yazı mürekkebe döner; mono yazı serife
 * geçer; Gölge kimliklerinin üzerine takma adlar yazılır. Azaltılmış harekette son durum
 * anında gösterilir.
 */
import { useEffect, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';

import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { cellar, fonts, paper } from '@/theme/tokens';

const DURATION = 1500;

type Post = { no: number; shade: string; nickname: string | null; text: string };

function Typed({ text, progress }: { text: string; progress: number }) {
  const n = Math.round(text.length * progress);
  return (
    <Text style={st.nick} accessibilityLabel={text}>
      {text.slice(0, n)}
      {n < text.length ? <Text style={{ color: paper.seal }}>▌</Text> : null}
    </Text>
  );
}

export function RevealTransition({
  title,
  posts,
  onDone,
}: {
  title: string;
  posts: Post[];
  onDone: () => void;
}) {
  const reduced = useReducedMotion();
  const t = useAnimatedValue(reduced ? 1 : 0);
  const [typing, setTyping] = useState(reduced ? 1 : 0);

  useEffect(() => {
    if (reduced) {
      onDone();
      return;
    }
    const id = t.addListener(({ value }) => setTyping(Math.max(0, Math.min(1, (value - 0.45) / 0.5))));
    Animated.timing(t, {
      toValue: 1,
      duration: DURATION,
      easing: Easing.inOut(Easing.cubic),
      useNativeDriver: false,
    }).start(() => onDone());
    return () => t.removeListener(id);
  }, [onDone, reduced, t]);

  const bg = t.interpolate({ inputRange: [0, 1], outputRange: [cellar.bg, paper.bg] });
  const ink = t.interpolate({ inputRange: [0, 1], outputRange: [cellar.amber, paper.ink] });
  const monoOpacity = t.interpolate({ inputRange: [0, 0.55], outputRange: [1, 0], extrapolate: 'clamp' });
  const serifOpacity = t.interpolate({ inputRange: [0.4, 1], outputRange: [0, 1], extrapolate: 'clamp' });
  const strike = t.interpolate({ inputRange: [0.35, 0.6], outputRange: ['0%', '100%'], extrapolate: 'clamp' });

  return (
    <Animated.View style={[st.stage, { backgroundColor: bg }]} accessibilityLiveRegion="polite">
      <Animated.Text style={[st.kicker, { color: ink }]}>İFŞA · BAŞLIK ÖNERİYE DÖNÜŞTÜ</Animated.Text>
      <View>
        <Animated.Text style={[st.titleMono, { color: ink, opacity: monoOpacity }]}>{title}</Animated.Text>
        <Animated.Text style={[st.titleSerif, { opacity: serifOpacity }]}>{title}</Animated.Text>
      </View>
      {posts.map((p) => (
        <View key={p.no} style={st.post}>
          <View style={st.head}>
            <View>
              <Animated.Text style={[st.shade, { color: ink }]}>Gölge·{p.shade}</Animated.Text>
              <Animated.View style={[st.strikeLine, { width: strike }]} />
            </View>
            {p.nickname ? <Typed text={p.nickname} progress={typing} /> : null}
          </View>
          <View>
            <Animated.Text style={[st.bodyMono, { color: ink, opacity: monoOpacity }]}>{p.text}</Animated.Text>
            <Animated.Text style={[st.bodySerif, { opacity: serifOpacity }]}>{p.text}</Animated.Text>
          </View>
        </View>
      ))}
    </Animated.View>
  );
}

const st = StyleSheet.create({
  stage: { flex: 1, padding: 18, gap: 14 },
  kicker: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 2 },
  titleMono: { fontFamily: fonts.terminal, fontSize: 34, lineHeight: 38 },
  titleSerif: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    fontFamily: fonts.serifBold,
    fontSize: 30,
    lineHeight: 38,
    color: paper.ink,
  },
  post: { gap: 4 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  shade: { fontFamily: fonts.mono, fontSize: 13 },
  strikeLine: { position: 'absolute', top: '52%', left: 0, height: 2, backgroundColor: paper.seal },
  nick: { fontFamily: fonts.serifBold, fontSize: 17, color: paper.seal },
  bodyMono: { fontFamily: fonts.mono, fontSize: 14, lineHeight: 21 },
  bodySerif: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    fontFamily: fonts.serif,
    fontSize: 17,
    lineHeight: 21,
    color: paper.ink,
  },
});
