import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  ErrorNotice,
  Field,
  Kicker,
  Muted,
  Page,
  PageHead,
  Rule,
  Section,
  Split,
  useWide,
} from '@/components/paper';
import { describeArticleValue, fmtDateTime, shortHash } from '@/lib/format';
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

function SilentChange({ h }: { h: any }) {
  const lines: string[] = [];
  if (h.alanlar.includes('deger')) {
    lines.push(
      `kayıtta ${describeArticleValue(h.tur, h.kayittaki)} → bulunan ${h.bulunan ? describeArticleValue(h.tur, h.bulunan) : 'madde yok'}`,
    );
  }
  if (h.alanlar.includes('degistirilemez')) lines.push('değiştirilemez bayrağı değişmişti');
  if (h.alanlar.includes('izinli_aralik')) {
    lines.push(`izinli aralık: ${h.kayittaki_aralik ?? '—'} → ${h.bulunan_aralik ?? '—'} (kod düzeyinde)`);
  }
  const failed = h.geri_alinamayan?.length;
  return (
    <View style={st.silent}>
      <Text style={st.silentHead}>
        {h.madde} · #{h.oturum} numaralı oturumun {h.asama === 'acilis' ? 'açılışında' : 'kapanışında'} ·{' '}
        {fmtDateTime(h.tespit_zamani)}
      </Text>
      {lines.map((l) => (
        <Text key={l} style={st.silentText}>
          {l}
        </Text>
      ))}
      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <Text style={[st.nodeStatus, { color: failed ? paper.seal : paper.ok }]}>
          {failed ? 'GERİ ALINAMADI · kod düzeyinde' : 'GERİ ALINDI · son oylanmış hâline döndü'}
        </Text>
        <Text
          style={st.silentLink}
          accessibilityRole="link"
          onPress={() => router.setParams({ h: h.hash })}
        >
          defterde: ⌗ {shortHash(h.hash)}
        </Text>
      </View>
    </View>
  );
}

/** Çalışan kodun yönetmeliği ile defterdeki son YONETMELIK_DURUMU kaydının karşılaştırması ve
 * defterin tamamındaki oylamasız değişiklikler (kalıcı liste; hiç boşalmaz). */
function RegulationIntegrity({ r }: { r: any }) {
  const tone = r.status === 'tutarli' ? paper.ok : paper.seal;
  const label = { tutarli: 'TUTARLI', farkli: 'FARKLI', kayit_yok: 'KAYIT YOK' }[r.status as string] ?? r.status;
  return (
    <View style={[st.node, { borderColor: tone }]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <Text style={st.nodeUrl}>Yönetmelik bütünlüğü</Text>
        <Text style={[st.nodeStatus, { color: tone }]}>{label}</Text>
      </View>
      <Muted style={{ fontSize: 14 }}>{r.message}</Muted>
      <Text style={st.field}>
        çalışan kod ⌗ {shortHash(r.current_hash)} · defter ⌗ {shortHash(r.recorded_hash)}
        {r.record_seq ? ` (kayıt #${r.record_seq})` : ''}
      </Text>
      {r.differences?.length ? (
        <Text style={[st.field, { color: paper.seal }]}>farklı maddeler: {r.differences.join(', ')}</Text>
      ) : null}
      <Rule faint />
      <Kicker>Geçmişte tespit edilen oylamasız değişiklikler</Kicker>
      {r.history == null ? (
        <Muted style={{ fontSize: 14 }}>Defterdeki geçmiş okunamadı.</Muted>
      ) : r.history.length ? (
        r.history.map((h: any) => <SilentChange key={h.hash} h={h} />)
      ) : (
        <Muted style={{ fontSize: 14 }}>
          Henüz yok. Liste defterdeki kayıtlardan kurulur ve hiç boşalmaz.
        </Muted>
      )}
    </View>
  );
}

/** İki satırlık başlık: zincir ve yönetmelik ayrı ayrı. Biri bozuksa ikisi de bordo, onay işareti yok. */
function Verdict({ chainOk, regulation }: { chainOk: boolean; regulation?: string }) {
  const regOk = regulation === 'tutarli';
  const allOk = chainOk && (regulation === undefined || regOk);
  const tone = allOk ? paper.ok : paper.seal;
  const regLabel = { tutarli: 'tutarlı', farkli: 'FARKLI', kayit_yok: 'KAYIT YOK' }[regulation ?? ''] ?? regulation;
  return (
    <View accessibilityRole="summary" style={{ gap: 2 }}>
      <Text style={[st.verdict, { color: tone }]}>
        {allOk ? '✓ ' : ''}Zincir: {chainOk ? 'tutarlı' : 'TUTARSIZ'}
      </Text>
      {regulation !== undefined ? (
        <Text style={[st.verdict, { color: tone }]}>
          {allOk ? '✓ ' : ''}Yönetmelik: {regLabel}
        </Text>
      ) : null}
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
  const wide = useWide();

  const runVerify = async () => {
    setError(null);
    try {
      setVerify(await api('/ledger/verify'));
    } catch (e) {
      setError(e);
    }
  };

  const verifySection = (
    <>
      <Section title="Defteri doğrula">
        <Body style={{ marginBottom: 10 }}>
          Üç düğümün zincirleri baştan yeniden hesaplanır ve birbiriyle karşılaştırılır. Çalışan kodun
          uyguladığı yönetmelik, defterdeki son yönetmelik kaydının hash&apos;iyle karşılaştırılır; Karar
          Saati açılış ve kapanışlarında tespit edilip geri alınan oylamasız değişiklikler defterin
          tamamından listelenir.
        </Body>
        <Button label="Doğrula" onPress={runVerify} />
        {verify ? (
          <View style={{ marginTop: 14, gap: 10 }}>
            <Verdict chainOk={verify.ok} regulation={verify.yonetmelik?.status} />
            {verify.yonetmelik ? <RegulationIntegrity r={verify.yonetmelik} /> : null}
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
    </>
  );
  const lookupSection = (
    <>
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
    </>
  );

  return (
    <Page>
      <PageHead kicker="Sadece eklenebilir · hash zincirli · üç düğüm" title="Defter">
        <Muted>
          Her kayıt bir öncekinin hash&apos;ine bağlıdır: hash = sha256(prev_hash ‖ payload_hash ‖ ts ‖ type).
          Oylamayla silinen içerik de defterde kalır.
        </Muted>
      </PageHead>
      {wide ? (
        <Split left={verifySection} right={lookupSection} />
      ) : (
        <>
          {verifySection}
          {lookupSection}
        </>
      )}
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
  silent: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 10, paddingVertical: 4, gap: 2, marginTop: 4 },
  silentHead: { fontFamily: fonts.monoMedium, fontSize: 12, color: paper.ink },
  silentText: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.ink },
  silentLink: { fontFamily: fonts.mono, fontSize: 12, color: paper.seal, textDecorationLine: 'underline' },
});
