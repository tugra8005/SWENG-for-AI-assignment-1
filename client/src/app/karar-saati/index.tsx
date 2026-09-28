import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  Countdown,
  ErrorNotice,
  H1,
  InfoNotice,
  Kicker,
  Mono,
  Muted,
  Page,
  PressLink,
  Rule,
  Section,
  Tag,
} from '@/components/paper';
import { maturityLine, ProposalTitle } from '@/components/proposal-title';
import { useAuth } from '@/lib/auth';
import { useClock } from '@/lib/clock';
import { fmtDateTime, fmtWeekdayTime, shortHash, TYPE_LABELS } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

function BallotItem({ item, onVoted }: { item: any; onVoted: () => void }) {
  const [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [commit, setCommit] = useState<string | null>(null);
  const p = item.proposal;

  const cast = async (body: object) => {
    setError(null);
    try {
      const r = await api('/decision-hour/votes', { method: 'POST', body: { proposal_id: p.id, ...body } });
      setCommit(r.commit);
      onVoted();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <View style={st.item}>
      <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Text style={st.no}>№{p.id}</Text>
        <Tag>{TYPE_LABELS[p.type]}</Tag>
        <Muted style={{ fontSize: 13 }}>seçmen: {p.scope}</Muted>
      </View>
      <PressLink href={`/oneri/${p.id}`}>
        <ProposalTitle title={p.title} effective={p.effective_title} style={st.title} />
      </PressLink>
      {item.narrowings?.map((n: any, i: number) => (
        <Text key={i} style={{ fontFamily: fonts.serifBold, color: paper.seal }}>{n.message}</Text>
      ))}
      <View style={{ flexDirection: 'row', gap: 16, alignItems: 'baseline', marginTop: 4 }}>
        <Kicker>Oy ağırlığınız</Kicker>
        <Text style={st.weight}>{item.weight}</Text>
        {item.weight > 1 ? <Muted>({item.weight - 1} havale sizde bitiyor)</Muted> : null}
      </View>

      {item.can_vote ? (
        item.kind === 'approval' ? (
          <View style={{ gap: 6, marginTop: 8 }}>
            <Muted>Kabul edebileceğiniz tüm metinleri işaretleyin.</Muted>
            {item.texts.map((t: any) => {
              const on = picked.includes(t.id);
              return (
                <Pressable
                  key={t.id}
                  onPress={() => setPicked((x) => (on ? x.filter((i) => i !== t.id) : [...x, t.id]))}
                  accessibilityRole="checkbox"
                  aria-checked={on}
                  style={[st.textOpt, on && { borderColor: paper.seal, backgroundColor: paper.sealWash }]}
                >
                  <Text style={st.box}>{on ? '☒' : '☐'}</Text>
                  <View style={{ flex: 1 }}>
                    <Kicker>Metin #{t.id} · {t.author}</Kicker>
                    <Body>{t.text}</Body>
                  </View>
                </Pressable>
              );
            })}
            <Button label="Onayları mühürle" onPress={() => cast({ approvals: picked })} />
          </View>
        ) : (
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 10 }}>
            <Button label="Evet" onPress={() => cast({ approve: true })} />
            <Button label="Hayır" variant="secondary" onPress={() => cast({ approve: false })} />
          </View>
        )
      ) : (
        <Muted style={{ marginTop: 8 }}>{item.reason}</Muted>
      )}
      {commit ? (
        <Text style={st.commit}>Mühürlendi · commit ⌗ {shortHash(commit)} — pencere kapanınca açılacak</Text>
      ) : null}
      <ErrorNotice error={error} />
    </View>
  );
}

export default function DecisionHour() {
  const { me } = useAuth();
  const { status, sync } = useClock();
  const ballot = useApi<any>(me && status?.open_session ? '/decision-hour/ballot' : null);
  const sessions = useApi<any[]>('/decision-hour/sessions', 20_000);
  const open = status?.open_session;

  return (
    <Page>
      <Kicker>Planlı oylama oturumu</Kicker>
      <H1>Karar Saati</H1>
      <Muted>
        Oturum haftada bir açılır ({fmtWeekdayTime(status?.next_scheduled_at)},{' '}
        {status?.window_minutes ?? '…'} dakika; yönetmelikteki karar_saati maddesi). Açılış anında seçmen
        listesi ve havale grafı kilitlenir; oylar pencere boyunca mühürlüdür, kapanışta tek tek açılır.
      </Muted>
      <Rule double />

      <View style={st.clock}>
        <Kicker style={open ? { color: paper.seal } : undefined}>
          {open ? `Oturum #${open.id} · pencerenin kapanmasına` : 'Bir sonraki oturuma'}
        </Kicker>
        <Countdown target={open ? open.closes_at : status?.next_scheduled_at ?? null} big />
        <Muted>{fmtDateTime(open ? open.closes_at : status?.next_scheduled_at)}</Muted>
      </View>

      {open ? (
        <Section title="Oy pusulası" aside={<Kicker>{open.item_count} öneri</Kicker>}>
          {!me ? <InfoNotice>Oy vermek için giriş yapın.</InfoNotice> : null}
          {ballot.data?.items.map((it: any) => (
            <BallotItem key={it.proposal.id} item={it} onVoted={() => { ballot.reload(); sync(); }} />
          ))}
        </Section>
      ) : (
        <Section title="Kuyruk" aside={<Kicker>{status?.queued.length ?? 0} öneri</Kicker>}>
          {status?.queued.map((q: any) => {
            const maturing = maturityLine(q.maturity);
            return (
              <PressLink key={q.id} href={`/oneri/${q.id}`} style={st.queued}>
                <Text style={st.no}>№{q.id}</Text>
                <Tag>{TYPE_LABELS[q.type]}</Tag>
                <View style={{ flex: 1, minWidth: 180, gap: 2 }}>
                  <ProposalTitle
                    title={q.title}
                    effective={q.effective_title}
                    style={{ ...st.title, fontSize: 17, lineHeight: 22 }}
                  />
                  {maturing ? <Text style={st.maturing}>{maturing}</Text> : null}
                </View>
              </PressLink>
            );
          })}
          {status && status.queued.length === 0 ? <Muted>Kuyruk boş.</Muted> : null}
        </Section>
      )}

      <Section title="Geçmiş oturumlar">
        {(sessions.data ?? []).map((s) => (
          <PressLink key={s.id} href={`/karar-saati/${s.id}`} style={st.queued}>
            <Mono style={{ color: paper.seal }}>#{s.id}</Mono>
            <Body style={{ flex: 1 }}>
              {fmtDateTime(s.opened_at)} · {s.item_count} öneri {s.scheduled ? '' : '· elle açıldı'}
            </Body>
            <Tag tone={s.status === 'OPEN' ? 'seal' : 'ink'}>{s.status === 'OPEN' ? 'Açık' : 'Kapandı'}</Tag>
          </PressLink>
        ))}
        {sessions.data?.length === 0 ? <Muted>Henüz oturum yok.</Muted> : null}
      </Section>
    </Page>
  );
}

const st = StyleSheet.create({
  clock: { alignItems: 'center', paddingVertical: 12, gap: 4 },
  item: { paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 6 },
  no: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.seal },
  title: { fontFamily: fonts.serifBold, fontSize: 20, lineHeight: 26, color: paper.ink },
  weight: { fontFamily: fonts.monoBold, fontSize: 28, color: paper.ink },
  textOpt: { flexDirection: 'row', gap: 10, borderWidth: 1, borderColor: paper.hairline, padding: 10 },
  box: { fontFamily: fonts.mono, fontSize: 20, color: paper.seal },
  commit: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal, marginTop: 8 },
  maturing: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 17, color: paper.seal },
  queued: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
    flexWrap: 'wrap',
  },
});
