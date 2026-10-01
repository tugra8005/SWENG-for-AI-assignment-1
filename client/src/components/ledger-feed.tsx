/**
 * "Defterden" kutusu: defterin son kayıtları, en yenisi önce. Her satırda kayıt numarası, türün okunur
 * adı, zaman ve mühür; mühre dokununca kayıt Defter sayfasında açılır.
 */
import { StyleSheet, Text, View } from 'react-native';

import { Kicker, Loading, Seal, Section } from '@/components/paper';
import { fmtDateTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Recent = { seq: number; records: { seq: number; label: string; ts: string; hash: string }[] };

export function LedgerFeed({ limit = 6 }: { limit?: number }) {
  const { data } = useApi<Recent>(`/ledger/recent?limit=${limit}`, 30_000);
  return (
    <Section title="Defterden" aside={<Kicker>{data ? `${data.seq} kayıt` : 'son kayıtlar'}</Kicker>}>
      {!data ? <Loading /> : null}
      {data?.records.map((r) => (
        <View key={r.seq} style={st.row}>
          <Text style={st.seq}>#{r.seq}</Text>
          <View style={{ flex: 1, gap: 1 }}>
            <Text style={st.label}>{r.label}</Text>
            <Text style={st.ts}>{fmtDateTime(r.ts)}</Text>
          </View>
          <Seal hash={r.hash} />
        </View>
      ))}
    </Section>
  );
}

const st = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
  },
  seq: { fontFamily: fonts.monoMedium, fontSize: 11, color: paper.muted, width: 40 },
  label: { fontFamily: fonts.serif, fontSize: 15, color: paper.ink },
  ts: { fontFamily: fonts.mono, fontSize: 10, color: paper.muted },
});
