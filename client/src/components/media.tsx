/**
 * Görseller: gazete baskısı (yarım ton) gösterimi ve yükleme alanı.
 *
 * Sitede her görsel önce baskı sürümüyle (mürekkep noktaları) görünür; dokununca özgün renkli
 * fotoğraf aynı çerçevede açılır. Alt metin zorunludur ve görselin altında künye olarak durur.
 */

import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { mediaUrl, uploadImage, type MediaItem, type PickedFile } from '@/api/client';
import { Button, ErrorNotice, Field, Grid, Kicker } from '@/components/paper';
import { fonts, paper } from '@/theme/tokens';

export type { MediaItem };

const MAX_BYTES = 8 * 1024 * 1024;

/** Tek görsel: baskı ↔ özgün geçişi ve künye. ``maxHeight`` dik görselin sütunu boydan kaplamasını önler. */
export function PrintImage({
  m,
  maxHeight = 520,
  caption = true,
}: {
  m: MediaItem;
  maxHeight?: number;
  caption?: boolean;
}) {
  const [original, setOriginal] = useState(false);
  const ratio = m.width / m.height;
  return (
    // Künye görselin genişliğinde kalır: dik görsel sütunu boydan kaplamaz, altındaki çizgi de taşmaz.
    <View style={[st.figure, { width: '100%', maxWidth: maxHeight * ratio }]}>
      <Pressable
        onPress={() => setOriginal(!original)}
        accessibilityRole="button"
        accessibilityLabel={`${m.alt}. ${original ? 'Baskı görünümüne dön.' : 'Özgün fotoğrafı göster.'}`}
      >
        <Image
          source={mediaUrl(m.id, original ? 'ozgun' : 'baski')}
          alt={m.alt}
          accessibilityLabel={m.alt}
          contentFit="cover"
          transition={120}
          style={[st.image, { aspectRatio: ratio }]}
        />
        <Text style={st.badge}>{original ? 'özgün' : 'baskı'}</Text>
      </Pressable>
      {caption ? (
        <View style={st.caption}>
          <Text style={st.alt}>{m.alt}</Text>
          {m.credit ? (
            <Text style={st.credit}>
              {m.credit}
              {m.source_url ? ' · kaynak: Wikimedia Commons' : ''}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

/** Mesajın görselleri: biri tam genişlikte, birden çoksa ızgarada. */
export function PictureSet({ items }: { items?: MediaItem[] | null }) {
  if (!items?.length) return null;
  if (items.length === 1) {
    return (
      <View style={{ marginTop: 10 }}>
        <PrintImage m={items[0]} maxHeight={440} />
      </View>
    );
  }
  return (
    <View style={{ marginTop: 10 }}>
      <Grid min={220} gap={12}>
        {items.map((m) => (
          <PrintImage key={m.id} m={m} maxHeight={360} />
        ))}
      </Grid>
    </View>
  );
}

type Pending = PickedFile & { preview: string; width: number; height: number };

/** Yükleme alanı: görsel seç → ne gösterdiğini yaz (alt metin) → ekle. Eklenen görseller küçük
 * önizleme olarak listelenir ve gönderimden önce çıkarılabilir. */
export function ImageAttach({
  value,
  onChange,
  max = 4,
  label = 'Görsel ekle',
}: {
  value: MediaItem[];
  onChange: (next: MediaItem[]) => void;
  max?: number;
  label?: string;
}) {
  const [pending, setPending] = useState<Pending | null>(null);
  const [alt, setAlt] = useState('');
  const [error, setError] = useState<unknown>(null);

  const pick = async () => {
    setError(null);
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: 'images', quality: 0.85 });
    if (r.canceled || !r.assets?.length) return;
    const a = r.assets[0];
    if (a.fileSize && a.fileSize > MAX_BYTES) {
      setError(new Error('Görsel en fazla 8 MB olabilir.'));
      return;
    }
    setPending({
      uri: a.uri,
      name: a.fileName ?? 'gorsel.jpg',
      type: a.mimeType ?? 'image/jpeg',
      file: a.file ?? undefined,
      preview: a.uri,
      width: a.width,
      height: a.height,
    });
  };

  const upload = async () => {
    if (!pending) return;
    setError(null);
    try {
      const m = await uploadImage(pending, alt);
      onChange([...value, m]);
      setPending(null);
      setAlt('');
    } catch (e) {
      setError(e);
    }
  };

  return (
    <View style={st.attach}>
      {value.length ? (
        <View style={st.thumbs}>
          {value.map((m) => (
            <View key={m.id} style={st.thumb}>
              <Image
                source={mediaUrl(m.id)}
                alt={m.alt}
                accessibilityLabel={m.alt}
                contentFit="cover"
                style={st.thumbImage}
              />
              <Text style={st.thumbAlt} numberOfLines={2}>
                {m.alt}
              </Text>
              <Button
                label="çıkar"
                variant="minor"
                onPress={() => onChange(value.filter((x) => x.id !== m.id))}
              />
            </View>
          ))}
        </View>
      ) : null}
      {pending ? (
        <View style={st.pending}>
          <Image
            source={pending.preview}
            contentFit="cover"
            style={[st.pendingImage, { aspectRatio: pending.width / pending.height || 1.5 }]}
            accessibilityLabel="Seçilen görselin önizlemesi"
          />
          <View style={{ flex: 1, minWidth: 220 }}>
            <Field
              label="Görselde ne var?"
              value={alt}
              onChangeText={setAlt}
              placeholder="Örn. Salonda perde ve dizili sandalyeler"
              hint="Zorunlu. Görmeyen okur bu cümleyi duyar; görselin altında künye olarak da yazılır."
              maxLength={300}
            />
            <View style={st.row}>
              <Button label="Ekle" small onPress={upload} disabled={alt.trim().length < 3} />
              <Button
                label="Vazgeç"
                variant="quiet"
                onPress={() => {
                  setPending(null);
                  setAlt('');
                }}
              />
            </View>
          </View>
        </View>
      ) : value.length < max ? (
        <View style={st.row}>
          <Button label={`＋ ${label}`} variant="secondary" small onPress={pick} />
          <Kicker>jpeg · png · webp, en çok 8 MB{max > 1 ? ` · ${value.length}/${max}` : ''}</Kicker>
        </View>
      ) : null}
      <ErrorNotice error={error} />
    </View>
  );
}

const st = StyleSheet.create({
  figure: { gap: 6 },
  image: { width: '100%', backgroundColor: paper.bgDeep, borderWidth: 1, borderColor: paper.ink },
  badge: {
    position: 'absolute',
    right: 6,
    bottom: 6,
    fontFamily: fonts.monoMedium,
    fontSize: 10,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    color: paper.ink,
    backgroundColor: paper.sheet,
    borderWidth: 1,
    borderColor: paper.ink,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  caption: { borderTopWidth: 1, borderTopColor: paper.hairline, paddingTop: 4, gap: 2 },
  alt: { fontFamily: fonts.serifItalic, fontSize: 14, lineHeight: 19, color: paper.inkSoft },
  credit: { fontFamily: fonts.mono, fontSize: 10, lineHeight: 14, letterSpacing: 0.3, color: paper.muted },
  attach: { gap: 10, marginBottom: 12 },
  row: { flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  thumbs: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  thumb: { width: 132, gap: 4 },
  thumbImage: { width: 132, height: 88, borderWidth: 1, borderColor: paper.ink, backgroundColor: paper.bgDeep },
  thumbAlt: { fontFamily: fonts.serifItalic, fontSize: 12, lineHeight: 16, color: paper.inkSoft },
  pending: {
    flexDirection: 'row',
    gap: 14,
    flexWrap: 'wrap',
    padding: 12,
    borderWidth: 1,
    borderColor: paper.hairline,
    borderStyle: 'dashed',
    backgroundColor: paper.sheet,
  },
  pendingImage: { width: 180, maxHeight: 220, borderWidth: 1, borderColor: paper.ink },
});
