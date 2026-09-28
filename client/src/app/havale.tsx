import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  Choice,
  ErrorNotice,
  Field,
  H1,
  InfoNotice,
  Kicker,
  Muted,
  Page,
  Rule,
  Section,
} from '@/components/paper';
import { DelegationExpiryStrip, daysLeftLabel, renewDelegation } from '@/components/delegation-expiry';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function Delegations() {
  const { me } = useAuth();
  const params = useLocalSearchParams<{ target?: string }>();
  const mine = useApi<any>(me ? '/delegations' : null);
  const areas = useApi<any[]>('/areas');
  const [target, setTarget] = useState(params.target ?? '');
  const [area, setArea] = useState<string>('');
  const [error, setError] = useState<unknown>(null);

  if (!me) {
    return (
      <Page>
        <H1>Havale</H1>
        <InfoNotice>Havale vermek için giriş yapın.</InfoNotice>
      </Page>
    );
  }
  const d = mine.data;

  const give = async () => {
    setError(null);
    try {
      await api('/delegations', { method: 'POST', body: { target, area_id: area || null } });
      setTarget('');
      mine.reload();
    } catch (e) {
      setError(e);
    }
  };
  const renew = async (areaId: string | null) => {
    setError(null);
    try {
      await renewDelegation(areaId);
      mine.reload();
    } catch (e) {
      setError(e);
    }
  };
  const revoke = async (areaId: string | null) => {
    setError(null);
    try {
      await api('/delegations', { method: 'DELETE', query: { area_id: areaId ?? '' } });
      mine.reload();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <Kicker>Oy hakkının devri</Kicker>
      <H1>Havale</H1>
      <Muted>
        Oyunuzu genel olarak ya da bir alan için güvendiğiniz birine devredebilirsiniz. Alan havalesi o
        alanda genel havaleyi ezer; alt alanlar üst alanın havalesini miras alır. Zincir son kişiye kadar
        akar. Havale ettiğiniz alanda kendiniz oy kullanamazsınız. Her havale verildiği ya da
        yenilendiği andan {d?.havale_suresi_gun ?? 180} gün sonra kendiliğinden sona erer ve oy size döner
        (havale_suresi); süreyi dilediğiniz an baştan başlatabilirsiniz.
      </Muted>
      <Rule double />
      {d ? <DelegationExpiryStrip data={d} onRenewed={mine.reload} /> : null}
      {d?.locked ? (
        <InfoNotice>
          <Text style={{ fontFamily: fonts.serifBold, color: paper.seal }}>
            Karar Saati penceresi açık: havale grafı bu oturum için kilitli.
          </Text>
        </InfoNotice>
      ) : null}

      <Section title="Verdiğiniz havaleler">
        {d?.given.map((g: any) => (
          <View key={g.area_id ?? 'genel'} style={st.row}>
            <View style={{ flex: 1, gap: 2 }}>
              <Kicker>{g.area_name}</Kicker>
              <Text style={st.chain}>{g.chain.join('  →  ')}</Text>
              <Muted style={{ fontSize: 13 }}>
                zincir {g.terminal} adlı yurttaşta bitiyor · verildi {fmtDate(g.since)}
              </Muted>
              <Text style={[st.expiry, g.expiring && { color: paper.seal }]}>
                bitiş {fmtDate(g.expires_at)} · {daysLeftLabel(g.days_left)}
              </Text>
            </View>
            <View style={{ alignItems: 'flex-end', gap: 8 }}>
              <Button label="Yenile" variant="quiet" onPress={() => renew(g.area_id)} disabled={d?.locked} />
              <Button label="Geri al" variant="quiet" onPress={() => revoke(g.area_id)} />
            </View>
          </View>
        ))}
        {d && d.given.length === 0 ? <Muted>Havale vermediniz; oyunuzu kendiniz kullanıyorsunuz.</Muted> : null}
      </Section>

      <Section title="Size gelen havaleler">
        {d?.received.map((r: any) => (
          <Body key={r.area_id ?? 'genel'}>
            {r.area_name}: <Text style={{ fontFamily: fonts.monoBold }}>{r.count}</Text>
          </Body>
        ))}
        {d?.received_list.map((r: any) => (
          <Text key={`${r.from}-${r.area_id ?? 'genel'}`} style={[st.expiry, r.expiring && { color: paper.seal }]}>
            {r.from} · {r.area_name} · bitiş {fmtDate(r.expires_at)} · {daysLeftLabel(r.days_left)}
          </Text>
        ))}
        {d && d.received.length === 0 ? <Muted>Size doğrudan havale veren yok.</Muted> : null}
      </Section>

      <Section title="Yeni havale">
        <Field label="Takma ad" value={target} onChangeText={setTarget} autoCapitalize="none" />
        <Choice
          label="Alan"
          value={area}
          options={[{ value: '', label: 'Genel (tüm alanlar)' }, ...(areas.data ?? []).map((a) => ({ value: a.id, label: a.name }))]}
          onChange={setArea}
        />
        <ErrorNotice error={error} />
        <Button label="Havale et" onPress={give} disabled={!target.trim() || d?.locked} />
        <Muted style={{ marginTop: 8, fontSize: 13 }}>
          Döngü oluşturacak havale reddedilir (R4); mirasla alt alanlarda oluşan döngüler de denetlenir.
        </Muted>
      </Section>
    </Page>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  chain: { fontFamily: fonts.monoMedium, fontSize: 15, color: paper.ink },
  expiry: { fontFamily: fonts.mono, fontSize: 12, color: paper.inkSoft },
});
