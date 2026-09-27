import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import {
  Countdown,
  ErrorNotice,
  H1,
  InfoNotice,
  Kicker,
  Loading,
  Muted,
  Page,
  PressLink,
  Rule,
  Seal,
  Tag,
} from '@/components/paper';
import { ProposalTitle } from '@/components/proposal-title';
import { RevealTally } from '@/components/reveal-tally';
import { fmtDateTime, TYPE_LABELS } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function SessionResults() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const s = useApi<any>(`/decision-hour/sessions/${id}`, 15_000);
  const data = s.data;
  if (!data) return <Page>{s.error ? <ErrorNotice error={s.error} /> : <Loading />}</Page>;
  const open = data.status === 'OPEN';

  return (
    <Page>
      <Kicker>Karar Saati · oturum #{data.id}</Kicker>
      <H1>{open ? 'Oylar mühürlü' : 'Sonuç açıklaması'}</H1>
      <Muted>
        {fmtDateTime(data.opened_at)} – {fmtDateTime(data.closed_at ?? data.closes_at)}
      </Muted>
      <View style={{ marginTop: 6 }}>
        <Seal hash={data.ledger_hash} label="oturum" />
      </View>
      <Rule double />
      {open ? (
        <InfoNotice>
          <Kicker>Pencerenin kapanmasına</Kicker>
          <Countdown target={data.closes_at} big />
          <Muted>Oylar açılmadan sayılmaz; deftere şimdilik yalnızca mühürler (commit) yazıldı.</Muted>
        </InfoNotice>
      ) : null}
      {data.items.map((it: any) => (
        <View key={it.proposal.id} style={st.item}>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Text style={st.no}>№{it.proposal.id}</Text>
            <Tag>{TYPE_LABELS[it.proposal.type]}</Tag>
            <Muted style={{ fontSize: 13 }}>seçmen: {it.proposal.scope} · {it.eligible_count} kişi</Muted>
          </View>
          <PressLink href={`/oneri/${it.proposal.id}`}>
            <ProposalTitle title={it.proposal.title} effective={it.proposal.effective_title} style={st.title} />
          </PressLink>
          {it.result ? (
            <RevealTally result={it.result} />
          ) : (
            <Muted>{it.sealed_votes} mühürlü oy · açılış pencere kapanınca</Muted>
          )}
        </View>
      ))}
    </Page>
  );
}

const st = StyleSheet.create({
  item: { paddingVertical: 18, borderBottomWidth: 2, borderBottomColor: paper.ink, gap: 10 },
  no: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.seal },
  title: { fontFamily: fonts.serifBold, fontSize: 22, lineHeight: 28, color: paper.ink },
});
