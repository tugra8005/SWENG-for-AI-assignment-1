import { Platform, StyleSheet, Text, View } from 'react-native';

import { API_URL } from '@/api/client';
import { EventRow, type EventSummary } from '@/components/event';
import { Button, Columns, ErrorNotice, Kicker, Loading, Muted, Page, PageHead, Section, useWide } from '@/components/paper';
import { fmtMonthYear } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Listing = { upcoming: EventSummary[]; past: EventSummary[] };

/** Ay başlıklı ajanda: aynı aydaki etkinlikler bir başlığın altında. */
function Agenda({ items, empty }: { items: EventSummary[]; empty: string }) {
  if (!items.length) return <Muted style={{ marginTop: 10 }}>{empty}</Muted>;
  const groups: { month: string; items: EventSummary[] }[] = [];
  for (const e of items) {
    const month = fmtMonthYear(e.starts_at);
    if (groups.at(-1)?.month !== month) groups.push({ month, items: [] });
    groups.at(-1)!.items.push(e);
  }
  return (
    <View>
      {groups.map((g) => (
        <View key={g.month} style={{ marginTop: 12 }}>
          <Text style={st.month}>{g.month}</Text>
          {g.items.map((e) => <EventRow key={e.id} e={e} />)}
        </View>
      ))}
    </View>
  );
}

function Subscribe() {
  if (Platform.OS !== 'web') return null;
  return (
    <View style={{ gap: 6, alignItems: 'flex-start' }}>
      <Button
        label="Takvime abone ol (.ics)"
        variant="secondary"
        small
        onPress={() => {
          window.location.href = `${API_URL}/calendar.ics`;
        }}
      />
      <Muted style={{ fontSize: 13 }}>Yaklaşan etkinlikler telefonunuzun ya da e-postanızın takvimine eklenir.</Muted>
    </View>
  );
}

export default function Calendar() {
  const wide = useWide();
  const res = useApi<Listing>('/calendar', 60_000);
  const d = res.data;
  const head = (
    <PageHead kicker="Takvim" title="Meşveret Takvimi">
      <Muted>
        Takvime giden bir konu kabul edilince etkinliği buraya yazılır. Etkinlikten önce “Geliyorum” diyebilir,
        sonra rapor ve fotoğraf ekleyebilirsiniz. Ortak salonun kullanımına Genel kapsam karar verir.
      </Muted>
    </PageHead>
  );
  if (!d) return <Page>{head}{res.error ? <ErrorNotice error={res.error} /> : <Loading />}</Page>;
  const upcoming = (
    <Section title="Yaklaşan" aside={<Kicker>{d.upcoming.length} etkinlik</Kicker>}>
      <Agenda items={d.upcoming} empty="Takvimde yaklaşan etkinlik yok. Takvime giden bir konu önerin." />
    </Section>
  );
  const past = (
    <Section title="Geçmiş" aside={<Kicker>raporlar ve fotoğraflar</Kicker>}>
      <Agenda items={d.past} empty="Henüz gerçekleşmiş etkinlik yok." />
    </Section>
  );
  return (
    <Page>
      {head}
      {wide ? (
        <Columns main={<>{upcoming}{past}</>} side={<View style={{ marginTop: 22 }}><Subscribe /></View>} />
      ) : (
        <>
          <Subscribe />
          {upcoming}
          {past}
        </>
      )}
    </Page>
  );
}

const st = StyleSheet.create({
  month: {
    fontFamily: fonts.monoBold,
    fontSize: 12,
    letterSpacing: 2,
    color: paper.seal,
    textTransform: 'uppercase',
    borderBottomWidth: 2,
    borderBottomColor: paper.ink,
    paddingBottom: 4,
  },
});
