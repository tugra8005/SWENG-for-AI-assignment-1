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
  LockIcon,
  Muted,
  Rule,
} from '@/components/paper';
import { EventFields, type EventInput } from '@/components/event';
import { ImageAttach, type MediaItem } from '@/components/media';
import { useAuth } from '@/lib/auth';
import { useLocalDraft } from '@/lib/draft';
import { describeArticleValue, fmtPercent1 } from '@/lib/format';
import { shareImpact, toRows } from '@/lib/shares';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export type FormContext = {
  type: string;
  topic?: string;
  message?: string;
  parent?: string;
  article?: string;
  reopen?: string;
  /** YONETMELIK: 'degistir' (varsayılan), 'ekle' (yeni içerik kuralı), 'kaldir' (içerik kuralı) */
  action?: string;
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
              aria-checked={on}
              aria-disabled={o.disabled}
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
  if (kind === 'icerik_kurali') {
    const v = value ?? article.value ?? { baslik: '', metin: '', anahtar_kelimeler: [] };
    return (
      <View>
        <Field label="Kuralın başlığı" value={v.baslik} onChangeText={(t) => onChange({ ...v, baslik: t })} />
        <Field label="Kuralın metni" value={v.metin} multiline onChangeText={(t) => onChange({ ...v, metin: t })} />
        <Field
          label="Anahtar kelimeler (virgülle ayırın)"
          value={(v.anahtar_kelimeler ?? []).join(',')}
          onChangeText={(t) => onChange({ ...v, anahtar_kelimeler: t.split(',') })}
          hint="Hâtif, bu kurala dayanan silme önerilerinde bu kelimeleri alıntıda arar."
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
  const regulation = useApi<any[]>(
    type === 'YONETMELIK' || type === 'SILME' || type === 'KONU' || type === 'ALT_KONU' ? '/regulation' : null,
  );
  const { me } = useAuth();
  const topicId = ctx.topic ?? ctx.parent ?? ctx.reopen;
  const topic = useApi<any>(topicId ? `/topics/${topicId}` : null);
  const history = useApi<any>(ctx.message ? `/messages/${ctx.message}/history` : null);

  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  // Cihazda saklanan taslak (Mahzen'den gelen sunucu taslağında gerekmez: o zaten kayıtlı).
  const draftKey = `mesveret.taslak.${type}.${ctx.parent ?? ctx.topic ?? ctx.message ?? ctx.article ?? ctx.reopen ?? ''}`;
  const localDraft = useLocalDraft(
    draftKey, title, body,
    (d) => {
      setTitle((t) => t || d.title);
      setBody((b) => b || d.body);
    },
    !draftId,
  );
  const [area, setArea] = useState<string | null>(null);
  const [scope, setScope] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [newText, setNewText] = useState<string | null>(null);
  const [articleKey, setArticleKey] = useState<string | null>(ctx.article ?? null);
  const [newValue, setNewValue] = useState<any>(null);
  const [rules, setRules] = useState<string[]>([]);
  // Bölünebilir kaynağın yapılandırılmış etkisi: {kaynak: {kapsam: yeni_pay (metin)}}
  const [effect, setEffect] = useState<Record<string, Record<string, string>>>({});
  const [excerpt, setExcerpt] = useState('');
  // Yeni konunun kapak görseli: kabul edilince konunun ve haberin görseli olur.
  const [cover, setCover] = useState<MediaItem[]>([]);
  // Muhatap (R9): kapsam seçilince sunucu her muhatabın bu kapsama açık olup olmadığını söyler.
  const [addressee, setAddressee] = useState<string | null>(null);
  // Takvime giden konunun etkinliği (isteğe bağlı): kabul edilince takvime yazılır.
  const [event, setEvent] = useState<EventInput | null>(null);
  const [error, setError] = useState<unknown>(null);

  const currentText = history.data?.versions?.at(-1)?.text ?? '';
  // Kendi mesajının silinmesi: yazarın rızası; gerekçe gerekmez, basit çoğunluk yeter.
  const ownMessage = type === 'SILME' && !!ctx.message && !!me && history.data?.author === me.nickname;
  const contentRules = (regulation.data ?? []).filter((a) => a.kind === 'icerik_kurali' && a.value);
  const deletionRatio = regulation.data?.find((a) => a.key === 'silme_esigi')?.value?.oran ?? '2/3';
  const article = regulation.data?.find((a) => a.key === articleKey);
  const regAction = type === 'YONETMELIK' ? (ctx.action ?? 'degistir') : null;
  const needsLabels = (type === 'KONU' && !ctx.reopen) || type === 'ALT_KONU';
  const addressees = useApi<any[]>(needsLabels ? `/addressees${scope ? `?scope_id=${scope}` : ''}` : null);
  const chosenAddressee = (addressees.data ?? []).find((a) => a.id === addressee);
  const inherited = type === 'ALT_KONU' ? topic.data?.addressee : null;
  // Sahip kapsamın oyladığı bölünebilir kaynaklar: etkiyi kapsam başına bildirmek zorunlu (R2).
  const splitResources = (resources.data ?? []).filter(
    (r) => picked.includes(r.id) && r.divisible && scope === r.owner_scope_id,
  );
  const thresholdPP = Number(regulation.data?.find((a) => a.key === 'orantisizlik_esigi')?.value?.deger ?? 10);
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
    if (needsLabels && cover.length) payload.cover_media_id = cover[0].id;
    if (needsLabels && addressee) payload.addressee = addressee;
    const toCalendar = (addressee ?? inherited?.id) === 'takvim';
    if (needsLabels && toCalendar && event) payload.event = event;
    if (needsLabels && splitResources.length) {
      payload.share_effect = Object.fromEntries(
        splitResources.map((r) => [
          r.id,
          Object.fromEntries(toRows(r.shares, effect[r.id] ?? {}).map((row) => [row.scopeId, row.next])),
        ]),
      );
    }
    if (type === 'ALT_KONU') payload.parent_topic_id = Number(ctx.parent);
    if (ctx.reopen) payload.reopens_topic_id = Number(ctx.reopen);
    if (type === 'DUZENLEME') Object.assign(payload, { target_message_id: Number(ctx.message), new_text: newText ?? currentText });
    if (type === 'SILME') {
      if (ctx.message) payload.target_message_id = Number(ctx.message);
      else payload.target_topic_id = Number(ctx.topic);
      Object.assign(payload, { content_rules: rules, excerpt });
    }
    if (type === 'KAPANIS') payload.target_topic_id = Number(ctx.topic);
    if (type === 'YONETMELIK') {
      let value = regAction === 'kaldir' ? null : newValue ?? article?.value;
      if (value && Array.isArray(value.anahtar_kelimeler)) {
        value = { ...value, anahtar_kelimeler: value.anahtar_kelimeler.map((k: string) => k.trim()).filter(Boolean) };
      }
      Object.assign(payload, { article_action: regAction, article_key: articleKey, new_value: value });
    }
    try {
      const res = await api(draftId ? `/proposals/${draftId}/submit` : '/proposals', {
        method: 'POST',
        body: payload,
      });
      localDraft.clear();
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

      {type === 'SILME' ? (
        <View>
          {ownMessage ? (
            <InfoNotice>
              Bu sizin mesajınız: gerekçe gerekmez, öneri basit çoğunlukla oylanır. İçerik defterde
              kalır; yalnızca sitede gizlenir.
            </InfoNotice>
          ) : (
            <Muted style={{ marginBottom: 10 }}>
              Silme istisnadır; tartışmalar silinmez. Başkasının içeriğini silmek için en az bir içerik
              kuralı seçin ve kuralı ihlal eden kısmı metinden aynen alıntılayın. Öneri, kullanılan
              oylar içinde en az {deletionRatio} EVET ile geçer (silme_esigi).
            </Muted>
          )}
          <Chips
            label={ownMessage ? 'Dayanılan içerik kuralı (isteğe bağlı)' : 'Dayanılan içerik kuralı'}
            options={contentRules.map((a) => ({
              value: a.key,
              label: `${a.key} ${a.value.baslik}`,
              note: a.value.metin,
            }))}
            selected={rules}
            onToggle={(v) => setRules((r) => (r.includes(v) ? r.filter((x) => x !== v) : [...r, v]))}
          />
          <Field
            label={ownMessage ? 'İhlal eden kısım (isteğe bağlı)' : 'Kuralı ihlal eden kısım (metinden aynen alıntı)'}
            value={excerpt}
            onChangeText={setExcerpt}
            multiline
            hint="Hâtif, seçtiğiniz kuralın anahtar kelimelerini bu alıntıda arar."
          />
        </View>
      ) : null}

      {type !== 'SILME' && type !== 'DUZENLEME' && type !== 'YONETMELIK' && !ctx.reopen ? (
        <Field
          label={type === 'KAPANIS' ? 'Başlık (isteğe bağlı)' : 'Başlık'}
          value={title}
          onChangeText={setTitle}
          maxLength={200}
          hint={title.length > 150 ? `${title.length}/200 karakter` : undefined}
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

      {regAction === 'ekle' ? (
        <View>
          <Muted style={{ marginBottom: 10 }}>
            Yeni içerik kuralının kodu (IK-…) öneri açılırken verilir. Kural dar olmalı: silme ancak
            yazılı bir ihlale dayanabilir, &quot;konu dışı&quot; gibi geniş kurallar çoğunluğun beğenmediği
            görüşü silmenin gerekçesine dönüşür.
          </Muted>
          <ValueEditor article={{ kind: 'icerik_kurali', value: null }} value={newValue} onChange={setNewValue} />
        </View>
      ) : null}

      {regAction !== null && article?.unchangeable ? (
        <InfoNotice>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <LockIcon size={14} />
            <Kicker style={{ color: paper.seal }}>Değiştirilemez madde · {article.key}</Kicker>
          </View>
          <Body>
            Bu madde yönetmeliğin tabanıdır: oylamayla değiştirilemez, kaldırılamaz, değiştirilmesi
            önerilemez (D7). Öneri açılışta R8 ile reddedilir.
          </Body>
        </InfoNotice>
      ) : null}

      {regAction === 'kaldir' && article?.value && !article.unchangeable ? (
        <InfoNotice>
          <Kicker>Kaldırılması önerilen kural</Kicker>
          <Body>
            <Text style={{ fontFamily: fonts.monoBold, color: paper.seal }}>{article.key}</Text> {article.value.baslik}
          </Body>
          <Muted>{article.value.metin}</Muted>
          <Muted style={{ marginTop: 6 }}>
            Kural kaldırılırsa ona dayanan yeni silme önerileri R7&apos;de reddedilir; bekleyen önerilerde
            Hâtif HAYIR der. Kodu bir daha kullanılmaz.
          </Muted>
        </InfoNotice>
      ) : null}

      {regAction === 'degistir' ? (
        <View>
          <Choice
            label="Madde"
            value={articleKey}
            options={(regulation.data ?? [])
              .filter((a) => a.value)
              .map((a) => ({ value: a.key, label: a.key, note: a.unchangeable ? 'değiştirilemez' : undefined }))}
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
        hint={localDraft.savedAt ? 'Taslak bu cihazda saklandı; gönderince silinir.' : undefined}
      />

      {needsLabels ? (
        <View>
          <Kicker style={{ marginBottom: 6 }}>Kapak görseli (isteğe bağlı)</Kicker>
          <ImageAttach value={cover} onChange={setCover} max={1} label="Kapak görseli seç" />
        </View>
      ) : null}

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
          <Choice
            label="Kime iletilecek? (muhatap)"
            value={addressee}
            options={(addressees.data ?? []).map((a) => ({
              value: a.id,
              label: a.name,
              note: !a.allowed ? 'bu kapsam yazamaz' : a.kind === 'TAKVIM' ? 'etkinlik' : 'dilekçe',
              disabled: !a.allowed,
            }))}
            onChange={setAddressee}
          />
          <Muted style={{ marginTop: -6, marginBottom: 14, fontSize: 14 }}>
            {chosenAddressee && !chosenAddressee.allowed
              ? chosenAddressee.refusal
              : chosenAddressee?.kind === 'KURUM'
                ? `Kabul edilirse ${chosenAddressee.name} adresine dilekçe olarak gider; konu karara bağlanınca Karar da iletilir. Yanıt süresi 30 gündür (3071 sayılı Kanun).`
                : chosenAddressee?.kind === 'TAKVIM'
                  ? 'Kabul edilirse Meşveret Takvimi’ne yazılır. Bir etkinlik bildirirseniz (tarih, saat, yer) takvimde o gün görünür.'
                  : inherited
                    ? `Seçmezseniz üst konunun muhatabı kullanılır: ${inherited.name}.`
                    : 'Her konu bir yere iletilmek için açılır: takvime ya da bir kuruma. Kapsam yalnızca yetki alanındaki kuruma yazar (R9).'}
          </Muted>
          {(addressee ?? inherited?.id) === 'takvim' ? <EventFields onChange={setEvent} /> : null}
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
          {splitResources.map((r) => {
            const rows = toRows(r.shares, effect[r.id] ?? {});
            const { average, flagged } = shareImpact(rows, thresholdPP);
            return (
              <View key={r.id} style={{ marginBottom: 14, gap: 6 }}>
                <Kicker style={{ color: paper.seal }}>Pay etkisi · {r.name}</Kicker>
                <Muted>
                  Bölünebilir kaynağı bütün adına oyluyorsunuz: etkisini kapsam başına yeni paylarla bildirin.
                  Payı ortalamanın en az {thresholdPP} yüzde puanı altında azalan kapsam ayrıca oylar; öneri
                  orada da çoğunluk almalı.
                </Muted>
                {rows.map((row) => (
                  <View key={row.scopeId} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <Text style={{ fontFamily: fonts.monoMedium, fontSize: 13, color: paper.ink, width: 90 }}>{row.name}</Text>
                    <Text style={{ fontFamily: fonts.mono, fontSize: 13, color: paper.muted, width: 60 }}>{row.old}</Text>
                    <View style={{ width: 110 }}>
                      <Field
                        label={`${row.name} yeni pay`}
                        value={effect[r.id]?.[row.scopeId] ?? String(row.old)}
                        keyboardType="number-pad"
                        onChangeText={(t) =>
                          setEffect((e) => ({ ...e, [r.id]: { ...(e[r.id] ?? {}), [row.scopeId]: t.replace(/[^0-9]/g, '') } }))
                        }
                      />
                    </View>
                    <Text style={{ fontFamily: fonts.mono, fontSize: 12, color: flagged.includes(row.scopeId) ? paper.seal : paper.muted }}>
                      {row.relative === null ? '—' : fmtPercent1(row.relative)}
                      {flagged.includes(row.scopeId) ? ' · orantısız → ayrı oylama' : ''}
                    </Text>
                  </View>
                ))}
                <Muted style={{ fontSize: 13 }}>
                  Ortalama değişim: {average === null ? '—' : fmtPercent1(average)}
                  {flagged.length ? ' · orantısız etkilenen kapsam varsa öneri doğrudan Karar Saati kuyruğuna girer.' : ''}
                </Muted>
              </View>
            );
          })}
        </View>
      ) : null}

      <ErrorNotice error={error} />
      <Button label={draftId ? 'Taslağı öneri olarak gönder' : 'Öneriyi aç'} onPress={submit} />
      <Muted style={{ marginTop: 10, fontSize: 13 }}>
        Öneri açılırken R1–R9 denetimleri çalışır; ihlal varsa gerekçesiyle reddedilir.
      </Muted>
    </View>
  );
}
