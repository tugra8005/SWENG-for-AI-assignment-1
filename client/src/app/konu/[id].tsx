import { Link, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  CensorStrip,
  Choice,
  Columns,
  ErrorNotice,
  Field,
  InitialText,
  Kicker,
  Loading,
  Muted,
  Nick,
  Page,
  PressLink,
  Rule,
  Seal,
  Section,
  Tag,
  useWide,
  type DeletionBasis,
} from '@/components/paper';
import { maturityLine, NarrowingBox, ProposalTitle } from '@/components/proposal-title';
import { useAuth } from '@/lib/auth';
import { fmtDateAblative, fmtDateTime, fmtDayMonth, STATUS_LABELS, TYPE_LABELS, withDative } from '@/lib/format';
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
  deletion_basis?: DeletionBasis | null;
  pending_deletion?: Pending | null;
};

type Pending = { proposal_id: number; decides_at: string | null };

/** Aktif silme oylamasındaki içeriğin üstündeki küçük işaret: "№10 silme oylamasında · 4 Ekim". */
function PendingDeletion({ pending }: { pending?: Pending | null }) {
  if (!pending) return null;
  return (
    <Link href={`/oneri/${pending.proposal_id}`} style={st.pending}>
      №{pending.proposal_id} silme oylamasında{pending.decides_at ? ` · ${fmtDayMonth(pending.decides_at)}` : ''}
    </Link>
  );
}

/** İkincil eylemler "⋯" arkasında durur; silme istisnadır, arayüz de öyle gösterir. */
function MoreActions({ label, children }: { label: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginLeft: 'auto' }}>
      {open ? children : null}
      <Pressable
        onPress={() => setOpen(!open)}
        accessibilityRole="button"
        accessibilityLabel={label}
        aria-expanded={open}
        hitSlop={8}
      >
        <Text style={st.more}>{open ? '×' : '⋯'}</Text>
      </Pressable>
    </View>
  );
}

function propose(params: Record<string, string | number>) {
  router.push({ pathname: '/oneri/yeni', params: params as any });
}

function Message({ m, topic, onChanged }: { m: Msg; topic: any; onChanged: () => void }) {
  const { me } = useAuth();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.text ?? '');
  const [error, setError] = useState<unknown>(null);
  if (m.deleted_by_proposal_id) {
    return <CensorStrip proposalId={m.deleted_by_proposal_id} hash={m.ledger_hash} basis={m.deletion_basis} />;
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
      <PendingDeletion pending={m.pending_deletion} />
      <View style={st.msgHead}>
        <Link href={`/profil/${encodeURIComponent(m.author ?? '')}`} style={st.author}>
          {m.author}
        </Link>
        <Text style={st.meta}>#{m.id} · {fmtDateTime(m.created_at)}</Text>
        {m.reply_to ? <Text style={st.meta}>↳ #{withDative(m.reply_to)} yanıt</Text> : null}
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
            {mine ? <Button label="Düzenle" variant="quiet" onPress={() => setEditing(true)} /> : null}
            <MoreActions label={`#${m.id} numaralı mesaj için diğer eylemler`}>
              {mine ? null : (
                <Button
                  label="düzenleme öner"
                  variant="minor"
                  onPress={() => propose({ type: 'DUZENLEME', message: m.id })}
                />
              )}
              <Button label="silme öner" variant="minor" onPress={() => propose({ type: 'SILME', message: m.id })} />
            </MoreActions>
          </>
        ) : null}
      </View>
    </View>
  );
}

function Decision({ d, onChanged }: { d: any; onChanged: () => void }) {
  const { me } = useAuth();
  const [text, setText] = useState('');
  const [basis, setBasis] = useState<string>('');
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState(false);
  const options: any[] = d.viewer_dissent_options ?? [];
  const chosen = options.length === 1 ? String(options[0].id) : basis;
  const submit = async () => {
    setError(null);
    try {
      await api(`/decisions/${d.id}/dissents`, {
        method: 'POST',
        body: { text, closure_text_id: chosen ? Number(chosen) : null },
      });
      setOpen(false);
      setText('');
      onChanged();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <>
      <View style={st.decision}>
        <Kicker style={{ color: paper.seal }}>Karar · №{d.proposal_id} numaralı kapanış oylaması</Kicker>
        <Text style={st.decisionText}>{d.text}</Text>
        <View style={st.actions}>
          <Seal hash={d.ledger_hash} label="karar" />
          <Muted style={{ fontSize: 13 }}>{fmtDateTime(d.created_at)}</Muted>
        </View>
      </View>
      <Section title="Şerhler" aside={<Kicker>{d.dissents.length ? `${d.dissents.length} şerh` : 'kaybeden tarafın sözü'}</Kicker>}>
        <Muted style={{ fontSize: 14 }}>
          Kaybeden metinlerin sahipleri ve o metinlere onay verenler karara şerh düşebilir. Şerh silinemez,
          düzenlenemez ve deftere yazılır.
        </Muted>
        {d.dissents.map((x: any) => (
          <View key={x.id} style={st.dissent}>
            <Kicker>Şerh · <Nick>{x.author}</Nick></Kicker>
            {x.based_on ? (
              <Text style={st.dissentBasis}>
                Dayandığı metin: #{x.based_on.id} «{x.based_on.text}» · {x.based_on.author}
              </Text>
            ) : null}
            <Body style={{ fontFamily: fonts.serifItalic }}>{x.text}</Body>
            <View style={st.actions}>
              <Seal hash={x.ledger_hash} label="şerh" />
              <Muted style={{ fontSize: 13 }}>{fmtDateTime(x.created_at)}</Muted>
            </View>
          </View>
        ))}
        {!d.dissents.length ? <Muted style={{ fontSize: 14 }}>Henüz şerh yok.</Muted> : null}
        {me && d.viewer_can_dissent ? (
          open ? (
            <View style={{ marginTop: 12, gap: 6 }}>
              {options.length > 1 ? (
                <Choice
                  label="Dayandığı kaybeden metin"
                  value={basis}
                  options={options.map((o) => ({ value: String(o.id), label: `#${o.id} ${o.text}` }))}
                  onChange={setBasis}
                />
              ) : (
                <Text style={st.dissentBasis}>
                  Dayandığı metin: #{options[0]?.id} «{options[0]?.text}» · {options[0]?.author}
                </Text>
              )}
              <Field
                label="Şerh metni"
                value={text}
                onChangeText={setText}
                multiline
                hint="Şerh silinemez ve düzenlenemez."
              />
              <ErrorNotice error={error} />
              <Button label="Şerhi mühürle" onPress={submit} disabled={!text.trim() || !chosen} />
            </View>
          ) : (
            <View style={{ marginTop: 10 }}>
              <Button label="Şerh ekle" variant="secondary" small onPress={() => setOpen(true)} />
            </View>
          )
        ) : null}
      </Section>
    </>
  );
}

export default function TopicPage() {
  const { id, reply } = useLocalSearchParams<{ id: string; reply?: string }>();
  const { me } = useAuth();
  const topic = useApi<any>(`/topics/${id}`);
  const wide = useWide();
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
        <CensorStrip proposalId={t.deleted_by_proposal_id} basis={t.deletion_basis} />
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

  const header = (
    <>
      <View style={st.crumbs}>
        <Link href={`/alan/${t.area_id}`} style={st.crumb}>§ {t.area_name}</Link>
        {t.parent ? (
          <Link href={`/konu/${t.parent.id}`} style={st.crumb}>› {t.parent.title}</Link>
        ) : null}
      </View>
      <PendingDeletion pending={t.pending_deletion} />
      <Kicker>
        Konu №{t.id} · sahibi: {t.owner_scope} · {t.status === 'CLOSED' ? 'karara bağlandı' : 'açık'}
      </Kicker>
      <View style={{ marginTop: 4 }}>
        <ProposalTitle title={t.title} effective={t.effective_title} style={st.h1} heading />
      </View>
      <Muted>
        {t.author} önerdi · {fmtDateTime(t.proposed_at)} · kabul: {fmtDateTime(t.created_at)}
      </Muted>
      <Rule double />
    </>
  );
  const opening = (
    <>
      {t.narrowings?.map((n: any, i: number) => (
        <NarrowingBox key={i} message={n.message} share={n.share} total={n.total} />
      ))}
      {t.opening ? (
        <View>
          <InitialText text={t.opening.text} style={st.opening} />
          <View style={st.actions}>
            <Seal hash={t.opening.ledger_hash} label="açılış" />
            {t.opening.edited_at ? (
              <Link href={`/mesaj/${t.opening.id}`} style={[st.meta, { textDecorationLine: 'underline' }]}>
                sürüm geçmişi
              </Link>
            ) : null}
            {me && t.status === 'OPEN' ? (
              <MoreActions label="Açılış metni için diğer eylemler">
                <Button
                  label="açılış metnine düzenleme öner"
                  variant="minor"
                  onPress={() => propose({ type: 'DUZENLEME', message: t.opening.id })}
                />
              </MoreActions>
            ) : null}
          </View>
        </View>
      ) : null}
    </>
  );
  const decision = t.decision ? <Decision d={t.decision} onChanged={topic.reload} /> : null;
  const actions = (
    <>
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
            <View style={{ gap: 4 }}>
              <Button
                label="Yeniden açma öner"
                variant="secondary"
                small
                disabled={!t.can_reopen}
                onPress={() => propose({ type: 'KONU', reopen: t.id })}
              />
              {!t.can_reopen && t.reopen_after ? (
                <Muted style={{ fontSize: 13 }}>Karar {fmtDateAblative(t.reopen_after)} sonra yeniden açılabilir.</Muted>
              ) : null}
            </View>
          )}
          <MoreActions label="Konu için diğer eylemler">
            <Button label="konuyu silme öner" variant="minor" onPress={() => propose({ type: 'SILME', topic: t.id })} />
          </MoreActions>
        </View>
      ) : null}
      {t.proposals.length ? (
        <Section title="Bu konudaki açık öneriler">
          {t.proposals.map((p: any) => (
            <PressLink key={p.id} href={`/oneri/${p.id}`} style={st.related}>
              <Text style={st.relNo}>№{p.id}</Text>
              <Tag>{TYPE_LABELS[p.type]}</Tag>
              <Tag tone="seal">{STATUS_LABELS[p.status]}</Tag>
              <View style={{ flex: 1, minWidth: 180, gap: 2 }}>
                <ProposalTitle title={p.title} effective={p.effective_title} style={st.relTitle} />
                {maturityLine(p.maturity) ? <Text style={st.relMaturing}>{maturityLine(p.maturity)}</Text> : null}
              </View>
            </PressLink>
          ))}
        </Section>
      ) : null}
      {t.subtopics.length ? (
        <Section title="Alt konular">
          {t.subtopics.map((s: any) =>
            s.deleted_by_proposal_id ? (
              <CensorStrip key={s.id} proposalId={s.deleted_by_proposal_id} basis={s.deletion_basis} />
            ) : (
              <PressLink key={s.id} href={`/konu/${s.id}`} style={st.related}>
                <Text style={st.relTitle}>└ {s.effective_title ?? s.title}</Text>
                <Muted style={{ fontSize: 13 }}>{s.area_name}</Muted>
              </PressLink>
            ),
          )}
        </Section>
      ) : null}
    </>
  );
  const discussion = (
    <>
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
    </>
  );

  // Geniş ekran: tartışma ana sütunda; Karar, Şerhler, eylemler ve ilgili öneriler yan sütunda.
  if (wide) {
    return (
      <Page>
        {header}
        <Columns
          sideWidth={380}
          main={
            <>
              {opening}
              {discussion}
            </>
          }
          side={
            <>
              {decision}
              {actions}
            </>
          }
        />
      </Page>
    );
  }

  return (
    <Page>
      {header}
      {opening}
      {decision}
      {actions}
      {discussion}
    </Page>
  );
}

const st = StyleSheet.create({
  h1: { fontFamily: fonts.serifBold, fontSize: 30, lineHeight: 36, color: paper.ink },
  crumbs: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 6 },
  crumb: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.inkSoft, letterSpacing: 0.6 },
  opening: { fontFamily: fonts.serif, fontSize: 20, lineHeight: 30, color: paper.ink, marginBottom: 10, paddingTop: 10 },
  actions: { flexDirection: 'row', gap: 14, alignItems: 'center', flexWrap: 'wrap' },
  msg: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  msgHead: { flexDirection: 'row', gap: 10, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 4 },
  author: { fontFamily: fonts.serifBold, fontSize: 16, color: paper.ink },
  meta: { fontFamily: fonts.mono, fontSize: 11, color: paper.muted },
  more: { fontFamily: fonts.monoBold, fontSize: 16, lineHeight: 18, color: paper.muted, paddingHorizontal: 4 },
  pending: {
    alignSelf: 'flex-start',
    fontFamily: fonts.monoMedium,
    fontSize: 11,
    letterSpacing: 0.4,
    color: paper.seal,
    borderWidth: 1,
    borderColor: paper.seal,
    borderStyle: 'dashed',
    paddingHorizontal: 6,
    paddingVertical: 1,
    marginBottom: 6,
  },
  decision: {
    marginTop: 22,
    borderWidth: 3,
    borderColor: paper.ink,
    borderStyle: 'solid',
    padding: 16,
    backgroundColor: paper.sheet,
    gap: 6,
  },
  dissent: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
  dissentBasis: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, color: paper.inkSoft },
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
  relMaturing: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 17, color: paper.seal },
});
