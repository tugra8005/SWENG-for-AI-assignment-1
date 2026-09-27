import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  Choice,
  ErrorNotice,
  Field,
  InfoNotice,
  Kicker,
  Muted,
  Rule,
} from '@/components/paper';
import { describeArticleValue } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export type FormContext = {
  type: string;
  topic?: string;
  message?: string;
  parent?: string;
  article?: string;
  reopen?: string;
};

function Chips<T extends string>({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: { value: T; label: string; note?: string; disabled?: boolean }[];
  selected: T[];
  onToggle: (v: T) => void;
}) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Kicker style={{ marginBottom: 6 }}>{label}</Kicker>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {options.map((o) => {
          const on = selected.includes(o.value);
          return (
            <Pressable
              key={o.value}
              disabled={o.disabled}
              onPress={() => onToggle(o.value)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on, disabled: o.disabled }}
              style={{
                borderWidth: 1,
                borderColor: on ? paper.seal : paper.ink,
                backgroundColor: on ? paper.seal : 'transparent',
                paddingHorizontal: 8,
                paddingVertical: 5,
                opacity: o.disabled ? 0.4 : 1,
              }}
            >
              <Text style={{ fontFamily: fonts.monoMedium, fontSize: 12, color: on ? paper.sheet : paper.ink }}>
                {on ? '■ ' : '□ '}
                {o.label}
              </Text>
              {o.note ? (
                <Text style={{ fontFamily: fonts.serifItalic, fontSize: 11, color: on ? paper.bgDeep : paper.muted }}>
                  {o.note}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

function ValueEditor({ article, value, onChange }: { article: any; value: any; onChange: (v: any) => void }) {
  const kind = article.kind;
  if (kind === 'sure') {
    const unit = Object.keys(value ?? article.value)[0] ?? 'gun';
    const amount = String((value ?? article.value)[unit] ?? '');
    return (
      <View>
        <Field
          label="Yeni süre"
          value={amount}
          keyboardType="number-pad"
          onChangeText={(t) => onChange({ [unit]: Number(t) || 0 })}
        />
        <Choice
          label="Birim"
          value={unit}
          options={[
            { value: 'dakika', label: 'dakika' },
            { value: 'saat', label: 'saat' },
            { value: 'gun', label: 'gün' },
          ]}
          onChange={(u) => onChange({ [u]: Number(amount) || 0 })}
        />
      </View>
    );
  }
  if (kind === 'oran') {
    const v = value ?? article.value;
    return (
      <View>
        <Field label="Yeni oran (pay/payda)" value={v.oran} onChangeText={(t) => onChange({ ...v, oran: t })} />
        <Choice
          label="Karşılaştırma"
          value={v.karsilastirma}
          options={[
            { value: '>', label: '>  (fazlası)' },
            { value: '>=', label: '≥  (en az)' },
          ]}
          onChange={(c) => onChange({ ...v, karsilastirma: c })}
        />
      </View>
    );
  }
  if (kind === 'tamsayi' || kind === 'sayi') {
    const v = value ?? article.value;
    return (
      <Field
        label="Yeni değer"
        value={String(v.deger)}
        keyboardType="numeric"
        onChangeText={(t) => onChange({ deger: Number(t.replace(',', '.')) || 0 })}
      />
    );
  }
  return (
    <Field
      label="Yeni değer (JSON)"
      multiline
      value={typeof value === 'string' ? value : JSON.stringify(value ?? article.value, null, 1)}
      onChangeText={(t) => {
        try {
          onChange(JSON.parse(t));
        } catch {
          onChange(t);
        }
      }}
    />
  );
}

export function ProposalForm({
  ctx,
  draftId,
  initial,
  onDone,
}: {
  ctx: FormContext;
  draftId?: number;
  initial?: { title?: string; body?: string };
  onDone: (id: number) => void;
}) {
  const type = ctx.type;
  const areas = useApi<any[]>('/areas');
  const scopes = useApi<any[]>('/scopes');
  const resources = useApi<any[]>('/resources');
  const regulation = useApi<any[]>(type === 'YONETMELIK' ? '/regulation' : null);
  const topicId = ctx.topic ?? ctx.parent ?? ctx.reopen;
  const topic = useApi<any>(topicId ? `/topics/${topicId}` : null);
  const history = useApi<any>(ctx.message ? `/messages/${ctx.message}/history` : null);

  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [area, setArea] = useState<string | null>(null);
  const [scope, setScope] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [newText, setNewText] = useState<string | null>(null);
  const [articleKey, setArticleKey] = useState<string | null>(ctx.article ?? null);
  const [newValue, setNewValue] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);

  const currentText = history.data?.versions?.at(-1)?.text ?? '';
  const article = regulation.data?.find((a) => a.key === articleKey);
  const needsLabels = (type === 'KONU' && !ctx.reopen) || type === 'ALT_KONU';
  const areaOptions = useMemo(() => {
    // Ağaç sırası (derinlik öncelikli), girintili.
    const list = areas.data ?? [];
    const out: { value: string; label: string }[] = [];
    const walk = (parent: string | null, depth: number) => {
      for (const a of list.filter((x) => x.parent_id === parent)) {
        out.push({ value: a.id, label: `${'· '.repeat(depth)}${a.name}` });
        walk(a.id, depth + 1);
      }
    };
    walk(null, 0);
    return out;
  }, [areas.data]);

  const submit = async () => {
    setError(null);
    const payload: Record<string, unknown> = { type, title, body };
    if (needsLabels) Object.assign(payload, { area_id: area, scope_id: scope, resource_ids: picked });
    if (type === 'ALT_KONU') payload.parent_topic_id = Number(ctx.parent);
    if (ctx.reopen) payload.reopens_topic_id = Number(ctx.reopen);
    if (type === 'DUZENLEME') Object.assign(payload, { target_message_id: Number(ctx.message), new_text: newText ?? currentText });
    if (type === 'SILME') {
      if (ctx.message) payload.target_message_id = Number(ctx.message);
      else payload.target_topic_id = Number(ctx.topic);
    }
    if (type === 'KAPANIS') payload.target_topic_id = Number(ctx.topic);
    if (type === 'YONETMELIK') Object.assign(payload, { article_key: articleKey, new_value: newValue ?? article?.value });
    try {
      const res = await api(draftId ? `/proposals/${draftId}/submit` : '/proposals', {
        method: 'POST',
        body: payload,
      });
      onDone(res.id);
    } catch (e) {
      setError(e);
    }
  };

  return (
    <View>
      {topic.data && !topic.data.deleted_by_proposal_id ? (
        <InfoNotice>
          <Kicker>Hedef konu</Kicker>
          <Body>
            №{topic.data.id} — {topic.data.title}
          </Body>
        </InfoNotice>
      ) : null}

      {type === 'DUZENLEME' || (type === 'SILME' && ctx.message) ? (
        <InfoNotice>
          <Kicker>Hedef mesaj #{ctx.message}</Kicker>
          <Body style={{ fontFamily: fonts.serifItalic }}>{currentText || '…'}</Body>
        </InfoNotice>
      ) : null}

      {type !== 'SILME' && type !== 'DUZENLEME' && type !== 'YONETMELIK' && !ctx.reopen ? (
        <Field
          label={type === 'KAPANIS' ? 'Başlık (isteğe bağlı)' : 'Başlık'}
          value={title}
          onChangeText={setTitle}
        />
      ) : null}

      {type === 'DUZENLEME' ? (
        <Field
          label="Önerilen yeni metin"
          value={newText ?? currentText}
          onChangeText={setNewText}
          multiline
        />
      ) : null}

      {type === 'YONETMELIK' ? (
        <View>
          <Choice
            label="Madde"
            value={articleKey}
            options={(regulation.data ?? []).map((a) => ({ value: a.key, label: a.key }))}
            onChange={(k) => {
              setArticleKey(k);
              setNewValue(null);
            }}
          />
          {article ? (
            <View>
              <Muted>{article.description}</Muted>
              <Body style={{ marginVertical: 6 }}>
                Şu anki değer: <Text style={{ fontFamily: fonts.monoMedium }}>{describeArticleValue(article.kind, article.value)}</Text>
              </Body>
              <ValueEditor article={article} value={newValue} onChange={setNewValue} />
              <Muted style={{ marginBottom: 10 }}>
                Yönetmelik değişiklikleri Genel kapsamda, Karar Saati&apos;nde ve yonetmelik_esigi ile oylanır.
              </Muted>
            </View>
          ) : null}
        </View>
      ) : null}

      <Field
        label={
          type === 'KAPANIS'
            ? 'Karar metni'
            : type === 'KONU' && !ctx.reopen
              ? 'Açılış metni'
              : type === 'ALT_KONU'
                ? 'Açılış metni'
                : 'Gerekçe'
        }
        value={body}
        onChangeText={setBody}
        multiline
      />

      {needsLabels ? (
        <View>
          <Rule faint />
          <Kicker style={{ marginBottom: 10, color: paper.seal }}>
            Etiketler — kapsamı ve etkilenen kaynakları siz seçersiniz; Hâtif denetler
          </Kicker>
          <Choice label="Alan" value={area} options={areaOptions} onChange={setArea} />
          <Choice
            label="Seçmen kapsamı (kim oy verecek?)"
            value={scope}
            options={(scopes.data ?? []).map((s) => ({
              value: s.id,
              label: s.name,
              note: s.has_vote_right === false ? 'oy hakkınız yok' : undefined,
            }))}
            onChange={setScope}
          />
          <Chips
            label="Etkilenen kaynaklar (isteğe bağlı)"
            options={(resources.data ?? [])
              .filter((r) => r.kind === 'ORTAK')
              .map((r) => ({
                value: r.id,
                label: r.name,
                note: `sahibi: ${r.owner}${r.divisible ? ' · şehir bazında bölünebilir' : ' · bölünemez'}`,
              }))}
            selected={picked}
            onToggle={(v) => setPicked((p) => (p.includes(v) ? p.filter((x) => x !== v) : [...p, v]))}
          />
        </View>
      ) : null}

      <ErrorNotice error={error} />
      <Button label={draftId ? 'Taslağı öneri olarak gönder' : 'Öneriyi aç'} onPress={submit} />
      <Muted style={{ marginTop: 10, fontSize: 13 }}>
        Öneri açılırken R1–R6 denetimleri çalışır; ihlal varsa gerekçesiyle reddedilir.
      </Muted>
    </View>
  );
}
