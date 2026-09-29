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
import { MyVotes } from '@/components/my-votes';
import { RevealTally } from '@/components/reveal-tally';
import { fmtDateTime, TYPE_LABELS } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function SessionResults() {
  const { id, izle } = useLocalSearchParams<{ id: string; izle?: string }>();
  const s = useApi<any>(`/decision-hour/sessions/${id}`, 15_000);
  const data = s.data;
  if (!data) return <Page>{s.error ? <ErrorNotice error={s.error} /> : <Loading />}</Page>;
  const open = data.status === 'OPEN';
  // Önerinin ana oylaması ve orantısız etkilenen kapsamlardaki ayrı oylamaları bir arada.
  const groups: { main: any; subs: any[] }[] = [];
  for (const it of data.items) {
    if (!it.concurrent) groups.push({ main: it, subs: [] });
    else groups.find((g) => g.main.proposal.id === it.proposal.id)?.subs.push(it);
  }

  return (
    <Page>
      <Kicker>Karar Saati · oturum #{data.id}</Kicker>
      <H1>{open ? 'Oylar mühürlü' : 'Sonuç açıklaması'}</H1>
      <Muted>
        {fmtDateTime(data.opened_at)} – {fmtDateTime(data.closed_at ?? data.closes_at)}
      </Muted>
      <View style={{ marginTop: 6, gap: 8 }}>
        <Seal hash={data.ledger_hash} label="oturum" />
        <MyVotes sessionId={data.id} />
      </View>
      <Rule double />
      {open ? (
        <InfoNotice>
          <Kicker>Pencerenin kapanmasına</Kicker>
          <Countdown target={data.closes_at} big />
          <Muted>Oylar açılmadan sayılmaz; deftere şimdilik yalnızca mühürler (commit) yazıldı.</Muted>
        </InfoNotice>
      ) : null}
      {!open && data.items.length === 0 ? (
        <InfoNotice>Bu oturumda oylanacak öneri yoktu; kuyruktaki öneriler henüz olgunlaşmamıştı ya da kuyruk boştu.</InfoNotice>
      ) : null}
      {groups.map(({ main, subs }) => (
        <View key={main.proposal.id} style={st.item}>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <Text style={st.no}>№{main.proposal.id}</Text>
            <Tag>{TYPE_LABELS[main.proposal.type]}</Tag>
            <Muted style={{ fontSize: 13 }}>seçmen: {main.proposal.scope} · {main.eligible_count} kişi</Muted>
            {subs.length ? <Tag tone="seal">eşzamanlı çoğunluk</Tag> : null}
          </View>
          <PressLink href={`/oneri/${main.proposal.id}`}>
            <ProposalTitle title={main.proposal.title} effective={main.proposal.effective_title} style={st.title} />
          </PressLink>
          {subs.length ? <Kicker>{main.vote_scope.name} oylaması</Kicker> : null}
          {main.result ? (
            <RevealTally result={main.result} autoplay={izle === String(main.proposal.id)} />
          ) : (
            <Muted>{main.sealed_votes} mühürlü oy · açılış pencere kapanınca</Muted>
          )}
          {subs.map((sub: any) => (
            <View key={sub.vote_scope.id} style={st.sub}>
              <Kicker style={{ color: paper.seal }}>
                {sub.vote_scope.name} oylaması · orantısız etkilenen kapsam · {sub.eligible_count} kişi
              </Kicker>
              <Muted style={{ fontSize: 13 }}>Havale yalnızca {sub.vote_scope.name} seçmenleri arasında çözülür.</Muted>
              {sub.result ? (
                <RevealTally result={sub.result} />
              ) : (
                <Muted>{sub.sealed_votes} mühürlü oy · açılış pencere kapanınca</Muted>
              )}
            </View>
          ))}
          {main.result?.overall?.summary ? (
            <Text style={[st.summary, !main.result.overall.passed && { color: paper.seal }]}>
              {main.result.overall.summary}
            </Text>
          ) : null}
          {main.result?.overall?.conflict ? (
            <InfoNotice>{main.result.overall.conflict.note}</InfoNotice>
          ) : null}
        </View>
      ))}
    </Page>
  );
}

const st = StyleSheet.create({
  item: { paddingVertical: 18, borderBottomWidth: 2, borderBottomColor: paper.ink, gap: 10 },
  no: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.seal },
  title: { fontFamily: fonts.serifBold, fontSize: 22, lineHeight: 28, color: paper.ink },
  sub: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 12, gap: 6, marginTop: 6 },
  summary: { fontFamily: fonts.monoBold, fontSize: 15, lineHeight: 22, color: paper.ink, marginTop: 4 },
});
