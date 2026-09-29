/**
 * "Oyumu doğrula": kullanıcının kendi oyları, yalnızca kendisine. Gizli oyda o oturumdaki takma
 * kimlik, mühür ve açılış kayıtlarının defterdeki hash'leri; commit sunucuda yeniden hesaplanır.
 * Baskın şüphesiyle dışlandığı oylamalar da burada, yalnızca kendisine görünür.
 */
import { Link } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Button, Kicker, Muted } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { shortHash } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

const choiceText = (c: any) =>
  Array.isArray(c) ? (c.length ? c.map((x: number) => `#${x}`).join(', ') : 'hiçbiri') : String(c);

export function MyVotes({ sessionId }: { sessionId?: number }) {
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const q = sessionId ? `?session_id=${sessionId}` : '';
  const data = useApi<any>(me && open ? `/decision-hour/my-votes${q}` : null);
  if (!me) return null;
  if (!open) return <Button label="Oyumu doğrula" variant="quiet" onPress={() => setOpen(true)} />;
  const d = data.data;
  return (
    <View style={st.box} accessibilityLabel="Yalnızca size görünür">
      <Kicker style={{ color: paper.seal }}>Oyumu doğrula · yalnızca size görünür</Kicker>
      {!d ? <Muted>yükleniyor…</Muted> : null}
      {d?.votes.map((v: any) => (
        <View key={`${v.session_id}:${v.proposal_id}:${v.vote_scope.id}`} style={st.row}>
          <Text style={st.head}>
            {sessionId ? '' : `Oturum #${v.session_id} · `}№{v.proposal_id} {v.title} · {v.vote_scope.name} oylaması
          </Text>
          <Text style={st.line}>
            oyunuz: <Text style={st.strong}>{choiceText(v.choice)}</Text> ·{' '}
            {v.open ? 'açık oy (takma adınızla)' : (
              <>
                gizli oy · bu oturumdaki takma kimliğiniz <Text style={st.strong}>{v.pseudonym}</Text>
              </>
            )}
          </Text>
          <Text style={st.mono}>
            commit ⌗ {shortHash(v.commit)} · {v.verified ? 'yeniden hesaplandı, eşleşiyor' : 'EŞLEŞMİYOR'}
          </Text>
          <View style={{ flexDirection: 'row', gap: 14, flexWrap: 'wrap' }}>
            {v.commit_ledger_hash ? (
              <Link href={`/defter?h=${v.commit_ledger_hash}`} style={st.link}>
                mühür kaydı ⌗ {shortHash(v.commit_ledger_hash)}
              </Link>
            ) : null}
            {v.reveal_ledger_hash ? (
              <Link href={`/defter?h=${v.reveal_ledger_hash}`} style={st.link}>
                açılış kaydı ⌗ {shortHash(v.reveal_ledger_hash)}
              </Link>
            ) : (
              <Muted style={{ fontSize: 12 }}>açılış kaydı pencere kapanınca yazılır</Muted>
            )}
          </View>
        </View>
      ))}
      {d?.excluded.map((e: any) => (
        <View key={`x${e.session_id}:${e.proposal_id}`} style={st.row}>
          <Text style={st.head}>
            {sessionId ? '' : `Oturum #${e.session_id} · `}№{e.proposal_id} {e.title}
          </Text>
          <Text style={[st.line, { color: paper.seal }]}>
            Bu oylamada baskın şüphesiyle dışlandınız: {e.reason}
          </Text>
        </View>
      ))}
      {d && !d.votes.length && !d.excluded.length ? <Muted>Bu oturumda oy vermediniz.</Muted> : null}
      <Muted style={{ fontSize: 12 }}>
        Bu bilgiler bir makbuz işlevi görür; başkasına göstermek oyunuzu kanıtlamak demektir.
      </Muted>
    </View>
  );
}

const st = StyleSheet.create({
  box: { borderWidth: 1, borderColor: paper.seal, padding: 12, gap: 8, backgroundColor: paper.sheet },
  row: { gap: 2, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  head: { fontFamily: fonts.serifBold, fontSize: 15, color: paper.ink },
  line: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, color: paper.ink },
  strong: { fontFamily: fonts.monoBold },
  mono: { fontFamily: fonts.mono, fontSize: 12, color: paper.inkSoft },
  link: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal, textDecorationLine: 'underline' },
});
