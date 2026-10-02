import { Link } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Body, Grid, H1, InfoNotice, Kicker, Loading, Muted, Page, PageHead } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDateTime } from '@/lib/format';
import { useNotifications } from '@/lib/notifications';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Item = {
  id: number;
  kind: 'KARAR_SAATI' | 'SESSIZ_ONAY' | 'YAVAS_SERIT' | 'DILEKCE';
  title: string;
  lines: string[];
  link: string | null;
  created_at: string;
  read: boolean;
};

const LINK_LABEL: Record<Item['kind'], string> = {
  KARAR_SAATI: 'Oturumun sonuçları →',
  SESSIZ_ONAY: 'Öneriyi aç →',
  YAVAS_SERIT: 'Öneriyi aç →',
  DILEKCE: 'Dilekçeyi aç →',
};

export default function Notifications() {
  const { me } = useAuth();
  const list = useApi<{ unread: number; items: Item[] }>(me ? '/notifications' : null);
  const { markAllRead } = useNotifications();
  const unread = list.data?.unread ?? 0;

  // Sayfa açılınca hepsi okundu sayılır; "yeni" işareti bu görünümde kalır (liste yeniden okunmaz).
  useEffect(() => {
    if (unread > 0) markAllRead().catch(() => undefined);
  }, [unread, markAllRead]);

  if (!me) {
    return (
      <Page>
        <H1>Bildirimler</H1>
        <InfoNotice>Bildirimleri görmek için giriş yapın.</InfoNotice>
      </Page>
    );
  }

  const items = list.data?.items ?? [];
  return (
    <Page>
      <PageHead kicker="Size gelen sonuçlar" title="Bildirimler">
        <Muted>
          Oy verdiğiniz ya da oyunuzun havaleyle kullanıldığı önerilerin sonuçları her Karar Saati
          kapanınca burada görünür; açtığınız önerilerin sessiz onay ve itiraz sonuçları da. Bildirimler
          yalnızca size görünür ve deftere yazılmaz.
        </Muted>
      </PageHead>
      {list.loading && !list.data ? <Loading /> : null}
      {list.data && items.length === 0 ? (
        <Body style={{ color: paper.inkSoft }}>
          Henüz bildiriminiz yok. İlk sonuçlar oy verdiğiniz ilk Karar Saati kapanınca gelir.
        </Body>
      ) : null}
      <Grid min={480} rowGap={0}>
        {items.map((n) => (
          <View key={n.id} style={[st.item, !n.read && st.unread]}>
            <View style={st.head}>
              {!n.read ? <Kicker style={{ color: paper.seal }}>yeni</Kicker> : null}
              <Kicker>{fmtDateTime(n.created_at)}</Kicker>
            </View>
            <Text style={st.title}>{n.title}</Text>
            {n.lines.map((line, i) => (
              <View key={i} style={st.line}>
                <Text style={st.bullet}>·</Text>
                <Body style={st.lineText}>{line}</Body>
              </View>
            ))}
            {n.link ? (
              <Link href={n.link as any} style={st.link}>
                {LINK_LABEL[n.kind] ?? 'Aç →'}
              </Link>
            ) : null}
          </View>
        ))}
      </Grid>
    </Page>
  );
}

const st = StyleSheet.create({
  item: {
    paddingVertical: 14,
    paddingLeft: 12,
    borderLeftWidth: 3,
    borderLeftColor: 'transparent',
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
    gap: 6,
  },
  unread: { borderLeftColor: paper.seal, backgroundColor: paper.sealWash },
  head: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  title: { fontFamily: fonts.serifMedium, fontSize: 19, lineHeight: 25, color: paper.ink },
  line: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  bullet: { fontFamily: fonts.monoBold, fontSize: 15, lineHeight: 23, color: paper.seal },
  lineText: { flex: 1, fontSize: 16, lineHeight: 23 },
  link: {
    alignSelf: 'flex-start',
    marginTop: 4,
    fontFamily: fonts.monoMedium,
    fontSize: 12,
    letterSpacing: 0.6,
    color: paper.seal,
    textDecorationLine: 'underline',
  },
});
