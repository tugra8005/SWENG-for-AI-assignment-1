import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Body,
  Button,
  CensorStrip,
  Countdown,
  Kicker,
  Loading,
  Mono,
  Muted,
  Page,
  PressLink,
  Section,
} from '@/components/paper';
import { DelegationNotices } from '@/components/delegation-expiry';
import { EmptyLine, ProposalRow, type ProposalSummary } from '@/components/proposal-row';
import { ProposalTitle } from '@/components/proposal-title';
import { useAuth } from '@/lib/auth';
import { useClock } from '@/lib/clock';
import { fmtDateTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Area = { id: string; name: string; parent_id: string | null; topic_count: number };

function DecisionHourBand() {
  const { status } = useClock();
  if (!status) return null;
  const open = status.open_session;
  return (
    <View style={[st.band, open && { backgroundColor: paper.ink }]}>
      <View style={{ flex: 1, minWidth: 220, gap: 4 }}>
        <Kicker style={open ? { color: paper.bgDeep } : undefined}>
          {open ? 'Karar Saati · pencere açık' : 'Karar Saati · sonraki oturum'}
        </Kicker>
        <Countdown
          target={open ? open.closes_at : status.next_scheduled_at}
          big
          color={open ? paper.bg : paper.ink}
          prefix={open ? 'kapanışa' : undefined}
        />
        <Text style={[st.bandNote, open && { color: paper.bgDeep }]}>
          {open
            ? `${open.item_count} öneri oylanıyor · kapanış ${fmtDateTime(open.closes_at)}`
            : `${fmtDateTime(status.next_scheduled_at)} · kuyrukta ${status.queued.length} öneri`}
        </Text>
      </View>
      <Pressable
        onPress={() => router.push('/karar-saati')}
        accessibilityRole="button"
        style={[st.bandButton, open && { borderColor: paper.bg }]}
      >
        <Text style={[st.bandButtonText, open && { color: paper.bg }]}>
          {open ? 'Oy pusulası →' : 'Kuyruğu gör →'}
        </Text>
      </Pressable>
    </View>
  );
}

function AreaTree({ areas }: { areas: Area[] }) {
  const children = (parent: string | null) => areas.filter((a) => a.parent_id === parent);
  const render = (parent: string | null, depth: number): React.ReactNode =>
    children(parent).map((a) => (
      <View key={a.id}>
        <PressLink href={`/alan/${a.id}`} style={[st.areaRow, { paddingLeft: depth * 18 }]}>
          <Text style={[st.areaName, depth === 0 && { fontFamily: fonts.serifBold }]}>
            {depth > 0 ? '└ ' : '§ '}
            {a.name}
          </Text>
          <Mono style={{ color: paper.muted }}>{a.topic_count ? `${a.topic_count} konu` : ''}</Mono>
        </PressLink>
        {render(a.id, depth + 1)}
      </View>
    ));
  return <View>{render(null, 0)}</View>;
}

export default function Home() {
  const { me } = useAuth();
  const proposals = useApi<ProposalSummary[]>('/proposals?state=open', 30_000);
  const areas = useApi<Area[]>('/areas');
  const topics = useApi<any[]>('/topics');
  const fast = (proposals.data ?? []).filter((p) => p.status === 'SILENT');
  const slow = (proposals.data ?? []).filter((p) => p.status !== 'SILENT');

  return (
    <Page>
      <DecisionHourBand />
      {me ? <DelegationNotices /> : null}

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 18, gap: 12, flexWrap: 'wrap' }}>
        <Body style={{ flex: 1, minWidth: 240, fontFamily: fonts.serifItalic, color: paper.inkSoft }}>
          Herkes konu önerebilir. Öneriler sessiz onayla ya da Karar Saati&apos;nde oylanarak kabul
          edilir; her karar deftere mühürlenir.
        </Body>
        {me ? (
          <Button label="Konu öner" onPress={() => router.push('/oneri/yeni?type=KONU')} />
        ) : (
          <Button label="Giriş yap" variant="secondary" onPress={() => router.push('/giris')} />
        )}
      </View>

      <Section title="İtiraza açık öneriler" aside={<Kicker>hızlı şerit · sessiz onay</Kicker>}>
        {proposals.loading ? <Loading /> : null}
        {fast.map((p) => <ProposalRow key={p.id} p={p} sectionStatus="SILENT" />)}
        {!proposals.loading && fast.length === 0 ? <EmptyLine>itiraza açık öneri yok</EmptyLine> : null}
      </Section>

      <Section title="Karar Saati kuyruğu" aside={<Kicker>yavaş şerit</Kicker>}>
        {slow.map((p) => <ProposalRow key={p.id} p={p} sectionStatus="QUEUED" />)}
        {!proposals.loading && slow.length === 0 ? <EmptyLine>kuyrukta öneri yok</EmptyLine> : null}
      </Section>

      <View style={st.columns}>
        <View style={{ flex: 1, minWidth: 260 }}>
          <Section title="Alanlar">
            {areas.data ? <AreaTree areas={areas.data} /> : <Loading />}
          </Section>
        </View>
        <View style={{ flex: 1.3, minWidth: 280 }}>
          <Section title="Konular">
            {(topics.data ?? []).slice(0, 12).map((t) =>
              t.deleted_by_proposal_id ? (
                <CensorStrip key={t.id} proposalId={t.deleted_by_proposal_id} basis={t.deletion_basis} />
              ) : (
                <PressLink key={t.id} href={`/konu/${t.id}`} style={st.topicRow}>
                  <ProposalTitle title={t.title} effective={t.effective_title} style={st.topicTitle} />
                  <Muted style={{ fontSize: 14 }}>
                    {t.area_name} · {t.message_count} mesaj
                    {t.status === 'CLOSED' ? ' · karara bağlandı' : ''}
                  </Muted>
                </PressLink>
              ),
            )}
          </Section>
        </View>
      </View>
    </Page>
  );
}

const st = StyleSheet.create({
  band: {
    borderWidth: 1.5,
    borderColor: paper.ink,
    padding: 16,
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 14,
    backgroundColor: paper.sheet,
  },
  bandNote: { fontFamily: fonts.serifItalic, fontSize: 14, color: paper.inkSoft },
  bandButton: { borderWidth: 1.5, borderColor: paper.ink, paddingVertical: 10, paddingHorizontal: 14 },
  bandButtonText: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.4, color: paper.ink },
  columns: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 28 },
  areaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
  },
  areaName: { fontFamily: fonts.serif, fontSize: 16, color: paper.ink },
  topicRow: { paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 2 },
  topicTitle: { fontFamily: fonts.serifMedium, fontSize: 18, color: paper.ink },
});
