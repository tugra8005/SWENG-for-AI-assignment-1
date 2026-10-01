import AsyncStorage from '@react-native-async-storage/async-storage';
import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  AmberButton,
  AmberError,
  AmberField,
  Banner,
  CellarPage,
  cellarStyles,
  DecayText,
  decayColor,
  LifeBar,
  Term,
  TermDim,
} from '@/components/cellar';
import { Columns, Page, useWide } from '@/components/paper';
import { RevealTransition } from '@/components/reveal-transition';
import { RevealedThread } from '@/components/revealed-thread';
import { useAuth } from '@/lib/auth';
import { fmtDateTime } from '@/lib/format';
import { CORRUPT_FROM } from '@/lib/decay';
import { useApi } from '@/lib/useApi';
import { cellar, fonts } from '@/theme/tokens';

function PostText({ text, decay, seed }: { text: string; decay: number; seed: number }) {
  // >>N referansları vurgulanır (yalnızca aynı başlık içinde geçerlidir).
  const parts = text.split(/(>>\d+)/g);
  // Bozulma başlayana kadar yalnızca soluklaşma; >>N vurgusu korunur.
  if (decay >= CORRUPT_FROM) return <DecayText text={text} decay={decay} seed={seed} />;
  return (
    <Text style={[st.text, { color: decayColor(decay) }]}>
      {parts.map((p, i) =>
        /^>>\d+$/.test(p) ? (
          <Text key={i} style={{ textDecorationLine: 'underline' }}>{p}</Text>
        ) : (
          <Text key={i}>{p}</Text>
        ),
      )}
    </Text>
  );
}

function VotePanel({ t, onChanged }: { t: any; onChanged: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const v = t.vote;
  const call = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.box}>
      <Term style={{ fontFamily: fonts.terminal, fontSize: 24 }}>ÖNERİYE DÖNÜŞTÜR</Term>
      {!v ? (
        t.viewer?.is_poster ? (
          <View style={{ gap: 6 }}>
            <TermDim>
              Oylama açılınca seçmenler şu ana kadar bu başlıkta yazmış olanlardır. EVET, seçmen listesinin
              yarısını aştığı an herkesin takma adı açığa çıkar.
            </TermDim>
            <AmberButton label="oylama aç" onPress={() => call(() => api(`/cellar/threads/${t.id}/reveal-vote`, { method: 'POST' }))} />
          </View>
        ) : (
          <TermDim>Bu başlıkta yazmamış biri başlık üzerinde işlem yapamaz.</TermDim>
        )
      ) : (
        <View style={{ gap: 6 }}>
          <Term>
            seçmen: {v.electorate_size} · geçmesi için gereken EVET: {v.needed_yes ?? '—'}
            {v.flagged_count ? ` · baskın şüphesiyle dışlanan: ${v.flagged_count}` : ''}
          </Term>
          <TermDim>oylar gizli; ara sayım gösterilmez. oyunuzu değiştirebilirsiniz.</TermDim>
          {v.flagged_self ? <Term>!! dışlandınız: {v.flagged_self}</Term> : null}
          {v.i_am_voter ? (
            <View style={{ gap: 6 }}>
              <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <AmberButton label="evet" selected={v.my_vote === true} onPress={() => call(() => api(`/cellar/threads/${t.id}/reveal-vote`, { method: 'PUT', body: { yes: true } }))} />
                <AmberButton label="hayır" selected={v.my_vote === false} onPress={() => call(() => api(`/cellar/threads/${t.id}/reveal-vote`, { method: 'PUT', body: { yes: false } }))} />
              </View>
              {v.my_vote !== null && v.my_vote !== undefined ? (
                <TermDim>seçiminiz: {v.my_vote ? 'evet' : 'hayır'} · kaydedildi; değiştirebilirsiniz</TermDim>
              ) : null}
            </View>
          ) : !v.flagged_self ? (
            <TermDim>Oylama açıldığında bu başlıkta yazmamıştınız; seçmen değilsiniz.</TermDim>
          ) : null}
        </View>
      )}
      <AmberError error={error} />
    </View>
  );
}

export default function Thread() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { me } = useAuth();
  const thread = useApi<any>(me ? `/cellar/threads/${id}` : null, 5000);
  const wide = useWide();
  const [text, setText] = useState('');
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [seen, setSeen] = useState<boolean | null>(null);
  const t = thread.data;
  const seenKey = `mesveret.ifsa.${id}`;

  useEffect(() => {
    AsyncStorage.getItem(seenKey).then((v) => setSeen(v === '1'));
  }, [seenKey]);
  // Geçişin son karesi ifşa edilmiş sayfanın kendisi olduğu için beklemeden geçilir.
  const markSeen = useCallback(() => {
    AsyncStorage.setItem(seenKey, '1');
    setSeen(true);
  }, [seenKey]);

  if (!t) {
    return (
      <CellarPage>
        <Banner style={{ fontSize: 40 }}>MAHZEN</Banner>
        {thread.error ? <Term>!! {thread.error.message}</Term> : <TermDim>yükleniyor…</TermDim>}
      </CellarPage>
    );
  }

  if (t.frozen && seen !== null) {
    if (!seen) {
      return <RevealTransition t={t} onDone={markSeen} />;
    }
    return (
      <Page reading>
        <RevealedThread t={t} />
      </Page>
    );
  }

  const decay = t.lifetime != null ? 1 - t.lifetime : 0;
  const reply = async () => {
    setError(null);
    try {
      await api(`/cellar/threads/${t.id}/posts`, { method: 'POST', body: { text, acknowledge: ack } });
      setText('');
      thread.reload();
    } catch (e) {
      setError(e);
    }
  };

  const posts = (
    <>
      {t.posts.map((p: any, i: number) => (
        <View key={p.no} style={st.post} nativeID={`p${p.no}`}>
          <View style={st.head}>
            <Text style={st.shade}>Gölge·{p.shade}</Text>
            {p.nickname ? <Text style={st.signed}>imzalı: {p.nickname}</Text> : null}
            <TermDim style={{ fontSize: 11 }}>{fmtDateTime(p.created_at)} · No.{p.no}</TermDim>
            {p.is_mine && !p.signed ? (
              <Pressable
                accessibilityRole="button"
                onPress={async () => {
                  await api(`/cellar/posts/${p.no}/sign`, { method: 'POST' });
                  thread.reload();
                }}
              >
                <TermDim style={{ fontSize: 11, textDecorationLine: 'underline' }}>[imzala]</TermDim>
              </Pressable>
            ) : null}
            {!p.is_mine ? (
              <Pressable accessibilityRole="button" onPress={() => setText((x) => `${x}>>${p.no} `)}>
                <TermDim style={{ fontSize: 11, textDecorationLine: 'underline' }}>[&gt;&gt;]</TermDim>
              </Pressable>
            ) : null}
          </View>
          <PostText text={p.text} decay={decay} seed={p.no * 3 + i} />
        </View>
      ))}
    </>
  );
  const respond = (
    <>
      <VotePanel t={t} onChanged={thread.reload} />
      <View style={{ marginTop: 16 }}>
        <AmberField label="yanıt" value={text} onChangeText={setText} multiline />
        {t.viewer?.needs_thread_warning ? (
          <Pressable onPress={() => setAck((a) => !a)} accessibilityRole="checkbox" aria-checked={ack}>
            <Term style={{ fontSize: 13 }}>[{ack ? 'x' : ' '}] {t.warning}</Term>
          </Pressable>
        ) : null}
        <AmberError error={error} />
        <View style={{ marginTop: 8 }}>
          <AmberButton
            label="gönder"
            onPress={reply}
            disabled={!text.trim() || (t.viewer?.needs_thread_warning && !ack)}
          />
        </View>
      </View>
    </>
  );

  return (
    <CellarPage>
      <Pressable onPress={() => router.push('/mahzen')} accessibilityRole="link">
        <TermDim style={{ fontSize: 12 }}>&lt; mahzen</TermDim>
      </Pressable>
      <DecayText text={t.title} decay={decay} seed={t.id} style={st.title} />
      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <TermDim style={{ fontSize: 12 }}>No.{t.id} · {t.reply_count} yanıt · sıra {t.rank != null ? t.rank + 1 : '—'}</TermDim>
        {t.lifetime != null ? <LifeBar lifetime={t.lifetime} /> : null}
        {t.bump_locked ? <TermDim style={{ fontSize: 12 }}>yükselme sınırında</TermDim> : null}
      </View>
      <View style={cellarStyles.rule} />
      {/* Geniş ekranda mesajlar solda; ifşa oylaması ve yanıt formu sağda, kaydırırken yerinde durur. */}
      {wide ? (
        <Columns ruleColor={cellar.amberDim} sideWidth={380} stickySide main={posts} side={respond} />
      ) : (
        <>
          {posts}
          <View style={cellarStyles.rule} />
          {respond}
        </>
      )}
    </CellarPage>
  );
}

const st = StyleSheet.create({
  title: { fontFamily: fonts.terminal, fontSize: 34, lineHeight: 38, marginTop: 6 },
  post: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: cellar.line, gap: 4 },
  head: { flexDirection: 'row', gap: 10, alignItems: 'center', flexWrap: 'wrap' },
  shade: { fontFamily: fonts.monoBold, fontSize: 13, color: cellar.amber },
  signed: { fontFamily: fonts.mono, fontSize: 12, color: cellar.amber, textDecorationLine: 'underline' },
  text: { fontFamily: fonts.mono, fontSize: 14, lineHeight: 21, color: cellar.amber },
  box: { borderWidth: 1, borderColor: cellar.amberDim, padding: 12, gap: 6 },
});
