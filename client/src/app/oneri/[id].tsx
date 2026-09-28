import { Link, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { DiffText } from '@/components/diff';
import {
  Body,
  Button,
  Countdown,
  ErrorNotice,
  Field,
  InfoNotice,
  Kicker,
  Loading,
  Mono,
  Muted,
  Page,
  Rule,
  Seal,
  Section,
  Tag,
} from '@/components/paper';
import { ProposalForm } from '@/components/proposal-form';
import { maturityDetail, maturityLine, NarrowingBox, ProposalTitle } from '@/components/proposal-title';
import { useAuth } from '@/lib/auth';
import { describeArticleValue, fmtDateTime, fmtNumber, fmtSession, STATUS_LABELS, TYPE_LABELS } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

function ObjectionMeter({ count, threshold }: { count: number; threshold: number }) {
  const cells = Array.from({ length: threshold }, (_, i) => i < count);
  return (
    <View style={{ flexDirection: 'row', gap: 4, alignItems: 'center' }} accessibilityLabel={`${count} itiraz, eşik ${threshold}`}>
      {cells.map((on, i) => (
        <View key={i} style={[st.cell, on && { backgroundColor: paper.seal }]} />
      ))}
      <Mono style={{ marginLeft: 8 }}>
        {count}/{threshold}
      </Mono>
    </View>
  );
}

function OracleOpinion({ text }: { text: string }) {
  return (
    <View style={st.oracle}>
      <Kicker style={{ color: paper.ink }}>Bilirkişi görüşü · Hâtif (kural tabanlı)</Kicker>
      {text.split('\n').map((line, i) => (
        <Text key={i} style={[st.oracleLine, line.startsWith('Etiket önerisi') && { fontFamily: fonts.monoBold }]}>
          {line}
        </Text>
      ))}
    </View>
  );
}

function Rival({ id, onDone }: { id: number; onDone: () => void }) {
  const [text, setText] = useState('');
  const [error, setError] = useState<unknown>(null);
  return (
    <View style={{ marginTop: 12 }}>
      <Field label="Rakip karar metni" value={text} onChangeText={setText} multiline />
      <ErrorNotice error={error} />
      <Button
        label="Rakip metni ekle"
        onPress={async () => {
          setError(null);
          try {
            await api(`/proposals/${id}/rivals`, { method: 'POST', body: { text } });
            setText('');
            onDone();
          } catch (e) {
            setError(e);
          }
        }}
        disabled={!text.trim()}
      />
    </View>
  );
}

function Result({ p }: { p: any }) {
  const r = p.result;
  if (!r) return null;
  return (
    <InfoNotice>
      <Kicker>Karar Saati #{p.session_id} sonucu</Kicker>
      {r.kind === 'approval' ? (
        <Body>
          {r.winner ? `Kazanan metin: #${r.winner}. ` : ''}
          {r.note}
        </Body>
      ) : (
        <Body>
          {r.yes} EVET · {r.no} HAYIR · {r.abstained} çekimser — {r.passed ? 'eşik aşıldı' : 'eşik aşılamadı'}
        </Body>
      )}
      <Link href={`/karar-saati/${p.session_id}`} style={[st.link, { marginTop: 4 }]}>
        Oyların açılışını izle →
      </Link>
    </InfoNotice>
  );
}

export default function ProposalPage() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const res = useApi<any>(`/proposals/${id}`);
  const [error, setError] = useState<unknown>(null);
  const p = res.data;

  if (!p) return <Page>{res.error ? <ErrorNotice error={res.error} /> : <Loading />}</Page>;

  const object = async () => {
    setError(null);
    try {
      await api(`/proposals/${p.id}/objections`, { method: 'POST' });
      res.reload();
    } catch (e) {
      setError(e);
    }
  };

  const isDraft = p.status === 'DRAFT';
  const lane = p.lane === 'FAST' ? 'Hızlı şerit' : 'Yavaş şerit';

  return (
    <Page>
      <Kicker>
        Öneri №{p.id} · {TYPE_LABELS[p.type]} · {lane}
      </Kicker>
      <View style={{ marginTop: 4 }}>
        <ProposalTitle title={p.title} effective={p.effective_title} style={st.h1} heading />
      </View>
      <View style={st.row}>
        <Tag tone={p.status === 'REJECTED' ? 'muted' : 'seal'}>{STATUS_LABELS[p.status]}</Tag>
        <Muted>
          {p.proposer} · {fmtDateTime(p.created_at)} · seçmen: {p.scope}
          {p.area_name ? ` · ${p.area_name}` : ''}
        </Muted>
      </View>
      <Rule double />

      {p.narrowings?.map((n: any, i: number) => (
        <NarrowingBox key={i} message={n.message} share={n.share} total={n.total} />
      ))}

      {p.payload?.cellar_thread_id ? (
        <InfoNotice>
          <Body>
            Bu öneri Mahzen başlığı #{p.payload.cellar_thread_id} katılımcılarının oylamasıyla doğdu.{' '}
            <Link href={`/ifsa/${p.payload.cellar_thread_id}`} style={{ color: paper.seal }}>
              İfşa edilen başlığı oku →
            </Link>
          </Body>
        </InfoNotice>
      ) : null}

      {isDraft ? (
        me?.nickname === p.proposer ? (
          <Section title="Taslağı tamamla">
            <Muted>Alanı, seçmen kapsamını ve etkilenen kaynakları seçip gönderin; öneri normal akışa girer.</Muted>
            <ProposalForm
              ctx={{ type: 'KONU' }}
              draftId={p.id}
              initial={{ title: p.title, body: p.body }}
              onDone={() => res.reload()}
            />
          </Section>
        ) : (
          <InfoNotice>Bu taslağı yalnızca sahibi gönderebilir.</InfoNotice>
        )
      ) : (
        <View>
          {p.body ? <Body style={{ fontSize: 19, lineHeight: 28 }}>{p.body}</Body> : null}

          {p.type === 'DUZENLEME' && p.diff ? (
            <Section title="Önerilen değişiklik">
              <DiffText chunks={p.diff} />
            </Section>
          ) : null}

          {p.type === 'SILME' && p.target_preview ? (
            <Section title="Silinmesi önerilen içerik">
              <View style={st.quote}>
                <Body style={{ fontFamily: fonts.serifItalic }}>
                  {p.target_preview.text ?? p.target_preview.title}
                </Body>
              </View>
              <Link href={`/konu/${p.payload.topic_id}`} style={st.link}>konuya git →</Link>
            </Section>
          ) : null}

          {p.type === 'SILME' ? (
            <Section title="Silme gerekçesi" aside={<Kicker>{p.own ? 'yazarın isteği' : 'içerik kuralı'}</Kicker>}>
              {p.own ? (
                <Body>Yazar kendi mesajının silinmesini istiyor; gerekçe gerekmez.</Body>
              ) : null}
              {p.content_rules?.map((r: any) => (
                <Body key={r.code}>
                  <Text style={{ fontFamily: fonts.monoBold, color: paper.seal }}>{r.code}</Text> {r.title}
                </Body>
              ))}
              {p.excerpt ? (
                <View style={st.quote}>
                  <Kicker>Kuralı ihlal ettiği belirtilen kısım</Kicker>
                  <Body style={{ fontFamily: fonts.serifItalic }}>«{p.excerpt}»</Body>
                </View>
              ) : null}
              {p.threshold ? (
                <Muted>
                  Eşik: {p.threshold.key} {p.threshold.karsilastirma === '>' ? '>' : '≥'} {p.threshold.oran}{' '}
                  (kullanılan oylar içinde{p.own ? '; yazarın kendi mesajı basit çoğunlukla oylanır' : ''}).
                </Muted>
              ) : null}
            </Section>
          ) : null}

          {p.type === 'YONETMELIK' ? (
            <Section title={`Madde: ${p.payload.article_key}`}>
              <Body>
                <Text style={{ fontFamily: fonts.monoMedium }}>{JSON.stringify(p.payload.old_value)}</Text>
                {'  →  '}
                <Text style={{ fontFamily: fonts.monoBold, color: paper.seal }}>
                  {JSON.stringify(p.payload.new_value)}
                </Text>
              </Body>
              <Muted>
                {describeArticleValue('', p.payload.old_value)} → {describeArticleValue('', p.payload.new_value)}
              </Muted>
            </Section>
          ) : null}

          {p.type === 'KAPANIS' && p.texts ? (
            <Section title="Karar metinleri" aside={<Kicker>onay oylaması</Kicker>}>
              {p.texts.map((t: any) => (
                <View key={t.id} style={st.text}>
                  <Kicker>Metin #{t.id} · {t.author}</Kicker>
                  <Body>{t.text}</Body>
                  <Seal hash={t.ledger_hash} />
                </View>
              ))}
              {p.status === 'RIVAL_PERIOD' ? (
                <View style={{ marginTop: 10, gap: 4 }}>
                  <Kicker>Rakip metin süresinin bitmesine</Kicker>
                  <Countdown target={p.deadline_at} />
                </View>
              ) : null}
              {p.viewer?.can_add_rival ? <Rival id={p.id} onDone={res.reload} /> : null}
              {p.decision_id ? (
                <Link href={`/konu/${p.payload.topic_id}`} style={[st.link, { marginTop: 8 }]}>
                  Karar ve şerhler →
                </Link>
              ) : null}
            </Section>
          ) : null}

          {p.resources?.length ? (
            <Section title="Etkilenen kaynaklar">
              {p.resources.map((r: any) => (
                <Body key={r.id}>
                  · {r.name}
                  {r.narrowed ? (
                    <Text style={{ color: paper.seal }}>
                      {` — yalnızca ${r.narrowed.scope} payı`}
                      {r.narrowed.total ? ` (${fmtNumber(r.narrowed.share)} / ${fmtNumber(r.narrowed.total)})` : ''}
                    </Text>
                  ) : null}
                </Body>
              ))}
            </Section>
          ) : null}

          {p.status === 'SILENT' ? (
            <Section title="Sessiz onay" aside={<Countdown target={p.deadline_at} />}>
              <Body style={{ marginBottom: 8 }}>
                Süre dolduğunda itiraz eşiği aşılmamışsa öneri kabul edilir. Eşik aşılırsa bir sonraki
                Karar Saati&apos;nde oylanır.
              </Body>
              <ObjectionMeter count={p.objections.count} threshold={p.objections.threshold} />
              <ErrorNotice error={error} />
              {me && !p.viewer?.has_objected ? (
                <View style={{ marginTop: 12 }}>
                  <Button
                    label="İtiraz et"
                    variant="secondary"
                    onPress={object}
                    disabled={p.viewer?.has_vote_right === false}
                  />
                  {p.viewer?.has_vote_right === false ? <Muted>{p.viewer.vote_right_reason}</Muted> : null}
                </View>
              ) : null}
              {p.viewer?.has_objected ? <Muted style={{ marginTop: 8 }}>İtirazınız kaydedildi.</Muted> : null}
            </Section>
          ) : null}

          {p.maturity && !p.maturity.mature ? (
            <View style={st.maturing}>
              <Kicker style={{ color: paper.seal }}>Olgunlaşma</Kicker>
              <Text style={st.maturingText}>{maturityLine(p.maturity)}</Text>
              <Muted>{maturityDetail(p.maturity)}</Muted>
            </View>
          ) : p.status === 'QUEUED' ? (
            <InfoNotice>
              Bu öneri {p.maturity ? `${fmtSession(p.maturity.first_session_at)} ` : 'bir sonraki '}
              Karar Saati&apos;nde oylanacak.
            </InfoNotice>
          ) : null}
          {p.status === 'VOTING' ? (
            <InfoNotice>
              <Body>Karar Saati penceresi açık. </Body>
              <Button label="Oy pusulası →" small onPress={() => router.push('/karar-saati')} />
            </InfoNotice>
          ) : null}
          {p.outcome_note && !p.result ? <InfoNotice>{p.outcome_note}</InfoNotice> : null}
          {p.topic_id ? (
            <InfoNotice>
              <Body>
                Öneri kabul edildi ve konu oldu.{' '}
                <Link href={`/konu/${p.topic_id}`} style={{ color: paper.seal }}>
                  Konuya git →
                </Link>
              </Body>
            </InfoNotice>
          ) : null}
          <Result p={p} />
        </View>
      )}

      {p.oracle_comment ? <OracleOpinion text={p.oracle_comment} /> : null}

      <View style={[st.row, { marginTop: 16 }]}>
        <Seal hash={p.ledger_hash} label="ilan" />
      </View>
    </Page>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', gap: 10, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 },
  h1: { fontFamily: fonts.serifBold, fontSize: 30, lineHeight: 36, color: paper.ink },
  link: { fontFamily: fonts.serif, fontSize: 16, color: paper.seal },
  maturing: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 12, marginVertical: 12, gap: 4 },
  maturingText: { fontFamily: fonts.serifBold, fontSize: 19, lineHeight: 25, color: paper.ink },
  cell: { width: 18, height: 18, borderWidth: 1.5, borderColor: paper.seal },
  oracle: {
    marginTop: 24,
    borderTopWidth: 3,
    borderBottomWidth: 1,
    borderColor: paper.ink,
    paddingVertical: 12,
    gap: 4,
  },
  oracleLine: { fontFamily: fonts.mono, fontSize: 13, lineHeight: 19, color: paper.ink },
  quote: { borderLeftWidth: 3, borderLeftColor: paper.hairline, paddingLeft: 12, marginVertical: 6 },
  text: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 4 },
});
