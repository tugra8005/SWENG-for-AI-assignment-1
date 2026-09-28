import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Button, H1, Kicker, LockIcon, Loading, Muted, Page, Rule, Section } from '@/components/paper';
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

/** Yönetmeliğin tabanı: anayasa sayfası gibi, çift çerçeveli belge. */
function Constitution({ items, ranged }: { items: any[]; ranged: any[] }) {
  const principles = items.filter((a) => a.kind === 'temel_ilke');
  return (
    <View style={st.charter} accessibilityRole="summary">
      <View style={st.charterInner}>
        <View style={st.charterHead}>
          <LockIcon size={18} />
          <Text style={st.charterKicker}>Yönetmeliğin tabanı</Text>
          <Text accessibilityRole="header" style={st.charterTitle}>
            Değiştirilemez Maddeler
          </Text>
          <Text style={st.charterPreamble}>
            Aşağıdaki maddeler oylamayla değiştirilemez, kaldırılamaz; değiştirilmeleri önerilemez. Forumda
            her şey oylamayla yürür; bu liste o kuralın bilinçli istisnasıdır. Tamamen oylanabilir bir düzende
            azınlığın güvencesi yalnızca daha yüksek bir çıtadır; burada bir tabandır.
          </Text>
        </View>
        <Rule double />
        {principles.map((a) => (
          <View key={a.key} style={st.charterArticle}>
            <View style={st.charterNum}>
              <Text style={st.charterNumText}>Madde {a.key}</Text>
              <LockIcon size={12} />
            </View>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={st.charterArticleTitle}>{a.value.baslik}</Text>
              <Text style={st.charterArticleText}>{a.value.metin}</Text>
            </View>
          </View>
        ))}
        <Rule />
        <Text style={st.charterSub}>İzinli aralıklar</Text>
        <Text style={st.charterArticleText}>
          Her sayısal parametrenin değiştirilemez bir izinli aralığı vardır ({ranged.length} parametre). Değer
          aralığın içinde oylamayla değişir; aralık D7 kapsamında değişmez. Aralıklar aşağıda her parametrenin
          yanında kilitle gösterilir. Aralıklar tasarımcının seçimidir ve keyfîdir; gerekçeleri tasarım
          belgesindedir.
        </Text>
        <Text style={st.charterFoot}>
          Bir maddeye dokunan ya da bir parametreyi izinli aralığının dışına çıkaran öneri açılışta reddedilir
          (R8). Yönetmeliğin tam hâli her Karar Saati sonunda hash&apos;iyle deftere yazılır.
        </Text>
      </View>
    </View>
  );
}

export default function Regulation() {
  const list = useApi<any[]>('/regulation');
  const constitution = (list.data ?? []).filter((a) => a.unchangeable);
  const params = (list.data ?? []).filter((a) => a.kind !== 'icerik_kurali' && !a.unchangeable);
  const rules = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && !a.removed);
  const removed = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && a.removed);
  return (
    <Page>
      <Kicker>Yönetmelik = veri</Kicker>
      <H1>Yönetmelik</H1>
      <Muted>
        Tüm eşikler ve süreler bu maddelerde durur; kod hiçbir eşiği sabit yazmaz. Değiştirilemez maddeler
        dışında her madde Genel kapsamda, Karar Saati&apos;nde yonetmelik_esigi ile değişir — bu maddenin
        kendisi de. Her sayısal parametre değiştirilemez izinli aralığının içinde kalır.
      </Muted>
      <Rule double />
      {!list.data ? <Loading /> : null}
      {list.data ? <Constitution items={constitution} ranged={(list.data ?? []).filter((a) => a.range)} /> : null}
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
              {a.range ? (
                <View style={st.floor} aria-label={`izinli aralık ${a.range}, değiştirilemez`}>
                  <LockIcon size={11} />
                  <Text style={st.floorText}>izinli: {a.range}</Text>
                </View>
              ) : null}
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
  floor: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  floorText: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal },
  charter: { borderWidth: 3, borderColor: paper.ink, padding: 4, marginVertical: 18, backgroundColor: paper.sheet },
  charterInner: { borderWidth: 1, borderColor: paper.ink, paddingHorizontal: 18, paddingVertical: 16, gap: 10 },
  charterHead: { alignItems: 'center', gap: 6 },
  charterKicker: {
    fontFamily: fonts.monoMedium,
    fontSize: 11,
    letterSpacing: 2,
    color: paper.seal,
    textTransform: 'uppercase',
  },
  charterTitle: { fontFamily: fonts.serifDisplay, fontSize: 30, lineHeight: 36, color: paper.ink, textAlign: 'center' },
  charterPreamble: {
    fontFamily: fonts.serifItalic,
    fontSize: 16,
    lineHeight: 24,
    color: paper.inkSoft,
    textAlign: 'center',
    maxWidth: 560,
  },
  charterArticle: { flexDirection: 'row', gap: 14, paddingVertical: 8, flexWrap: 'wrap' },
  charterNum: { width: 92, flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6, paddingTop: 6 },
  charterNumText: {
    fontFamily: fonts.monoBold,
    fontSize: 12,
    letterSpacing: 1,
    color: paper.seal,
    textTransform: 'uppercase',
  },
  charterArticleTitle: { fontFamily: fonts.serifBold, fontSize: 19, lineHeight: 25, color: paper.ink },
  charterArticleText: { fontFamily: fonts.serif, fontSize: 16, lineHeight: 23, color: paper.inkSoft },
  charterSub: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 1.5, color: paper.ink, textTransform: 'uppercase' },
  charterFoot: { fontFamily: fonts.serifItalic, fontSize: 14, color: paper.muted, textAlign: 'center', marginTop: 6 },
  keywords: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 18, color: paper.muted },
});
