/**
 * Gazete: Meydan'ın ön sayfası. Haberler sunucuda kararlardan hesaplanır (``GET /news``): konu
 * kabulü, Karar, dilekçe ve yanıtı, yanıtsız kalan dilekçe, takvim, etkinlik raporu, yönetmelik
 * değişikliği, silme. Burada yalnızca dizilir: görselli manşet, ikinci haberler, yaklaşan etkinlikler.
 */

import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { EventRow, type EventSummary } from '@/components/event';
import { PrintImage, type MediaItem } from '@/components/media';
import { Kicker, Muted, PressLink, Section } from '@/components/paper';
import { useClock } from '@/lib/clock';
import { fmtAgo } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

export type NewsItem = {
  id: string;
  kind: string;
  at: string;
  kicker: string;
  headline: string;
  dek: string;
  link: string;
  image: MediaItem | null;
  area: string | null;
  lines: string[];
};

export type FrontPage = { lead: NewsItem | null; items: NewsItem[]; upcoming: EventSummary[] };

function Meta({ n }: { n: NewsItem }) {
  const { now } = useClock();
  return (
    <Text style={st.meta}>
      {n.kicker}
      {n.area ? ` · ${n.area}` : ''} · {fmtAgo(n.at, now())}
    </Text>
  );
}

/** Manşet: büyük başlık, spot ve görsel; geniş ekranda görsel solda. */
export function LeadStory({ n, wide }: { n: NewsItem; wide?: boolean }) {
  return (
    <View style={[st.lead, wide && { flexDirection: 'row', gap: 24, alignItems: 'flex-start' }]}>
      {n.image ? (
        <View style={wide ? { flex: 1.15 } : { marginBottom: 12 }}>
          <PrintImage m={n.image} maxHeight={wide ? 420 : 300} />
        </View>
      ) : null}
      <View style={{ flex: 1, gap: 8 }}>
        <Meta n={n} />
        <Link href={n.link as any} accessibilityRole="link">
          <Text style={[st.leadHead, !wide && { fontSize: 30, lineHeight: 36 }]}>{n.headline}</Text>
        </Link>
        <Text style={st.leadDek}>{n.dek}</Text>
        {n.lines.slice(0, 1).map((line, i) => (
          <Text key={i} style={st.quote}>
            {line}
          </Text>
        ))}
        <Link href={n.link as any} style={st.more}>
          Devamı →
        </Link>
      </View>
    </View>
  );
}

/** İkinci haber: başlık, spot, küçük görsel. */
export function NewsCard({ n }: { n: NewsItem }) {
  return (
    <PressLink href={n.link} style={st.card}>
      <Meta n={n} />
      {n.image ? (
        <View style={{ marginVertical: 6 }}>
          <PrintImage m={n.image} maxHeight={170} caption={false} />
        </View>
      ) : null}
      <Text style={st.cardHead}>{n.headline}</Text>
      <Text style={st.cardDek} numberOfLines={4}>
        {n.dek}
      </Text>
    </PressLink>
  );
}

export function UpcomingEvents({ items }: { items: EventSummary[] }) {
  return (
    <Section title="Yaklaşan" aside={<Link href="/takvim" style={st.asideLink}>Takvim →</Link>}>
      {items.length ? (
        items.map((e) => <EventRow key={e.id} e={e} />)
      ) : (
        <Muted style={{ marginTop: 8 }}>Takvimde yaklaşan etkinlik yok.</Muted>
      )}
    </Section>
  );
}

export function NewsKicker() {
  return <Kicker style={{ color: paper.seal }}>Kararlar dünyaya dokunur · ön sayfa</Kicker>;
}

const st = StyleSheet.create({
  lead: { paddingVertical: 16, borderBottomWidth: 2, borderBottomColor: paper.ink, marginBottom: 6 },
  leadHead: { fontFamily: fonts.serifDisplay, fontSize: 40, lineHeight: 46, color: paper.ink },
  leadDek: { fontFamily: fonts.serif, fontSize: 19, lineHeight: 28, color: paper.inkSoft },
  quote: {
    fontFamily: fonts.serifItalic,
    fontSize: 17,
    lineHeight: 25,
    color: paper.ink,
    paddingLeft: 12,
    borderLeftWidth: 2,
    borderLeftColor: paper.seal,
  },
  more: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1, color: paper.seal, textDecorationLine: 'underline' },
  meta: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1, color: paper.muted, textTransform: 'uppercase' },
  card: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  cardHead: { fontFamily: fonts.serifBold, fontSize: 19, lineHeight: 25, color: paper.ink },
  cardDek: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 22, color: paper.inkSoft },
  asideLink: { fontFamily: fonts.monoBold, fontSize: 12, color: paper.seal, textDecorationLine: 'underline' },
});
