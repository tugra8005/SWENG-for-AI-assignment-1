import { Link, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';

import { api, API_URL } from '@/api/client';
import { attendeeLine, DateBlock, EVENT_STATUS, type EventSummary } from '@/components/event';
import { ImageAttach, PictureSet, type MediaItem } from '@/components/media';
import {
  Body,
  Button,
  Columns,
  ErrorNotice,
  Field,
  Kicker,
  Loading,
  Muted,
  Page,
  Seal,
  Section,
  useWide,
} from '@/components/paper';
import { ShareLink } from '@/components/share';
import { useAuth } from '@/lib/auth';
import { fmtDateTime, fmtLong, fmtTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Report = {
  id: number;
  author: string;
  text: string;
  headcount: number | null;
  created_at: string;
  ledger_hash: string | null;
  media: MediaItem[];
};

type EventView = EventSummary & {
  topic: { id: number; title: string; participants: number };
  proposal_id: number;
  ledger_hash: string | null;
  attendee_names: string[];
  reports: Report[];
  viewer: {
    attending: boolean;
    can_attend: boolean;
    attend_refusal: string | null;
    can_report: boolean;
    report_refusal: string | null;
  };
};

function ReportForm({ eventId, onDone }: { eventId: number; onDone: () => void }) {
  const [text, setText] = useState('');
  const [count, setCount] = useState('');
  const [photos, setPhotos] = useState<MediaItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const submit = async () => {
    setError(null);
    try {
      await api(`/events/${eventId}/reports`, {
        method: 'POST',
        body: { text, headcount: count ? Number(count) : null, media_ids: photos.map((p) => p.id) },
      });
      onDone();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.form}>
      <Kicker style={{ color: paper.seal, marginBottom: 8 }}>Etkinlik raporu yaz</Kicker>
      <Field label="Ne oldu?" value={text} onChangeText={setText} multiline placeholder="Kaç kişi geldi, ne konuşuldu, bir sonraki buluşma…" />
      <Field
        label="Kaç kişi vardı? (isteğe bağlı)"
        value={count}
        onChangeText={(t) => setCount(t.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad"
      />
      <ImageAttach value={photos} onChange={setPhotos} max={4} label="Fotoğraf ekle" />
      <ErrorNotice error={error} />
      <Button label="Raporu mühürle" onPress={submit} disabled={text.trim().length < 10} />
    </View>
  );
}

export default function EventPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const wide = useWide();
  const res = useApi<EventView>(`/events/${id}`);
  const [error, setError] = useState<unknown>(null);
  const e = res.data;
  if (!e) return <Page reading>{res.error ? <ErrorNotice error={res.error} /> : <Loading />}</Page>;

  const attend = async (coming: boolean) => {
    setError(null);
    try {
      await api(`/events/${e.id}/attendance`, { method: 'PUT', body: { coming } });
      await res.reload();
    } catch (err) {
      setError(err);
    }
  };

  const head = (
    <View style={{ gap: 12 }}>
      <Kicker>
        <Link href={`/konu/${e.topic.id}`} style={{ textDecorationLine: 'underline' }}>
          Konu №{e.topic.id} · {e.topic.title}
        </Link>
      </Kicker>
      <View style={{ flexDirection: 'row', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
        <DateBlock iso={e.starts_at} />
        <View style={{ flex: 1, minWidth: 220, gap: 6 }}>
          <Text style={st.title}>{e.title}</Text>
          <Text style={st.when}>
            {fmtLong(new Date(e.starts_at))} · {fmtTime(e.starts_at)}–{fmtTime(e.ends_at)}
          </Text>
          <Text style={st.venue}>
            {e.venue.kind === 'CEVRIMICI' ? 'Çevrim içi · ' : ''}
            {e.venue.text}
          </Text>
          <Text style={[st.status, e.status === 'SURUYOR' && { color: paper.seal }]}>{EVENT_STATUS[e.status]}</Text>
        </View>
      </View>
    </View>
  );

  const rsvp = (
    <View style={st.rsvp}>
      <Kicker>{attendeeLine(e) ?? 'Henüz kimse katılımını bildirmedi'}</Kicker>
      {e.attendee_names.length ? <Body style={{ fontSize: 15 }}>{e.attendee_names.join(', ')}</Body> : null}
      {me && e.viewer.can_attend ? (
        <Button
          label={e.viewer.attending ? 'Gelmeyeceğim' : 'Geliyorum'}
          variant={e.viewer.attending ? 'secondary' : 'primary'}
          onPress={() => attend(!e.viewer.attending)}
        />
      ) : (
        <Muted style={{ fontSize: 14 }}>{e.viewer.attend_refusal}</Muted>
      )}
      <ErrorNotice error={error} />
      <View style={{ flexDirection: 'row', gap: 14, flexWrap: 'wrap', marginTop: 4 }}>
        {Platform.OS === 'web' ? (
          <Button
            label="Takvime ekle (.ics)"
            variant="quiet"
            onPress={() => {
              window.location.href = `${API_URL}/events/${e.id}/ics`;
            }}
          />
        ) : null}
        <ShareLink path={`/etkinlik/${e.id}`} title={e.title} />
      </View>
      <View style={{ marginTop: 6 }}>
        <Seal hash={e.ledger_hash} label="etkinlik" />
      </View>
    </View>
  );

  const reports = (
    <Section title="Raporlar" aside={<Kicker>{e.reports.length ? `${e.reports.length} rapor` : 'etkinlikten sonra'}</Kicker>}>
      {e.reports.map((r) => (
        <View key={r.id} style={st.report}>
          <Muted style={{ fontSize: 13 }}>
            {r.author} · {fmtDateTime(r.created_at)}
            {r.headcount ? ` · ${r.headcount} kişi` : ''}
          </Muted>
          <Body>{r.text}</Body>
          <PictureSet items={r.media} />
          <Seal hash={r.ledger_hash} label="rapor" />
        </View>
      ))}
      {e.viewer.can_report ? (
        <ReportForm eventId={e.id} onDone={res.reload} />
      ) : e.reports.length === 0 || me ? (
        <Muted style={{ marginTop: 10, fontSize: 14 }}>{e.viewer.report_refusal}</Muted>
      ) : null}
    </Section>
  );

  if (wide) {
    return (
      <Page>
        <Columns main={<>{head}{reports}</>} side={rsvp} stickySide />
      </Page>
    );
  }
  return (
    <Page reading>
      {head}
      {rsvp}
      {reports}
    </Page>
  );
}

const st = StyleSheet.create({
  title: { fontFamily: fonts.serifDisplay, fontSize: 34, lineHeight: 40, color: paper.ink },
  when: { fontFamily: fonts.serifMedium, fontSize: 17, color: paper.ink },
  venue: { fontFamily: fonts.serifItalic, fontSize: 16, color: paper.inkSoft },
  status: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.5, color: paper.muted, textTransform: 'uppercase' },
  rsvp: { gap: 10, marginTop: 18, padding: 14, borderWidth: 1, borderColor: paper.ink, backgroundColor: paper.sheet },
  report: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 6 },
  form: { marginTop: 16, padding: 14, borderWidth: 1, borderColor: paper.hairline, borderStyle: 'dashed' },
});
