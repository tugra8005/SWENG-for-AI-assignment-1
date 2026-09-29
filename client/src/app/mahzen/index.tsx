import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { api } from '@/api/client';
import {
  AmberButton,
  AmberError,
  AmberField,
  Banner,
  CellarPage,
  cellarStyles,
  DecayText,
  LifeBar,
  Term,
  TermDim,
  WarningModal,
} from '@/components/cellar';
import { useAuth } from '@/lib/auth';
import { fmtDateTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { cellar } from '@/theme/tokens';

function NewThread({ onCreated }: { onCreated: (id: number) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!open) return <AmberButton label="+ yeni başlık" onPress={() => setOpen(true)} />;
  return (
    <View style={st.box}>
      <AmberField label="başlık" value={title} onChangeText={setTitle} maxLength={120} />
      <AmberField label="ilk düşünce" value={text} onChangeText={setText} multiline />
      <Pressable onPress={() => setAck((a) => !a)} accessibilityRole="checkbox" aria-checked={ack}>
        <Term style={{ fontSize: 13 }}>
          [{ack ? 'x' : ' '}] Bu başlık katılımcılarının oylamasıyla öneriye dönüştürülürse, burada yazan
          herkesin takma adı açığa çıkar.
        </Term>
      </Pressable>
      <AmberError error={error} />
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 8 }}>
        <AmberButton
          label="aç"
          disabled={!ack || !title.trim() || !text.trim()}
          onPress={async () => {
            setError(null);
            try {
              const r = await api('/cellar/threads', { method: 'POST', body: { title, text, acknowledge: ack } });
              onCreated(r.id);
            } catch (e) {
              setError(e);
            }
          }}
        />
        <AmberButton label="vazgeç" subtle onPress={() => setOpen(false)} />
      </View>
    </View>
  );
}

export default function CellarIndex() {
  const { me, ready, refresh } = useAuth();
  const entry = useApi<any>(me ? '/cellar/entry' : null);
  const list = useApi<any>(me && entry.data && !entry.data.needs_warning ? '/cellar/threads' : null, 15_000);

  if (ready && !me) {
    return (
      <CellarPage>
        <Banner>MAHZEN</Banner>
        <Term style={{ marginTop: 12 }}>Mahzen&apos;e girmek için önce Meydan&apos;da giriş yapın.</Term>
        <View style={{ marginTop: 10 }}>
          <AmberButton label="giriş" onPress={() => router.push('/giris')} />
        </View>
      </CellarPage>
    );
  }

  return (
    <CellarPage>
      <WarningModal
        visible={!!entry.data?.needs_warning}
        text={`Mahzen anonim ve geçicidir; başlıklar alta düştükçe kalıcı olarak silinir. ${entry.data?.warning ?? ''}`}
        onAccept={async () => {
          await api('/cellar/entry/ack', { method: 'POST' });
          await refresh();
          entry.reload();
        }}
        onCancel={() => router.replace('/')}
      />
      <Banner>MAHZEN</Banner>
      {/* Değerler yüklenmeden (uyarı penceresinin arkasında) "kapasite … başlık" gösterilmez. */}
      {list.data ? (
        <TermDim>anonim · geçici · kapasite {list.data.capacity} başlık · yükselme sınırı {list.data.bump_limit} yanıt</TermDim>
      ) : (
        <TermDim>anonim · geçici</TermDim>
      )}
      <View style={cellarStyles.rule} />
      <NewThread onCreated={(id) => router.push(`/mahzen/${id}`)} />
      <View style={cellarStyles.rule} />
      {list.data?.threads.map((t: any) => {
        const decay = 1 - t.lifetime;
        return (
          <Pressable
            key={t.id}
            onPress={() => router.push(`/mahzen/${t.id}`)}
            accessibilityRole="link"
            accessibilityLabel={`${t.title}, ${t.reply_count} yanıt`}
            style={({ hovered }: any) => [st.row, hovered && { backgroundColor: cellar.amberGlow }]}
          >
            <View style={st.rowHead}>
              <TermDim style={{ fontSize: 11 }}>No.{t.id} · Gölge·{t.op_shade} · {fmtDateTime(t.bumped_at)}</TermDim>
              <LifeBar lifetime={t.lifetime} />
            </View>
            <DecayText text={t.title} decay={decay} seed={t.id} style={{ fontSize: 17, lineHeight: 24 }} />
            <DecayText text={t.op_preview} decay={decay} seed={t.id + 1000} numberOfLines={2} style={{ fontSize: 13 }} />
            <TermDim style={{ fontSize: 11 }}>
              {t.reply_count} yanıt{t.bump_locked ? ' · yükselme sınırında' : ''}{t.has_vote ? ' · oylama açık' : ''}
            </TermDim>
          </Pressable>
        );
      })}
    </CellarPage>
  );
}

const st = StyleSheet.create({
  box: { borderWidth: 1, borderColor: cellar.amberDim, padding: 12 },
  row: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: cellar.line, gap: 2 },
  rowHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
});
