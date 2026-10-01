import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Anchor,
  Button,
  Columns,
  Grid,
  Kicker,
  LockIcon,
  Loading,
  Muted,
  Page,
  PageHead,
  Rule,
  Section,
  useScrollTo,
  useWide,
} from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { describeArticleValue, fmtDate, fmtNumber } from '@/lib/format';
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

const GROUPS = ['Oylama eşikleri', 'Süreler', 'Havale', 'Mahzen', 'Baskın tespiti'] as const;
const anchorId = (name: string) => `yonetmelik-${name.toLocaleLowerCase('tr-TR').replace(/\s+/g, '-')}`;

/** Sayfa başındaki küçük içindekiler. */
function Contents({ vertical }: { vertical?: boolean }) {
  const scrollTo = useScrollTo();
  const entries = ['Değiştirilemez Maddeler', 'İçerik kuralları', ...GROUPS];
  return (
    <View style={[st.toc, vertical && { marginTop: 22 }]} role="navigation" aria-label="İçindekiler">
      <Kicker>İçindekiler</Kicker>
      <View style={vertical ? { gap: 8, marginTop: 4 } : st.tocList}>
        {entries.map((e, i) => (
          <Pressable key={e} onPress={() => scrollTo(anchorId(e))} accessibilityRole="link" hitSlop={4}>
            {({ hovered }: any) => (
              <Text style={[st.tocItem, hovered && { textDecorationLine: 'underline' }]}>
                {i + 1}. {e}
              </Text>
            )}
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const WEIGHT_ROWS: { key: string; label: string; window?: string }[] = [
  { key: 'yanit', label: 'Yanıt (bir yurttaşın diğerine yanıtı)' },
  { key: 'havale', label: 'Havale' },
  { key: 'yakin_kayit', label: 'Yakın zamanda kayıt', window: 'yakin_kayit_dk' },
  { key: 'ortak_baslik', label: 'Aynı Mahzen başlığında yakın zamanda yazma', window: 'ortak_baslik_dk' },
];

/** etkilesim_agirliklari: ham anahtar-değer yerine küçük tablo. */
function WeightsTable({ value }: { value: Record<string, number> }) {
  return (
    <View style={st.table} aria-label="Etkileşim ağırlıkları">
      <View style={[st.tr, st.thead]}>
        <Text style={[st.th, { flex: 1 }]}>Sinyal</Text>
        <Text style={[st.th, st.num]}>Ağırlık</Text>
        <Text style={[st.th, st.num]}>Pencere</Text>
      </View>
      {WEIGHT_ROWS.map((r) => (
        <View key={r.key} style={st.tr}>
          <Text style={[st.td, { flex: 1 }]}>{r.label}</Text>
          <Text style={[st.tdNum, st.num]}>{fmtNumber(value[r.key])}</Text>
          <Text style={[st.tdNum, st.num]}>{r.window ? `${value[r.window]} dk` : '—'}</Text>
        </View>
      ))}
    </View>
  );
}

function Parameter({ a }: { a: any }) {
  return (
    <View style={st.article}>
      <View style={st.titleRow}>
        <Text style={st.paramTitle}>{a.title ?? a.key}</Text>
        <Text style={st.paramKey}>{a.key}</Text>
      </View>
      {a.kind === 'agirliklar' ? (
        <WeightsTable value={a.value} />
      ) : (
        <Text style={st.value}>{describeArticleValue(a.kind, a.value)}</Text>
      )}
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
  );
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
  const wide = useWide();
  const constitution = (list.data ?? []).filter((a) => a.unchangeable);
  const params = (list.data ?? []).filter((a) => a.kind !== 'icerik_kurali' && !a.unchangeable);
  const rules = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && !a.removed);
  const removed = (list.data ?? []).filter((a) => a.kind === 'icerik_kurali' && a.removed);
  const body = (
    <>
      {list.data ? (
        <Anchor id={anchorId('Değiştirilemez Maddeler')}>
          <Constitution items={constitution} ranged={(list.data ?? []).filter((a) => a.range)} />
        </Anchor>
      ) : null}
      {list.data ? (
        <Anchor id={anchorId('İçerik kuralları')}>
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
        </Anchor>
      ) : null}
      {list.data
        ? GROUPS.map((g) => (
            <Anchor key={g} id={anchorId(g)}>
              <Section title={g}>
                <Grid min={400} rowGap={0}>
                  {params.filter((a) => (a.group ?? 'Süreler') === g).map((a) => (
                    <Parameter key={a.key} a={a} />
                  ))}
                </Grid>
              </Section>
            </Anchor>
          ))
        : null}
    </>
  );

  return (
    <Page>
      <PageHead kicker="Yönetmelik = veri" title="Yönetmelik">
        <Muted>
          Tüm eşikler ve süreler bu maddelerde durur; kod hiçbir eşiği sabit yazmaz. Değiştirilemez maddeler
          dışında her madde Genel kapsamda, Karar Saati&apos;nde yonetmelik_esigi ile değişir — bu maddenin
          kendisi de. Her sayısal parametre değiştirilemez izinli aralığının içinde kalır.
        </Muted>
      </PageHead>
      {!list.data ? <Loading /> : null}
      {/* Geniş ekranda içindekiler solda yapışık sütunda; parametreler iki sütunlu ızgarada. */}
      {list.data && wide ? (
        <Columns sideLeft stickySide sideWidth={240} side={<Contents vertical />} main={body} />
      ) : (
        <>
          {list.data ? <Contents /> : null}
          {body}
        </>
      )}
    </Page>
  );
}

const st = StyleSheet.create({
  article: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  titleRow: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 10, rowGap: 2, alignItems: 'baseline' },
  paramTitle: { fontFamily: fonts.serifBold, fontSize: 19, lineHeight: 25, color: paper.ink },
  paramKey: { fontFamily: fonts.mono, fontSize: 12, color: paper.muted },
  toc: { marginTop: 14, gap: 6 },
  tocList: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 16, rowGap: 4 },
  tocItem: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.seal, letterSpacing: 0.3 },
  table: { borderTopWidth: 1, borderColor: paper.ink, marginVertical: 4, maxWidth: 560 },
  thead: { borderBottomColor: paper.ink },
  tr: { flexDirection: 'row', gap: 10, paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  th: { fontFamily: fonts.monoMedium, fontSize: 10, letterSpacing: 1.2, textTransform: 'uppercase', color: paper.inkSoft },
  td: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 20, color: paper.ink },
  tdNum: { fontFamily: fonts.mono, fontSize: 13, color: paper.ink },
  num: { width: 64, textAlign: 'right' },
  key: { fontFamily: fonts.monoBold, fontSize: 15, color: paper.ink },
  value: { fontFamily: fonts.serifMedium, fontSize: 18, color: paper.ink },
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
