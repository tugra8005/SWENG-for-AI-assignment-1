import { router } from 'expo-router';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { Body, Button, H1, InfoNotice, Kicker, Muted, Rule, Seal } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDateTime } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

/** İfşa geçişinin ortasındaki durum: takma adların ne kadarı yazıldı, gölge kimlikleri ne kadar çizildi. */
export type RevealProgress = {
  typing: number;
  strike: Animated.AnimatedInterpolation<string | number>;
};

function Typed({ text, progress }: { text: string; progress: number }) {
  const n = Math.round(text.length * progress);
  return (
    <Text style={st.nick} accessibilityLabel={text}>
      {text.slice(0, n)}
      {n < text.length ? <Text style={{ color: paper.seal }}>▌</Text> : null}
    </Text>
  );
}

/**
 * İfşa edilmiş Mahzen başlığının Meydan'daki (kâğıt) hâli. ``progress`` verilirse ifşa geçişinin
 * kâğıt katmanı olarak çizilir; geçişin son karesi bu sayfanın kendisidir.
 */
export function RevealedThread({ t, progress }: { t: any; progress?: RevealProgress }) {
  const { me } = useAuth();
  const draftId = t.revealed?.draft_proposal_id;
  return (
    <View>
      <Kicker>Mahzen başlığı No.{t.id} · ifşa edildi {fmtDateTime(t.revealed?.at)}</Kicker>
      <H1>{t.title}</H1>
      <View style={{ marginTop: 6 }}>
        <Seal hash={t.revealed?.ledger_hash} label="ifşa kaydı" />
      </View>
      <Rule double />
      {t.posts.map((p: any) => (
        <View key={p.no} style={st.post}>
          <View style={st.head}>
            {/* Gölge kimliği üstü çizilir; çizgi geçişte soldan sağa ilerler. */}
            <View>
              <Text style={st.shade}>Gölge·{p.shade}</Text>
              <Animated.View style={[st.strike, { width: progress ? progress.strike : '100%' }]} />
            </View>
            {progress ? <Typed text={p.nickname ?? ''} progress={progress.typing} /> : <Text style={st.nick}>{p.nickname}</Text>}
            <Muted style={{ fontSize: 12 }}>{fmtDateTime(p.created_at)}</Muted>
          </View>
          <Body>{p.text}</Body>
        </View>
      ))}
      <InfoNotice>
        <Body>
          Başlık, katılımcılarının oylamasıyla öneriye dönüştürüldü. Yazan herkesin takma adı açığa çıktı ve
          başlık kimlikleriyle birlikte deftere yazıldı.
        </Body>
        {draftId ? (
          <View style={{ marginTop: 8 }}>
            <Button
              label={`Öneri taslağı №${draftId} →`}
              variant="secondary"
              small
              onPress={() => router.push(`/oneri/${draftId}`)}
            />
          </View>
        ) : null}
      </InfoNotice>
      {!me ? null : <Muted style={{ fontSize: 12 }}>Taslağı yalnızca oylamayı açan kişi tamamlayıp gönderebilir.</Muted>}
    </View>
  );
}

const st = StyleSheet.create({
  post: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  head: { flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' },
  shade: { fontFamily: fonts.mono, fontSize: 12, color: paper.muted },
  strike: { position: 'absolute', top: '50%', left: 0, height: 1.5, backgroundColor: paper.seal },
  nick: { fontFamily: fonts.serifBold, fontSize: 17, color: paper.seal },
});
