import { StyleSheet, Text, View } from 'react-native';

import { Kicker, Muted, PressLink, Tag } from '@/components/paper';
import { useClock } from '@/lib/clock';
import { fmtRemaining, STATUS_LABELS, TYPE_LABELS } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

export type ProposalSummary = {
  id: number;
  type: string;
  status: string;
  lane: string;
  title: string;
  proposer: string;
  scope: string;
  area_name: string | null;
  deadline_at: string | null;
};

export function ProposalRow({ p }: { p: ProposalSummary }) {
  const { now } = useClock();
  const remaining =
    p.deadline_at && (p.status === 'SILENT' || p.status === 'RIVAL_PERIOD')
      ? fmtRemaining(new Date(p.deadline_at).getTime() - now())
      : null;
  return (
    <PressLink href={`/oneri/${p.id}`} style={st.row}>
        <Text style={st.number}>№{p.id}</Text>
        <View style={{ flex: 1, gap: 4 }}>
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            <Tag>{TYPE_LABELS[p.type] ?? p.type}</Tag>
            <Tag tone={p.status === 'ACCEPTED' ? 'ink' : p.status === 'REJECTED' ? 'muted' : 'seal'}>
              {STATUS_LABELS[p.status] ?? p.status}
            </Tag>
          </View>
          <Text style={st.title}>{p.title}</Text>
          <Muted style={{ fontSize: 14 }}>
            {p.proposer} · {p.scope}
            {p.area_name ? ` · ${p.area_name}` : ''}
            {remaining ? ` · ${remaining}` : ''}
          </Muted>
        </View>
    </PressLink>
  );
}

export function EmptyLine({ children }: { children: string }) {
  return (
    <View style={{ paddingVertical: 10 }}>
      <Kicker style={{ color: paper.muted }}>{children}</Kicker>
    </View>
  );
}

const st = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
  },
  number: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.seal, width: 44, paddingTop: 2 },
  title: { fontFamily: fonts.serifMedium, fontSize: 19, lineHeight: 24, color: paper.ink },
});
