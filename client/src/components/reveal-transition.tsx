/**
 * İfşa geçişi (~1,5 sn): siyah zemin kâğıda, amber yazı mürekkebe döner; mono yazı serife
 * geçer; Gölge kimliklerinin üzerine takma adlar yazılır. Sahne sayfa sütununun içindedir ve
 * tipografisi ifşa edilmiş sayfayla aynıdır; künye (başlık, alt bilgi) t > 0,7'de belirir, son kare
 * son sayfanın kendisidir. Azaltılmış harekette son durum anında gösterilir.
 */
import { useEffect, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';

import { Page } from '@/components/paper';
import { RevealedThread } from '@/components/revealed-thread';
import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { cellar, fonts, paper } from '@/theme/tokens';

const DURATION = 1500;

type Post = { no: number; shade: string; text: string };

/** Başlangıçtaki Mahzen görünümü: amber mono yazı. Kâğıt katmanın üstünde durur ve söner. */
function CellarLayer({ title, posts }: { title: string; posts: Post[] }) {
  return (
    <View style={[StyleSheet.absoluteFill, { pointerEvents: 'none' }]}>
      <Text style={st.kicker}>İFŞA · BAŞLIK ÖNERİYE DÖNÜŞTÜ</Text>
      <Text style={st.title}>{title}</Text>
      {posts.map((p) => (
        <View key={p.no} style={st.post}>
          <Text style={st.shade}>Gölge·{p.shade}</Text>
          <Text style={st.body}>{p.text}</Text>
        </View>
      ))}
    </View>
  );
}

export function RevealTransition({ t: thread, onDone }: { t: any; onDone: () => void }) {
  const reduced = useReducedMotion();
  const t = useAnimatedValue(reduced ? 1 : 0);
  const [progress, setTyping] = useState(0);
  const typing = reduced ? 1 : progress;

  useEffect(() => {
    if (reduced) {
      // Değer sonradan true'ya döndüyse başlamış animasyon durdurulur, son hâl gösterilir.
      t.stopAnimation();
      t.setValue(1);
      onDone();
      return;
    }
    const id = t.addListener(({ value }) => setTyping(Math.max(0, Math.min(1, (value - 0.45) / 0.5))));
    Animated.timing(t, {
      toValue: 1,
      duration: DURATION,
      easing: Easing.inOut(Easing.cubic),
      useNativeDriver: false,
    }).start(({ finished }) => finished && onDone());
    return () => t.removeListener(id);
  }, [onDone, reduced, t]);

  const reveal = {
    background: t.interpolate({ inputRange: [0, 1], outputRange: [cellar.bg, paper.bg] }),
    paper: t.interpolate({ inputRange: [0.5, 1], outputRange: [0, 1], extrapolate: 'clamp' }),
    chrome: t.interpolate({ inputRange: [0.7, 1], outputRange: [0, 1], extrapolate: 'clamp' }),
  };
  const cellarOpacity = t.interpolate({ inputRange: [0, 0.55], outputRange: [1, 0], extrapolate: 'clamp' });
  const paperOpacity = t.interpolate({ inputRange: [0.4, 1], outputRange: [0, 1], extrapolate: 'clamp' });
  const strike = t.interpolate({ inputRange: [0.35, 0.6], outputRange: ['0%', '100%'], extrapolate: 'clamp' });

  return (
    <Page reveal={reveal} reading>
      <View accessibilityLiveRegion="polite">
        <Animated.View style={{ opacity: paperOpacity }}>
          <RevealedThread t={thread} progress={{ typing, strike }} />
        </Animated.View>
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: cellarOpacity, pointerEvents: 'none' }]}>
          <CellarLayer title={thread.title} posts={thread.posts} />
        </Animated.View>
      </View>
    </Page>
  );
}

const st = StyleSheet.create({
  kicker: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 2, color: cellar.amber },
  title: { fontFamily: fonts.terminal, fontSize: 34, lineHeight: 38, color: cellar.amber, marginTop: 4 },
  post: { paddingVertical: 12, gap: 4 },
  shade: { fontFamily: fonts.mono, fontSize: 13, color: cellar.amber },
  body: { fontFamily: fonts.mono, fontSize: 14, lineHeight: 21, color: cellar.amber },
});
