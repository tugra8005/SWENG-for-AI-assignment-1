/**
 * Takvim parçaları: takvim yaprağı (tarih bloğu), etkinlik satırı, konunun yan sütunundaki
 * etkinlik kutusu ve öneri formundaki etkinlik alanları.
 */

import { Link } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ChoiceChip, Field, Kicker, Muted, PressLink } from '@/components/paper';
import { maskBirthDate } from '@/lib/birth-date';
import { fmtDay, fmtMonthShort, fmtTime, fmtWeekday } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

export type EventStatus = 'YAKLASIYOR' | 'SURUYOR' | 'GERCEKLESTI';
export type Venue = { kind: 'SALON' | 'ADRES' | 'CEVRIMICI'; label: string; text: string };

export type EventSummary = {
  id: number;
  title: string;
  topic_id: number;
  area_name: string | null;
  scope: string | null;
  starts_at: string;
  ends_at: string;
  venue: Venue;
  status: EventStatus;
  attendees: number;
  reports: number;
};

export const EVENT_STATUS: Record<EventStatus, string> = {
  YAKLASIYOR: 'yaklaşıyor',
  SURUYOR: 'şu anda sürüyor',
  GERCEKLESTI: 'gerçekleşti',
};

/** "6 kişi geliyor"; etkinlik başladıktan sonra katılım kapanır: "6 kişi Geliyorum dedi". */
export function attendeeLine(e: { attendees: number; status: EventStatus }): string | null {
  if (!e.attendees) return null;
  return e.status === 'YAKLASIYOR' ? `${e.attendees} kişi geliyor` : `${e.attendees} kişi Geliyorum dedi`;
}

/** Takvim yaprağı: üstte ay, ortada gün, altta gün adı ve saat. */
export function DateBlock({ iso, small }: { iso: string; small?: boolean }) {
  return (
    <View style={[st.leaf, small && st.leafSmall]} accessibilityLabel={`${fmtDay(iso)} ${fmtWeekday(iso)} ${fmtTime(iso)}`}>
      <Text style={[st.leafMonth, small && { fontSize: 10 }]}>{fmtMonthShort(iso)}</Text>
      <Text style={[st.leafDay, small && { fontSize: 26, lineHeight: 30 }]}>{fmtDay(iso)}</Text>
      <Text style={[st.leafWeekday, small && { fontSize: 11 }]}>
        {fmtWeekday(iso)} {fmtTime(iso)}
      </Text>
    </View>
  );
}

/** Ajandadaki satır: yaprak, başlık, yer, durum. */
export function EventRow({ e }: { e: EventSummary }) {
  const past = e.status === 'GERCEKLESTI';
  return (
    <PressLink href={`/etkinlik/${e.id}`} style={st.row}>
      <DateBlock iso={e.starts_at} small />
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={[st.rowTitle, past && { color: paper.inkSoft }]}>{e.title}</Text>
        <Text style={st.rowVenue}>
          {e.venue.kind === 'CEVRIMICI' ? 'Çevrim içi · ' : ''}
          {e.venue.text}
        </Text>
        <Text style={st.rowMeta}>
          {[e.area_name, e.scope, EVENT_STATUS[e.status],
            attendeeLine(e),
            e.reports ? `${e.reports} rapor` : null].filter(Boolean).join(' · ')}
        </Text>
      </View>
    </PressLink>
  );
}

/** Konunun yan sütununda: bu konunun etkinliği. */
export function EventBox({ e }: { e?: EventSummary | null }) {
  if (!e) return null;
  return (
    <View style={st.box}>
      <Kicker style={{ color: paper.seal }}>Takvimde · {EVENT_STATUS[e.status]}</Kicker>
      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
        <DateBlock iso={e.starts_at} small />
        <View style={{ flex: 1 }}>
          <Text style={st.boxVenue}>{e.venue.text}</Text>
          <Muted style={{ fontSize: 13 }}>
            {fmtTime(e.starts_at)}–{fmtTime(e.ends_at)}
            {e.attendees ? ` · ${attendeeLine(e)}` : ''}
          </Muted>
        </View>
      </View>
      <Link href={`/etkinlik/${e.id}`} style={st.boxLink}>Etkinlik sayfası →</Link>
    </View>
  );
}

// --- öneri formu ----------------------------------------------------------------------------------

export type EventInput = { starts_at: string; duration_min: number; venue: { kind: string; text?: string } };

/** "1930" → "19:30"; yalnız rakam alınır. */
export function maskTime(raw: string): string {
  const d = raw.replace(/\D/g, '').slice(0, 4);
  return d.length > 2 ? `${d.slice(0, 2)}:${d.slice(2)}` : d;
}

/** "GG.AA.YYYY" + "SS:DD" → İstanbul saatiyle ISO; geçersizse null. */
export function eventIso(date: string, time: string): string | null {
  const m = date.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  const t = time.match(/^(\d{2}):(\d{2})$/);
  if (!m || !t || Number(t[1]) > 23 || Number(t[2]) > 59) return null;
  const iso = `${m[3]}-${m[2]}-${m[1]}T${t[1]}:${t[2]}:00+03:00`;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime()) || d.getUTCDate() !== new Date(`${m[3]}-${m[2]}-${m[1]}T12:00:00Z`).getUTCDate()) {
    return null;
  }
  return iso;
}

const DURATIONS = [60, 90, 120, 180];
const VENUES = [
  { value: 'SALON', label: 'Ortak toplantı salonu', note: 'Genel kapsamın kaynağı (R2)' },
  { value: 'ADRES', label: 'Bir adres' },
  { value: 'CEVRIMICI', label: 'Çevrim içi' },
];

/** Takvime giden konunun etkinlik bilgisi. Boş bırakılırsa konu etkinliksiz takvim konusudur. */
export function EventFields({ onChange }: { onChange: (v: EventInput | null) => void }) {
  const [on, setOn] = useState(false);
  const [date, setDate] = useState('');
  const [time, setTime] = useState('20:00');
  const [minutes, setMinutes] = useState(120);
  const [venue, setVenue] = useState('SALON');
  const [text, setText] = useState('');
  const iso = eventIso(date, time);
  const value = useMemo<EventInput | null>(
    () => (on && iso ? { starts_at: iso, duration_min: minutes, venue: venue === 'SALON' ? { kind: venue } : { kind: venue, text } } : null),
    [on, iso, minutes, venue, text],
  );
  useEffect(() => onChange(value), [value, onChange]);
  return (
    <View style={st.fields}>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: on ? 12 : 0 }}>
        <ChoiceChip label="Etkinliksiz" on={!on} onPress={() => setOn(false)} />
        <ChoiceChip label="Etkinlik ekle" note="tarih, saat, yer" on={on} onPress={() => setOn(true)} />
      </View>
      {on ? (
        <>
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 150 }}>
              <Field
                label="Tarih (GG.AA.YYYY)"
                value={date}
                onChangeText={(t) => setDate(maskBirthDate(t))}
                keyboardType="number-pad"
                placeholder="02.10.2026"
                error={date.length === 10 && !iso ? 'Tarih ya da saat geçersiz.' : undefined}
              />
            </View>
            <View style={{ width: 120 }}>
              <Field label="Saat" value={time} onChangeText={(t) => setTime(maskTime(t))} keyboardType="number-pad" placeholder="20:00" />
            </View>
          </View>
          <Kicker style={{ marginBottom: 6 }}>Süre</Kicker>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {DURATIONS.map((m) => (
              <ChoiceChip key={m} label={m % 60 ? `${m} dk` : `${m / 60} saat`} on={minutes === m} onPress={() => setMinutes(m)} />
            ))}
          </View>
          <Kicker style={{ marginBottom: 6 }}>Yer</Kicker>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {VENUES.map((v) => (
              <ChoiceChip key={v.value} label={v.label} note={v.note} on={venue === v.value} onPress={() => setVenue(v.value)} />
            ))}
          </View>
          {venue !== 'SALON' ? (
            <Field
              label={venue === 'ADRES' ? 'Adres' : 'Bağlantı ya da toplantı bilgisi'}
              value={text}
              onChangeText={setText}
              placeholder={venue === 'ADRES' ? 'Moda Sahnesi, Kadıköy' : 'Bağlantı buluşmadan önce konuya yazılır'}
            />
          ) : (
            <Muted style={{ fontSize: 13, marginBottom: 8 }}>
              Salon Genel kapsama ait bir kaynaktır: öneri onu etiketler, bu yüzden yalnızca Genel kapsamla
              açılabilir. Aynı saatte salonda planlı bir etkinlik varsa öneri açılmaz.
            </Muted>
          )}
          <Muted style={{ fontSize: 13 }}>
            Etkinlik, önerinin karara bağlanabileceği en erken andan (sessiz onay süresi) sonra olmalı. Konu kabul
            edilince takvime yazılır; etkinlikten sonra katılanlar rapor ve fotoğraf ekler.
          </Muted>
        </>
      ) : null}
    </View>
  );
}

const st = StyleSheet.create({
  leaf: {
    width: 104,
    borderWidth: 1.5,
    borderColor: paper.ink,
    backgroundColor: paper.sheet,
    alignItems: 'center',
    paddingBottom: 6,
  },
  leafSmall: { width: 78 },
  leafMonth: {
    alignSelf: 'stretch',
    textAlign: 'center',
    backgroundColor: paper.seal,
    color: paper.sheet,
    fontFamily: fonts.monoBold,
    fontSize: 12,
    letterSpacing: 2,
    paddingVertical: 2,
  },
  leafDay: { fontFamily: fonts.serifDisplay, fontSize: 40, lineHeight: 46, color: paper.ink },
  leafWeekday: { fontFamily: fonts.mono, fontSize: 12, color: paper.inkSoft, textAlign: 'center' },
  row: {
    flexDirection: 'row',
    gap: 14,
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
  },
  rowTitle: { fontFamily: fonts.serifMedium, fontSize: 19, lineHeight: 25, color: paper.ink },
  rowVenue: { fontFamily: fonts.serifItalic, fontSize: 15, color: paper.inkSoft },
  rowMeta: { fontFamily: fonts.mono, fontSize: 12, color: paper.muted },
  box: { borderWidth: 1, borderColor: paper.ink, padding: 12, gap: 8, marginTop: 14, backgroundColor: paper.sheet },
  boxVenue: { fontFamily: fonts.serifMedium, fontSize: 16, color: paper.ink },
  boxLink: { fontFamily: fonts.monoBold, fontSize: 12, color: paper.seal, textDecorationLine: 'underline' },
  fields: { borderLeftWidth: 2, borderLeftColor: paper.seal, paddingLeft: 12, marginBottom: 16 },
});
