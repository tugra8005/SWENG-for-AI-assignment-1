import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Body, Button, H1, InfoNotice, Kicker, Muted, Rule, Seal } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDateTime } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

/** İfşa edilmiş Mahzen başlığının Meydan'daki (kâğıt) hâli. */
export function RevealedThread({ t }: { t: any }) {
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
            <Text style={st.shade}>Gölge·{p.shade}</Text>
            <Text style={st.nick}>{p.nickname}</Text>
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
  shade: { fontFamily: fonts.mono, fontSize: 12, color: paper.muted, textDecorationLine: 'line-through' },
  nick: { fontFamily: fonts.serifBold, fontSize: 17, color: paper.seal },
});
