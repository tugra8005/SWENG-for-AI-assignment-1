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

const choiceLabel = (c: any) =>
  Array.isArray(c) ? (c.length ? c.map((x: number) => `#${x}`).join(', ') : 'hiçbiri') : String(c);

/** Tarafsız seçenek: EVET ve HAYIR aynı stilde; seçilen dolar. */
function VoteOption({ label, selected, disabled, onPress }: {
  label: string; selected?: boolean; disabled?: boolean; onPress?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      aria-pressed={selected}
      aria-disabled={disabled}
      style={[st.option, selected && st.optionOn, disabled && !selected && st.optionOff]}
    >
      <Text style={[st.optionText, selected && { color: paper.bg }, disabled && !selected && { color: paper.muted }]}>
        {label}
      </Text>
    </Pressable>
  );
}

/** Bir oylama: ana oylama ya da orantısız etkilenen kapsamın ayrı oylaması. */
function VoteSection({ item, label, onVoted }: { item: any; label?: string; onVoted: () => void }) {
  const [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [commit, setCommit] = useState<string | null>(null);
  const p = item.proposal;

  const cast = async (body: object) => {
    setError(null);
    try {
      const scope = item.concurrent ? { vote_scope_id: item.vote_scope.id } : {};
      const r = await api('/decision-hour/votes', { method: 'POST', body: { proposal_id: p.id, ...scope, ...body } });
      setCommit(r.commit);
      onVoted();
    } catch (e) {
      setError(e);
    }
  };
  const voted = item.voted;
  const mine = item.my_choice;

  return (
    <View style={[st.section, label ? st.sectionLabelled : null]}>
      {label ? <Text style={st.sectionTitle}>{label}</Text> : null}
      {item.concurrent ? (
        <Muted style={{ fontSize: 13 }}>
          Öneri {item.vote_scope.name} payını orantısız azaltıyor; {item.vote_scope.name} seçmenleri ayrıca oylar
          ve öneri burada da çoğunluk almalı. Havale yalnızca {item.vote_scope.name} seçmenleri arasında çözülür.
        </Muted>
      ) : null}
      <View style={{ flexDirection: 'row', gap: 16, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <Kicker>Oy ağırlığınız</Kicker>
        <Text style={st.weight}>{item.weight}</Text>
        {item.weight > 1 ? <Muted>({item.weight - 1} havale sizde bitiyor)</Muted> : null}
      </View>
      {item.eligible && item.weight > 0 ? (
        <Text style={[st.secrecy, item.open_vote && { color: paper.seal }]}>{item.secrecy_note}</Text>
      ) : null}

      {item.kind === 'approval' && (item.can_vote || voted) ? (
        <View style={{ gap: 6, marginTop: 8 }}>
          {!voted ? <Muted>Kabul edebileceğiniz tüm metinleri işaretleyin.</Muted> : null}
          {item.texts.map((t: any) => {
            const on = voted ? (mine ?? []).includes(t.id) : picked.includes(t.id);
            return (
              <Pressable
                key={t.id}
                disabled={voted}
                onPress={() => setPicked((x) => (on ? x.filter((i) => i !== t.id) : [...x, t.id]))}
                accessibilityRole="checkbox"
                aria-checked={on}
                style={[st.textOpt, on && { borderColor: paper.ink, backgroundColor: paper.bgDeep }]}
              >
                <Text style={st.box}>{on ? '☒' : '☐'}</Text>
                <View style={{ flex: 1 }}>
                  <Kicker>Metin #{t.id}</Kicker>
                  <Text style={st.author}>{t.author}</Text>
                  <Body>{t.text}</Body>
                </View>
              </Pressable>
            );
          })}
          {!voted ? <Button label="Onayları mühürle" onPress={() => cast({ approvals: picked })} /> : null}
        </View>
      ) : null}
      {item.kind === 'binary' && (item.can_vote || voted) ? (
        <View style={{ flexDirection: 'row', gap: 12, marginTop: 10 }}>
          <VoteOption label="EVET" selected={voted && mine === 'EVET'} disabled={voted} onPress={() => cast({ approve: true })} />
          <VoteOption label="HAYIR" selected={voted && mine === 'HAYIR'} disabled={voted} onPress={() => cast({ approve: false })} />
        </View>
      ) : null}
      {voted ? (
        <Text style={st.chosen}>Seçiminiz: {choiceLabel(mine)} · mühürlendi</Text>
      ) : !item.can_vote ? (
        <Muted style={{ marginTop: 8 }}>{item.reason}</Muted>
      ) : null}
      {commit ? (
        <Text style={st.commit}>commit ⌗ {shortHash(commit)} · pencere kapanınca açılacak</Text>
      ) : null}
      <ErrorNotice error={error} />
    </View>
  );
}

/** Öneri başına tek kart; eşzamanlı çoğunlukta yalnızca oy hakkınız olan alt oylamalar görünür. */
function BallotCard({ items, onVoted }: { items: any[]; onVoted: () => void }) {
  const main = items.find((i) => !i.concurrent) ?? items[0];
  const p = main.proposal;
  const visible = items.filter((i) => !i.concurrent || i.eligible);
  const multi = items.some((i) => i.concurrent);
  return (
    <View style={st.item}>
      <View style={st.meta}>
        <Text style={st.no}>№{p.id}</Text>
        <Tag>{TYPE_LABELS[p.type]}</Tag>
        <Muted style={{ fontSize: 13 }}>seçmen: {p.scope}</Muted>
      </View>
      <PressLink href={`/oneri/${p.id}`}>
        <ProposalTitle title={p.title} effective={p.effective_title} style={st.title} />
      </PressLink>
      {main.narrowings?.map((n: any, i: number) => (
        <Text key={i} style={{ fontFamily: fonts.serifBold, color: paper.seal }}>{n.message}</Text>
      ))}
      {main.shared_resource_notes?.map((n: string) => (
        <Text key={n} style={st.sharedNote}>
          <Text style={{ fontFamily: fonts.monoBold }}>AYNI KAYNAK · </Text>
          {n}
        </Text>
      ))}
      {visible.map((it) => (
        <VoteSection
          key={it.vote_scope.id}
          item={it}
          label={multi ? `${it.vote_scope.name} oylaması${it.concurrent ? ' · orantısız etkilenen kapsam' : ''}` : undefined}
          onVoted={onVoted}
        />
      ))}
    </View>
  );
}

function groupByProposal(items: any[]): any[][] {
  const groups = new Map<number, any[]>();
  for (const it of items) groups.set(it.proposal.id, [...(groups.get(it.proposal.id) ?? []), it]);
  return [...groups.values()];
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
          {groupByProposal(ballot.data?.items ?? []).map((items) => (
            <BallotCard
              key={items[0].proposal.id}
              items={items}
              onVoted={() => {
                ballot.reload();
                sync();
              }}
            />
          ))}
        </Section>
      ) : (
        <Section title="Kuyruk" aside={<Kicker>{status?.queued.length ?? 0} öneri</Kicker>}>
          {status?.queued.map((q: any) => {
            const maturing = maturityLine(q.maturity);
            return (
              <PressLink key={q.id} href={`/oneri/${q.id}`} style={st.queuedStack}>
                <View style={st.meta}>
                  <Text style={st.no}>№{q.id}</Text>
                  <Tag>{TYPE_LABELS[q.type]}</Tag>
                </View>
                <View style={{ gap: 2 }}>
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
  sharedNote: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, color: paper.seal, borderLeftWidth: 2, borderLeftColor: paper.seal, paddingLeft: 8 },
  textOpt: { flexDirection: 'row', gap: 10, borderWidth: 1, borderColor: paper.hairline, padding: 10 },
  box: { fontFamily: fonts.mono, fontSize: 20, color: paper.seal },
  commit: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal, marginTop: 8 },
  meta: { flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
  section: { gap: 6, marginTop: 6 },
  sectionLabelled: { borderLeftWidth: 3, borderLeftColor: paper.ink, paddingLeft: 10, marginTop: 10 },
  sectionTitle: { fontFamily: fonts.monoBold, fontSize: 13, letterSpacing: 1, color: paper.ink },
  secrecy: { fontFamily: fonts.serifItalic, fontSize: 14, lineHeight: 20, color: paper.inkSoft },
  author: { fontFamily: fonts.serifItalic, fontSize: 13, color: paper.inkSoft },
  option: {
    borderWidth: 1.5,
    borderColor: paper.ink,
    paddingVertical: 10,
    paddingHorizontal: 22,
    minWidth: 96,
    alignItems: 'center',
  },
  optionOn: { backgroundColor: paper.ink },
  optionOff: { borderColor: paper.hairline },
  optionText: { fontFamily: fonts.monoBold, fontSize: 14, letterSpacing: 2, color: paper.ink },
  chosen: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.ink, marginTop: 6 },
  queuedStack: { gap: 4, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline },
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
