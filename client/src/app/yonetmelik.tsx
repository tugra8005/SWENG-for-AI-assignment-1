import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Button, H1, Kicker, Loading, Muted, Page, Rule } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { describeArticleValue, fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function Regulation() {
  const { me } = useAuth();
  const list = useApi<any[]>('/regulation');
  return (
    <Page>
      <Kicker>Yönetmelik = veri</Kicker>
      <H1>Yönetmelik</H1>
      <Muted>
        Tüm eşikler ve süreler bu maddelerde durur; kod hiçbir eşiği sabit yazmaz. Her madde Genel
        kapsamda, Karar Saati&apos;nde yonetmelik_esigi ile değişir — bu maddenin kendisi de.
      </Muted>
      <Rule double />
      {!list.data ? <Loading /> : null}
      {list.data?.map((a, i) => (
        <View key={a.key} style={st.article}>
          <View style={{ flexDirection: 'row', gap: 10, alignItems: 'baseline' }}>
            <Text style={st.num}>Madde {i + 1}</Text>
            <Text style={st.key}>{a.key}</Text>
          </View>
          <Text style={st.value}>{describeArticleValue(a.kind, a.value)}</Text>
          <Muted>{a.description}</Muted>
          {a.history.map((h: any, j: number) => (
            <Text key={j} style={st.history}>
              {fmtDate(h.changed_at)} · №{h.proposal_id} ile {describeArticleValue(a.kind, h.old_value)} →{' '}
              {describeArticleValue(a.kind, h.new_value)}
            </Text>
          ))}
          {me ? (
            <Button
              label="Değişiklik öner"
              variant="quiet"
              onPress={() => router.push({ pathname: '/oneri/yeni', params: { type: 'YONETMELIK', article: a.key } })}
            />
          ) : null}
        </View>
      ))}
    </Page>
  );
}

const st = StyleSheet.create({
  article: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  num: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 1.2, color: paper.seal, textTransform: 'uppercase' },
  key: { fontFamily: fonts.monoBold, fontSize: 15, color: paper.ink },
  value: { fontFamily: fonts.serifBold, fontSize: 20, color: paper.ink },
  history: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal },
});
