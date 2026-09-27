import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  ErrorNotice,
  Field,
  H1,
  Kicker,
  Muted,
  Page,
  Rule,
  Section,
} from '@/components/paper';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

const STATUS: Record<string, { label: string; tone: string }> = {
  tutarli: { label: 'TUTARLI', tone: paper.ok },
  geride: { label: 'GERİDE', tone: paper.inkSoft },
  tutarsiz: { label: 'TUTARSIZ', tone: paper.seal },
  butunluk_bozuk: { label: 'BÜTÜNLÜK BOZUK', tone: paper.seal },
  erisilemiyor: { label: 'ERİŞİLEMİYOR', tone: paper.seal },
};

function LedgerRecord({ rec }: { rec: any }) {
  return (
    <View style={st.record}>
      <Kicker>Kayıt #{rec.seq} · {rec.type}</Kicker>
      <Text style={st.field}>ts            {rec.ts}</Text>
      <Text style={st.field}>prev_hash     {rec.prev_hash}</Text>
      <Text style={st.field}>payload_hash  {rec.payload_hash}</Text>
      <Text style={[st.field, { color: paper.seal }]}>hash          {rec.hash}</Text>
      <Rule faint />
      <Text style={st.payload}>{JSON.stringify(rec.payload, null, 2)}</Text>
    </View>
  );
}

export default function Ledger() {
  const params = useLocalSearchParams<{ h?: string }>();
  const [verify, setVerify] = useState<any>(null);
  const [hash, setHash] = useState(params.h ?? '');
  const [error, setError] = useState<unknown>(null);
  const looked = useApi<any>(params.h ? `/ledger/records/${encodeURIComponent(params.h.trim())}` : null);
  const rec = looked.data;

  const runVerify = async () => {
    setError(null);
    try {
      setVerify(await api('/ledger/verify'));
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <Kicker>Sadece eklenebilir · hash zincirli · üç düğüm</Kicker>
      <H1>Defter</H1>
      <Muted>
        Her kayıt bir öncekinin hash&apos;ine bağlıdır: hash = sha256(prev_hash ‖ payload_hash ‖ ts ‖ type).
        Oylamayla silinen içerik de defterde kalır.
      </Muted>
      <Rule double />

      <Section title="Defteri doğrula">
        <Body style={{ marginBottom: 10 }}>
          Üç düğümün zincirleri baştan yeniden hesaplanır ve birbiriyle karşılaştırılır.
        </Body>
        <Button label="Doğrula" onPress={runVerify} />
        {verify ? (
          <View style={{ marginTop: 14, gap: 10 }}>
            <Text style={[st.verdict, { color: verify.ok ? paper.ok : paper.seal }]}>
              {verify.ok ? '✓ Üç düğüm tutarlı' : '✗ Tutarsızlık bulundu'}
            </Text>
            {verify.nodes.map((n: any) => {
              const s = STATUS[n.status] ?? { label: n.status, tone: paper.ink };
              return (
                <View key={n.url} style={[st.node, { borderColor: s.tone }]}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                    <Text style={st.nodeUrl}>{n.url.replace(/^https?:\/\//, '')}</Text>
                    <Text style={[st.nodeStatus, { color: s.tone }]}>{s.label}</Text>
                  </View>
                  <Text style={st.field}>{n.length} kayıt</Text>
                  <Muted style={{ fontSize: 14 }}>{n.message}</Muted>
                </View>
              );
            })}
          </View>
        ) : null}
      </Section>

      <Section title="Kaydı görüntüle">
        <Field
          label="Hash (en az 6 karakter)"
          value={hash}
          onChangeText={setHash}
          autoCapitalize="none"
          onSubmitEditing={() => router.setParams({ h: hash })}
        />
        <Button label="Getir" variant="secondary" onPress={() => router.setParams({ h: hash })} disabled={hash.trim().length < 6} />
        <ErrorNotice error={error ?? looked.error} />
        {rec ? <LedgerRecord rec={rec} /> : null}
      </Section>
    </Page>
  );
}

const st = StyleSheet.create({
  verdict: { fontFamily: fonts.serifBold, fontSize: 22 },
  node: { borderWidth: 1.5, padding: 12, gap: 2, backgroundColor: paper.sheet },
  nodeUrl: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.ink },
  nodeStatus: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.5 },
  record: { marginTop: 14, borderWidth: 1, borderColor: paper.ink, padding: 12, backgroundColor: paper.sheet, gap: 2 },
  field: { fontFamily: fonts.mono, fontSize: 12, color: paper.ink },
  payload: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 18, color: paper.inkSoft },
});
