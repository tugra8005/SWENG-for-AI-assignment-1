import { Image } from 'expo-image';
import { Link, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { ImageAttach, PrintImage, type MediaItem } from '@/components/media';
import {
  Body,
  Button,
  Choice,
  ErrorNotice,
  Field,
  Kicker,
  Loading,
  Muted,
  Page,
  Section,
  Seal,
} from '@/components/paper';
import { STATUS_TEXT } from '@/components/petition';
import { ShareLink } from '@/components/share';
import { maskBirthDate } from '@/lib/birth-date';
import { useAuth } from '@/lib/auth';
import { useClock } from '@/lib/clock';
import { fmtDate, fmtDateNumeric, fmtDateTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

const sealMark = require('@/assets/images/seal-mark.png');

type Recipient = {
  id: string;
  name: string;
  status: 'YANITLANDI' | 'BEKLIYOR' | 'SURE_DOLDU';
  reply?: {
    id: number;
    text: string;
    replied_on: string;
    reference: string | null;
    entered_by: string;
    entered_at: string;
    ledger_hash: string | null;
    media: MediaItem[];
  };
};

/** Yönelme eki (büyük harf): "Belediyesi" → "NE", "Bakanlığı" → "NA" (son ünlüye göre, kaynaştırma n). */
function dativeSuffix(name: string): string {
  const vowels = name.toLocaleLowerCase('tr-TR').match(/[aıoueiöü]/g);
  const last = vowels?.at(-1) ?? 'a';
  return 'eiöü'.includes(last) ? 'NE' : 'NA';
}

/** "GG.AA.YYYY" → "YYYY-AA-GG"; geçersizse null. */
function isoOf(text: string): string | null {
  const m = text.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (!m) return null;
  const d = new Date(`${m[3]}-${m[2]}-${m[1]}T12:00:00Z`);
  return Number.isNaN(d.getTime()) || d.getUTCDate() !== Number(m[1]) ? null : `${m[3]}-${m[2]}-${m[1]}`;
}

function ReplyForm({ petitionId, pending, onDone }: { petitionId: number; pending: Recipient[]; onDone: () => void }) {
  const { now } = useClock();
  const [who, setWho] = useState<string | null>(pending.length === 1 ? pending[0].id : null);
  const [date, setDate] = useState(fmtDateNumeric(new Date(now()).toISOString()));
  const [reference, setReference] = useState('');
  const [text, setText] = useState('');
  const [scan, setScan] = useState<MediaItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const iso = isoOf(date);
  const submit = async () => {
    setError(null);
    try {
      await api(`/petitions/${petitionId}/replies`, {
        method: 'POST',
        body: { recipient_id: who, text, replied_on: iso, reference: reference || null, media_id: scan[0]?.id ?? null },
      });
      onDone();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.form}>
      <Kicker style={{ color: paper.seal, marginBottom: 8 }}>Kurumun yanıtını işle</Kicker>
      <Muted style={{ fontSize: 14, marginBottom: 12 }}>
        Yanıtı kurum değil, konunun bir katılımcısı olarak siz işliyorsunuz. Defter yanıtı kimin
        işlediğini kaydeder; yazının aslını taranmış görüntüsüyle eklemeniz önerilir.
      </Muted>
      {pending.length > 1 ? (
        <Choice label="Yanıt veren kurum" value={who} options={pending.map((r) => ({ value: r.id, label: r.name }))} onChange={setWho} />
      ) : null}
      <Field
        label="Yazının tarihi (GG.AA.YYYY)"
        value={date}
        onChangeText={(t) => setDate(maskBirthDate(t))}
        keyboardType="number-pad"
        error={date.length === 10 && !iso ? 'Tarih geçersiz.' : undefined}
      />
      <Field label="Yazının sayısı (isteğe bağlı)" value={reference} onChangeText={setReference} placeholder="Örn. E-34990-120.01-1234" />
      <Field label="Yanıtın metni" value={text} onChangeText={setText} multiline />
      <ImageAttach value={scan} onChange={setScan} max={1} label="Taranmış yazıyı ekle" />
      <ErrorNotice error={error} />
      <Button label="Yanıtı mühürle" onPress={submit} disabled={!who || !iso || !text.trim()} />
    </View>
  );
}

/** Web'de yazdırılırken yalnızca yazı (antet, metin, imza) kâğıda çıkar; site çerçevesi gizlenir. */
const printable = Platform.OS === 'web' ? ({ dataSet: { print: 'letter' } } as object) : {};

function PrintButton() {
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const style = document.createElement('style');
    style.textContent = `@media print {
      body * { visibility: hidden !important; }
      [data-print="letter"], [data-print="letter"] * { visibility: visible !important; }
      [data-print="letter"] { position: absolute; left: 0; top: 0; width: 100%; border: none !important; }
    }`;
    document.head.appendChild(style);
    return () => style.remove();
  }, []);
  if (Platform.OS !== 'web') return null;
  return <Button label="Yazdır" variant="quiet" onPress={() => window.print()} />;
}

export default function PetitionPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const res = useApi<any>(`/petitions/${id}`);
  const d = res.data;
  if (!d) {
    return <Page reading>{res.error ? <ErrorNotice error={res.error} /> : <Loading />}</Page>;
  }
  const recipients: Recipient[] = d.recipients;
  const pending = recipients.filter((r) => r.status !== 'YANITLANDI');
  const karar = d.kind === 'KARAR';
  return (
    <Page reading>
      <Kicker>
        <Link href={`/konu/${d.topic.id}`} style={{ textDecorationLine: 'underline' }}>Konu №{d.topic.id} · {d.topic.title}</Link>
      </Kicker>

      <View style={st.tools}>
        <PrintButton />
        <ShareLink path={`/dilekce/${d.id}`} title={`${d.number} · ${d.subject}`} />
      </View>

      <View style={st.letter} accessibilityLabel={`${d.number} sayılı dilekçe`} {...printable}>
        <View style={st.letterHead}>
          <Image source={sealMark} style={st.seal} accessibilityLabel="Meşveret mührü" />
          <View style={{ flex: 1 }}>
            <Text style={st.org}>MEŞVERET</Text>
            <Text style={st.orgSub}>oylamayla yönetilen topluluk · {d.topic.area_name}</Text>
          </View>
          <View style={st.refBox}>
            <Text style={st.ref}>Sayı: {d.number}</Text>
            <Text style={st.ref}>Tarih: {fmtDateNumeric(d.sent_at)}</Text>
          </View>
        </View>
        <Text style={st.subject}>
          <Text style={st.label}>Konu: </Text>
          {d.subject}
        </Text>
        <View style={st.toBlock}>
          {recipients.map((r) => (
            <Text key={r.id} style={st.to}>
              {r.name.toLocaleUpperCase('tr-TR')}
              {recipients.length === 1 ? dativeSuffix(r.name) : ''}
            </Text>
          ))}
          {recipients.length > 1 ? <Text style={st.distribution}>(dağıtım: {recipients.length} kurum)</Text> : null}
        </View>
        <Body style={st.intro}>
          {karar
            ? `Daha önce dilekçeyle size ilettiğimiz "${d.topic.title}" konusunda topluluğumuz aşağıdaki kararı almıştır.`
            : `Topluluğumuz ${d.scope} kapsamında yaptığı oylamayla aşağıdaki talebi size iletmeyi kararlaştırmıştır.`}
        </Body>
        <Text style={st.body}>{d.text}</Text>
        <Body style={st.intro}>
          Gereğini bilgilerinize arz ederiz. 3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun
          uyarınca {d.reply_days} gün içinde yanıt beklenmektedir.
        </Body>
        <View style={st.signature}>
          <Text style={st.signLabel}>Meşveret adına</Text>
          <Text style={st.signText}>{d.signature}</Text>
          <Text style={st.signMeta}>öneren: {d.proposer} · konu katılımcısı: {d.topic.participants}</Text>
          <Seal hash={d.ledger_hash} label="dilekçe" />
        </View>
      </View>

      <Section title="Yanıtlar" aside={<Kicker>yasal süre {fmtDate(d.due_at)}</Kicker>}>
        {recipients.map((r) => (
          <View key={r.id} style={st.reply}>
            <View style={st.replyHead}>
              <Text style={st.replyName}>{r.name}</Text>
              <Text style={[st.status, r.status === 'YANITLANDI' && { color: paper.ok }, r.status === 'SURE_DOLDU' && { color: paper.seal }]}>
                {STATUS_TEXT[r.status]}
              </Text>
            </View>
            {r.reply ? (
              <>
                <Muted style={{ fontSize: 13 }}>
                  yazı tarihi {fmtDate(r.reply.replied_on)}
                  {r.reply.reference ? ` · sayı ${r.reply.reference}` : ''} · işleyen {r.reply.entered_by} ({fmtDateTime(r.reply.entered_at)})
                </Muted>
                <Body>{r.reply.text}</Body>
                {r.reply.media.map((m) => (
                  <View key={m.id} style={{ marginTop: 8 }}>
                    <PrintImage m={m} maxHeight={520} />
                  </View>
                ))}
                <Seal hash={r.reply.ledger_hash} label="yanıt" />
              </>
            ) : r.status === 'SURE_DOLDU' ? (
              <Muted style={{ fontSize: 14 }}>{d.reply_days} günlük yasal süre içinde yanıt işlenmedi.</Muted>
            ) : null}
          </View>
        ))}
        {pending.length && me && d.viewer.can_reply ? (
          <ReplyForm petitionId={d.id} pending={pending} onDone={res.reload} />
        ) : pending.length && me ? (
          <Muted style={{ marginTop: 10, fontSize: 14 }}>{d.viewer.reply_refusal}</Muted>
        ) : null}
      </Section>
    </Page>
  );
}

const st = StyleSheet.create({
  tools: { flexDirection: 'row', gap: 16, marginTop: 10, flexWrap: 'wrap' },
  letter: {
    marginTop: 10,
    backgroundColor: paper.sheet,
    borderWidth: 1,
    borderColor: paper.ink,
    padding: 22,
    gap: 14,
  },
  letterHead: { flexDirection: 'row', gap: 12, alignItems: 'center', borderBottomWidth: 2, borderBottomColor: paper.ink, paddingBottom: 12, flexWrap: 'wrap' },
  seal: { width: 54, height: 54 },
  org: { fontFamily: fonts.serifDisplay, fontSize: 24, letterSpacing: 3, color: paper.ink },
  orgSub: { fontFamily: fonts.serifItalic, fontSize: 13, color: paper.inkSoft },
  refBox: { gap: 2 },
  ref: { fontFamily: fonts.mono, fontSize: 12, color: paper.ink },
  subject: { fontFamily: fonts.serifMedium, fontSize: 17, lineHeight: 24, color: paper.ink },
  label: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1 },
  toBlock: { alignItems: 'center', gap: 2, marginVertical: 6 },
  to: { fontFamily: fonts.serifBold, fontSize: 15, letterSpacing: 1, color: paper.ink, textAlign: 'center' },
  distribution: { fontFamily: fonts.mono, fontSize: 11, color: paper.muted },
  intro: { fontSize: 16, lineHeight: 24 },
  body: { fontFamily: fonts.serif, fontSize: 18, lineHeight: 28, color: paper.ink, paddingLeft: 14, borderLeftWidth: 2, borderLeftColor: paper.seal },
  signature: { alignSelf: 'flex-end', alignItems: 'flex-end', gap: 4, marginTop: 6, maxWidth: 420 },
  signLabel: { fontFamily: fonts.serifBold, fontSize: 15, color: paper.ink },
  signText: { fontFamily: fonts.serifItalic, fontSize: 14, lineHeight: 20, color: paper.inkSoft, textAlign: 'right' },
  signMeta: { fontFamily: fonts.mono, fontSize: 11, color: paper.muted },
  reply: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 6 },
  replyHead: { flexDirection: 'row', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' },
  replyName: { fontFamily: fonts.serifBold, fontSize: 17, color: paper.ink },
  status: { fontFamily: fonts.serifItalic, fontSize: 15, color: paper.inkSoft },
  form: { marginTop: 16, padding: 14, borderWidth: 1, borderColor: paper.hairline, borderStyle: 'dashed' },
});
