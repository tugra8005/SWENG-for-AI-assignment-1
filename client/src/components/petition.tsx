/**
 * Muhatap ve dilekçe parçaları: önerinin/konunun nereye iletildiğini söyleyen satır ve konunun
 * yan sütunundaki dilekçe kutusu (iletildi → yanıt / süre).
 */

import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Kicker } from '@/components/paper';
import { fmtDate } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

export type Addressee = { id: string; kind: 'TAKVIM' | 'KURUM' | 'IC'; name: string; short: string; level: string };

export type PetitionSummary = {
  id: number;
  number: string;
  kind: 'TALEP' | 'KARAR';
  subject: string;
  sent_at: string;
  due_at: string;
  recipients: { id: string; name: string; status: 'YANITLANDI' | 'BEKLIYOR' | 'SURE_DOLDU' }[];
  replied: number;
  overdue: number;
};

const KIND_NOTE: Record<Addressee['kind'], string> = {
  TAKVIM: 'kabul edilirse Meşveret Takvimi’ne yazılır',
  KURUM: 'kabul edilirse kuruma dilekçe olarak gider; Kararı da',
  IC: 'Meşveret’in iç düzeni',
};

/** "→ İstanbul Büyükşehir Belediyesi · kabul edilirse kuruma dilekçe olarak gider" */
export function AddresseeLine({ a, note = true }: { a?: Addressee | null; note?: boolean }) {
  if (!a) return null;
  return (
    <Text style={st.line}>
      <Text style={st.arrow}>→ </Text>
      <Text style={st.name}>{a.name}</Text>
      {note ? <Text style={st.note}> · {KIND_NOTE[a.kind]}</Text> : null}
    </Text>
  );
}

export const STATUS_TEXT: Record<PetitionSummary['recipients'][number]['status'], string> = {
  YANITLANDI: 'yanıtlandı',
  BEKLIYOR: 'yanıt bekleniyor',
  SURE_DOLDU: 'süresinde yanıt verilmedi',
};

/** Konunun dilekçeleri: evrak numarası, alıcılar ve her alıcının durumu. */
export function PetitionBox({ items }: { items?: PetitionSummary[] | null }) {
  if (!items?.length) return null;
  return (
    <View style={st.box}>
      <Kicker style={{ color: paper.seal }}>Dilekçe{items.length > 1 ? 'ler' : ''}</Kicker>
      {items.map((p) => (
        <Link key={p.id} href={`/dilekce/${p.id}`} style={st.item}>
          <Text style={st.number}>{p.number} · {p.kind === 'KARAR' ? 'karar bildirimi' : 'talep'}</Text>
          {'\n'}
          <Text style={st.meta}>iletildi {fmtDate(p.sent_at)} · yasal süre {fmtDate(p.due_at)}</Text>
          {p.recipients.map((r) => (
            <Text key={r.id}>
              {'\n'}
              <Text style={st.recipient}>{r.name}: </Text>
              <Text style={[st.status, r.status === 'YANITLANDI' && { color: paper.ok },
                r.status === 'SURE_DOLDU' && { color: paper.seal }]}>
                {STATUS_TEXT[r.status]}
              </Text>
            </Text>
          ))}
        </Link>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  line: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.inkSoft, marginTop: 2 },
  arrow: { fontFamily: fonts.monoBold, color: paper.seal },
  name: { fontFamily: fonts.serifMedium, color: paper.ink },
  note: { fontFamily: fonts.serifItalic, color: paper.muted },
  box: { marginTop: 18, borderWidth: 1, borderColor: paper.ink, padding: 12, gap: 8, backgroundColor: paper.sheet },
  item: { paddingTop: 6, borderTopWidth: 1, borderTopColor: paper.hairline },
  number: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 0.5, color: paper.ink },
  meta: { fontFamily: fonts.mono, fontSize: 11, color: paper.muted },
  recipient: { fontFamily: fonts.serif, fontSize: 14, color: paper.ink },
  status: { fontFamily: fonts.serifItalic, fontSize: 14, color: paper.inkSoft },
});
