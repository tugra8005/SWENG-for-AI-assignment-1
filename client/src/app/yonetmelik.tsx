import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Button, H1, Kicker, Loading, Muted, Page, Rule, Section } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { describeArticleValue, fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

function ProposeChange({ articleKey, action = 'degistir', label = 'Değişiklik öner' }: {
  articleKey?: string;
  action?: 'degistir' | 'ekle' | 'kaldir';
  label?: string;
}) {
  const { me } = useAuth();
  if (!me) return null;
  const params: Record<string, string> = { type: 'YONETMELIK', action };
  if (articleKey) params.article = articleKey;
  return (
    <Button label={label} variant="quiet" onPress={() => router.push({ pathname: '/oneri/yeni', params })} />
  );
}

function History({ a }: { a: any }) {
  return a.history.map((h: any, j: number) => (
    <Text key={j} style={st.history}>
      {fmtDate(h.changed_at)} · №{h.proposal_id} ile {describeArticleValue(a.kind, h.old_value)} →{' '}
      {describeArticleValue(a.kind, h.new_value)}
    </Text>
  ));
}

export default function Regulation() {
  const list = useApi<any[]>('/regulation');
  const params = (list.data ?? []).filter((a) => a.kind !== 'icerik_kurali');
  const rules = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && !a.removed);
  const removed = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && a.removed);
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
      {list.data ? (
        <Section title="İçerik kuralları" aside={<Kicker>silmenin tek dayanağı</Kicker>}>
          <Muted>
            Başkasının içeriğini silme önerisi bu kurallardan en az birine dayanmak ve ihlal eden kısmı
            metinden alıntılamak zorundadır; kullanılan oylar içinde en az 2/3 EVET ile geçer (silme_esigi). Kurallar bilerek dar
            tutulur: &quot;konu dışı&quot; gibi geniş bir kural sansür aracına dönüşür. Kural eklemek, kaldırmak ya
            da değiştirmek bir yönetmelik önerisidir (yonetmelik_esigi).
          </Muted>
          <ProposeChange action="ekle" label="Yeni içerik kuralı öner" />
          {rules.map((a) => (
            <View key={a.key} style={st.article}>
              <View style={{ flexDirection: 'row', gap: 10, alignItems: 'baseline' }}>
                <Text style={st.key}>{a.key}</Text>
                <Text style={st.value}>{a.value.baslik}</Text>
              </View>
              <Text style={st.ruleText}>{a.value.metin}</Text>
              <Text style={st.keywords}>Hâtif&apos;in anahtar kelimeleri: {a.value.anahtar_kelimeler.join(', ')}</Text>
              <History a={a} />
              <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap' }}>
                <ProposeChange articleKey={a.key} />
                <ProposeChange articleKey={a.key} action="kaldir" label="Kaldırılmasını öner" />
              </View>
            </View>
          ))}
          {removed.length ? <Kicker style={{ marginTop: 12 }}>Kaldırılan kurallar</Kicker> : null}
          {removed.map((a) => {
            const last = a.history.at(-1);
            return (
              <Text key={a.key} style={st.history}>
                {a.key} {last?.old_value?.baslik} · {fmtDate(last?.changed_at)} tarihinde №{last?.proposal_id} ile
                kaldırıldı; kod bir daha kullanılmaz.
              </Text>
            );
          })}
        </Section>
      ) : null}
      {list.data ? (
        <Section title="Parametreler">
          {params.map((a, i) => (
            <View key={a.key} style={st.article}>
              <View style={{ flexDirection: 'row', gap: 10, alignItems: 'baseline' }}>
                <Text style={st.num}>Madde {i + 1}</Text>
                <Text style={st.key}>{a.key}</Text>
              </View>
              <Text style={st.value}>{describeArticleValue(a.kind, a.value)}</Text>
              <Muted>{a.description}</Muted>
              <History a={a} />
              <ProposeChange articleKey={a.key} />
            </View>
          ))}
        </Section>
      ) : null}
    </Page>
  );
}

const st = StyleSheet.create({
  article: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  num: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 1.2, color: paper.seal, textTransform: 'uppercase' },
  key: { fontFamily: fonts.monoBold, fontSize: 15, color: paper.ink },
  value: { fontFamily: fonts.serifBold, fontSize: 20, color: paper.ink },
  history: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal },
  ruleText: { fontFamily: fonts.serif, fontSize: 17, lineHeight: 25, color: paper.ink },
  keywords: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 18, color: paper.muted },
});
