import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { api } from '@/api/client';
import {
  Button,
  CensorStrip,
  ErrorNotice,
  H1,
  Kicker,
  Loading,
  Muted,
  Page,
  PressLink,
  Rule,
  Section,
} from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function AreaPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const areas = useApi<any[]>('/areas');
  const topics = useApi<any[]>(`/topics?area_id=${id}`);
  const [error, setError] = useState<unknown>(null);
  const area = areas.data?.find((a) => a.id === id);
  if (!area) return <Page>{areas.error ? <ErrorNotice error={areas.error} /> : <Loading />}</Page>;
  const parent = areas.data?.find((a) => a.id === area.parent_id);
  const children = areas.data?.filter((a) => a.parent_id === id) ?? [];
  const m = area.membership;

  const toggle = async () => {
    setError(null);
    try {
      await api(`/me/interests/${id}`, { method: m ? 'DELETE' : 'POST' });
      areas.reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <Kicker>
        Alan {parent ? `· ${parent.name} altında` : '· kök alan'}
      </Kicker>
      <H1>{area.name}</H1>
      <Muted>anahtar kelimeler: {area.keywords.join(', ')}</Muted>
      {me ? (
        <Text style={st.member}>
          {m
            ? m.has_vote_right
              ? `İlgi kapsamının üyesisiniz; oy hakkınız var (${fmtDate(m.since)} tarihinden beri).`
              : `İlgi kapsamına katıldınız; oy hakkınız ${fmtDate(m.vote_right_from)} tarihinde doğacak.`
            : 'Bu alanın ilgi kapsamına üye değilsiniz.'}
        </Text>
      ) : null}
      {me ? <Button label={m ? 'İlgi kapsamından ayrıl' : 'İlgi kapsamına katıl'} variant="secondary" small onPress={toggle} /> : null}
      <ErrorNotice error={error} />
      <Rule double />
      {children.length ? (
        <Section title="Alt alanlar">
          {children.map((c) => (
            <PressLink key={c.id} href={`/alan/${c.id}`} style={st.row}>
              <Text style={st.name}>└ {c.name}</Text>
            </PressLink>
          ))}
        </Section>
      ) : null}
      <Section title="Konular (alt alanlar dahil)">
        {(topics.data ?? []).map((t) =>
          t.deleted_by_proposal_id ? (
            <CensorStrip key={t.id} proposalId={t.deleted_by_proposal_id} />
          ) : (
            <PressLink key={t.id} href={`/konu/${t.id}`} style={st.row}>
              <Text style={st.name}>{t.title}</Text>
              <Muted style={{ fontSize: 13 }}>{t.area_name} · {t.message_count} mesaj · sahibi {t.owner_scope}</Muted>
            </PressLink>
          ),
        )}
        {topics.data?.length === 0 ? <Muted>Bu alanda henüz kabul edilmiş konu yok.</Muted> : null}
      </Section>
      {me ? (
        <Button label="Bu alanda konu öner" onPress={() => router.push({ pathname: '/oneri/yeni', params: { type: 'KONU' } })} />
      ) : null}
    </Page>
  );
}

const st = StyleSheet.create({
  member: { fontFamily: fonts.serifItalic, fontSize: 15, color: paper.inkSoft, marginVertical: 8 },
  row: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 2 },
  name: { fontFamily: fonts.serifMedium, fontSize: 18, color: paper.ink },
});
