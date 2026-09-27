import { Link, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  CensorStrip,
  ErrorNotice,
  Field,
  H1,
  Kicker,
  Loading,
  Muted,
  Page,
  PressLink,
  Rule,
  Seal,
  Section,
  Tag,
} from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDateTime, STATUS_LABELS, TYPE_LABELS } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Msg = {
  id: number;
  author?: string;
  text?: string;
  created_at?: string;
  edited_at?: string | null;
  version?: number;
  reply_to?: number | null;
  ledger_hash?: string | null;
  deleted_by_proposal_id?: number;
};

function propose(params: Record<string, string | number>) {
  router.push({ pathname: '/oneri/yeni', params: params as any });
}

function Message({ m, topic, onChanged }: { m: Msg; topic: any; onChanged: () => void }) {
  const { me } = useAuth();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.text ?? '');
  const [error, setError] = useState<unknown>(null);
  if (m.deleted_by_proposal_id) {
    return <CensorStrip proposalId={m.deleted_by_proposal_id} hash={m.ledger_hash} />;
  }
  const mine = me?.nickname === m.author;
  const open = topic.status === 'OPEN';
  const save = async () => {
    setError(null);
    try {
      await api(`/messages/${m.id}`, { method: 'PUT', body: { text: draft } });
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.msg} nativeID={`m${m.id}`}>
      <View style={st.msgHead}>
        <Link href={`/profil/${encodeURIComponent(m.author ?? '')}`} style={st.author}>
          {m.author}
        </Link>
        <Text style={st.meta}>#{m.id} · {fmtDateTime(m.created_at)}</Text>
        {m.reply_to ? <Text style={st.meta}>↳ #{m.reply_to}&apos;e yanıt</Text> : null}
        {m.edited_at ? (
          <Link href={`/mesaj/${m.id}`} style={[st.meta, { textDecorationLine: 'underline' }]}>
            düzenlendi (sürüm {m.version})
          </Link>
        ) : null}
      </View>
      {editing ? (
        <View>
          <Field label="Yeni sürüm" value={draft} onChangeText={setDraft} multiline />
          <ErrorNotice error={error} />
          <View style={st.actions}>
            <Button label="Sürümü kaydet" small onPress={save} />
            <Button label="Vazgeç" variant="quiet" onPress={() => setEditing(false)} />
          </View>
        </View>
      ) : (
        <Body>{m.text}</Body>
      )}
      <View style={[st.actions, { marginTop: 8 }]}>
        <Seal hash={m.ledger_hash} />
        {me && open && !editing ? (
          <>
            <Button label="Yanıtla" variant="quiet" onPress={() => router.setParams({ reply: String(m.id) })} />
            {mine ? (
              <Button label="Düzenle" variant="quiet" onPress={() => setEditing(true)} />
            ) : (
              <Button
                label="Düzenleme öner"
                variant="quiet"
                onPress={() => propose({ type: 'DUZENLEME', message: m.id })}
              />
            )}
            <Button label="Silme öner" variant="quiet" onPress={() => propose({ type: 'SILME', message: m.id })} />
          </>
        ) : null}
      </View>
    </View>
  );
}

function Decision({ d, onChanged }: { d: any; onChanged: () => void }) {
  const { me } = useAuth();
  const [text, setText] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState(false);
  const submit = async () => {
    setError(null);
    try {
      await api(`/decisions/${d.id}/dissents`, { method: 'POST', body: { text } });
      setOpen(false);
      setText('');
      onChanged();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.decision}>
      <Kicker style={{ color: paper.seal }}>Karar · №{d.proposal_id} numaralı kapanış oylaması</Kicker>
      <Text style={st.decisionText}>{d.text}</Text>
      <View style={st.actions}>
        <Seal hash={d.ledger_hash} label="karar" />
        <Muted style={{ fontSize: 13 }}>{fmtDateTime(d.created_at)}</Muted>
      </View>
      {d.dissents.length ? <Rule faint /> : null}
      {d.dissents.map((x: any) => (
        <View key={x.id} style={{ marginTop: 6 }}>
          <Kicker>Şerh — {x.author}</Kicker>
          <Body style={{ fontFamily: fonts.serifItalic }}>{x.text}</Body>
          <Seal hash={x.ledger_hash} label="şerh" />
        </View>
      ))}
      {me ? (
        open ? (
          <View style={{ marginTop: 12 }}>
            <Field
              label="Şerh metni"
              value={text}
              onChangeText={setText}
              multiline
              hint="Şerh silinemez ve düzenlenemez; kaybeden metnin sahibi ya da destekçisi ekleyebilir."
            />
            <ErrorNotice error={error} />
            <Button label="Şerhi mühürle" onPress={submit} disabled={!text.trim()} />
          </View>
        ) : (
          <View style={{ marginTop: 10 }}>
            <Button label="Şerh ekle" variant="quiet" onPress={() => setOpen(true)} />
          </View>
        )
      ) : null}
    </View>
  );
}

export default function TopicPage() {
  const { id, reply } = useLocalSearchParams<{ id: string; reply?: string }>();
  const { me } = useAuth();
  const topic = useApi<any>(`/topics/${id}`);
  const [text, setText] = useState('');
  const [error, setError] = useState<unknown>(null);
  const t = topic.data;

  if (!t) {
    return (
      <Page>
        {topic.error ? <ErrorNotice error={topic.error} /> : <Loading />}
      </Page>
    );
  }
  if (t.deleted_by_proposal_id) {
    return (
      <Page>
        <Kicker>Konu №{t.id}</Kicker>
        <CensorStrip proposalId={t.deleted_by_proposal_id} />
      </Page>
    );
  }

  const post = async () => {
    setError(null);
    try {
      await api(`/topics/${t.id}/messages`, {
        method: 'POST',
        body: { text, reply_to: reply ? Number(reply) : null },
      });
      setText('');
      router.setParams({ reply: undefined });
      topic.reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <View style={st.crumbs}>
        <Link href={`/alan/${t.area_id}`} style={st.crumb}>§ {t.area_name}</Link>
        {t.parent ? (
          <Link href={`/konu/${t.parent.id}`} style={st.crumb}>› {t.parent.title}</Link>
        ) : null}
      </View>
      <Kicker>
        Konu №{t.id} · sahibi: {t.owner_scope} · {t.status === 'CLOSED' ? 'karara bağlandı' : 'açık'}
      </Kicker>
      <H1 style={{ marginTop: 4 }}>{t.title}</H1>
      <Muted>
        {t.author} tarafından önerildi · {fmtDateTime(t.created_at)}
      </Muted>
      <Rule double />

      {t.opening ? (
        <View>
          <Text style={st.opening}>{t.opening.text}</Text>
          <View style={st.actions}>
            <Seal hash={t.opening.ledger_hash} label="açılış" />
            {t.opening.edited_at ? (
              <Link href={`/mesaj/${t.opening.id}`} style={[st.meta, { textDecorationLine: 'underline' }]}>
                sürüm geçmişi
              </Link>
            ) : null}
            {me && t.status === 'OPEN' ? (
              <Button
                label="Açılış metnine düzenleme öner"
                variant="quiet"
                onPress={() => propose({ type: 'DUZENLEME', message: t.opening.id })}
              />
            ) : null}
          </View>
        </View>
      ) : null}

      {t.decision ? <Decision d={t.decision} onChanged={topic.reload} /> : null}

      {me ? (
        <View style={[st.actions, { marginTop: 18 }]}>
          {t.status === 'OPEN' ? (
            <>
              <Button label="Alt konu öner" variant="secondary" small onPress={() => propose({ type: 'ALT_KONU', parent: t.id })} />
              {t.viewer.is_participant ? (
                <Button label="Kapanış öner" variant="secondary" small onPress={() => propose({ type: 'KAPANIS', topic: t.id })} />
              ) : null}
            </>
          ) : (
            <Button label="Yeniden açma öner" variant="secondary" small onPress={() => propose({ type: 'KONU', reopen: t.id })} />
          )}
          <Button label="Konuyu silme öner" variant="quiet" onPress={() => propose({ type: 'SILME', topic: t.id })} />
        </View>
      ) : null}

      {t.proposals.length ? (
        <Section title="Bu konudaki açık öneriler">
          {t.proposals.map((p: any) => (
            <PressLink key={p.id} href={`/oneri/${p.id}`} style={st.related}>
              <Text style={st.relNo}>№{p.id}</Text>
              <Tag>{TYPE_LABELS[p.type]}</Tag>
              <Tag tone="seal">{STATUS_LABELS[p.status]}</Tag>
              <Text style={st.relTitle} numberOfLines={1}>{p.title}</Text>
            </PressLink>
          ))}
        </Section>
      ) : null}

      {t.subtopics.length ? (
        <Section title="Alt konular">
          {t.subtopics.map((s: any) =>
            s.deleted_by_proposal_id ? (
              <CensorStrip key={s.id} proposalId={s.deleted_by_proposal_id} />
            ) : (
              <PressLink key={s.id} href={`/konu/${s.id}`} style={st.related}>
                <Text style={st.relTitle}>└ {s.title}</Text>
                <Muted style={{ fontSize: 13 }}>{s.area_name}</Muted>
              </PressLink>
            ),
          )}
        </Section>
      ) : null}

      <Section title="Tartışma" aside={<Kicker>{t.messages.length} mesaj · oylamasız</Kicker>}>
        {t.messages.map((m: Msg) => (
          <Message key={m.id} m={m} topic={t} onChanged={topic.reload} />
        ))}
        {t.messages.length === 0 ? <Muted>Henüz mesaj yok.</Muted> : null}
        {me && t.status === 'OPEN' ? (
          <View style={{ marginTop: 18 }}>
            <Field
              label={reply ? `#${reply} numaralı mesaja yanıt` : 'Mesajınız'}
              value={text}
              onChangeText={setText}
              multiline
              hint="Mesajlar oylamasız yazılır; kendi mesajınızı sonradan düzenleyebilirsiniz, geçmiş herkese açık kalır."
            />
            <ErrorNotice error={error} />
            <View style={st.actions}>
              <Button label="Gönder" onPress={post} disabled={!text.trim()} />
              {reply ? <Button label="Yanıtı iptal et" variant="quiet" onPress={() => router.setParams({ reply: undefined })} /> : null}
            </View>
          </View>
        ) : null}
        {t.status !== 'OPEN' ? <Muted style={{ marginTop: 12 }}>Konu karara bağlandı; tartışma salt okunur.</Muted> : null}
        {!me ? <Muted style={{ marginTop: 12 }}>Yazmak için giriş yapın.</Muted> : null}
      </Section>
    </Page>
  );
}

const st = StyleSheet.create({
  crumbs: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 6 },
  crumb: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.inkSoft, letterSpacing: 0.6 },
  opening: { fontFamily: fonts.serif, fontSize: 20, lineHeight: 30, color: paper.ink, marginBottom: 10 },
  actions: { flexDirection: 'row', gap: 14, alignItems: 'center', flexWrap: 'wrap' },
  msg: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  msgHead: { flexDirection: 'row', gap: 10, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 4 },
  author: { fontFamily: fonts.serifBold, fontSize: 16, color: paper.ink },
  meta: { fontFamily: fonts.mono, fontSize: 11, color: paper.muted },
  decision: {
    marginTop: 22,
    borderWidth: 3,
    borderColor: paper.ink,
    borderStyle: 'solid',
    padding: 16,
    backgroundColor: paper.sheet,
    gap: 6,
  },
  decisionText: { fontFamily: fonts.serifMedium, fontSize: 22, lineHeight: 30, color: paper.ink },
  related: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
    flexWrap: 'wrap',
  },
  relNo: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.seal },
  relTitle: { fontFamily: fonts.serifMedium, fontSize: 16, color: paper.ink, flexShrink: 1 },
});
