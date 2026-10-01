import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import {
  Body,
  Button,
  ChoiceChip,
  Columns,
  ErrorNotice,
  Field,
  H1,
  InfoNotice,
  Kicker,
  Muted,
  Page,
  PageHead,
  Section,
  useWide,
} from '@/components/paper';
import { AreaGroups } from '@/components/area-groups';
import { DelegationNotices, daysLeftLabel, renewDelegation } from '@/components/delegation-expiry';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export default function Delegations() {
  const { me } = useAuth();
  const params = useLocalSearchParams<{ target?: string }>();
  const mine = useApi<any>(me ? '/delegations' : null);
  const wide = useWide();
  const areas = useApi<any[]>('/areas');
  const [target, setTarget] = useState(params.target ?? '');
  const [area, setArea] = useState<string>('');
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!me) {
    return (
      <Page>
        <H1>Havale</H1>
        <InfoNotice>Havale vermek için giriş yapın.</InfoNotice>
      </Page>
    );
  }
  const d = mine.data;

  const run = async (fn: () => Promise<any>) => {
    setError(null);
    setNotice(null);
    try {
      const r = await fn();
      if (r?.message) setNotice(r.message);
      mine.reload();
    } catch (e) {
      setError(e);
    }
  };
  const give = () =>
    run(async () => {
      const r = await api('/delegations', { method: 'POST', body: { target, area_id: area || null } });
      setTarget('');
      return r;
    });
  const cancel = (id: number) => run(() => api(`/delegations/requests/${id}`, { method: 'DELETE' }));
  const giveBack = (from: string, areaId: string | null) =>
    run(() => api('/delegations/return', { method: 'POST', body: { giver: from, area_id: areaId } }));
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

  const lists = (
    <>
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
        {d?.pending_given.map((r: any) => (
          <View key={`p-${r.id}`} style={st.row}>
            <View style={{ flex: 1, gap: 2 }}>
              <Kicker>{r.area_name} · bekliyor</Kicker>
              <Text style={st.chain}>{r.target}</Text>
              <Muted style={{ fontSize: 13 }}>
                kabul edilene kadar oyunuz sizde · son kabul {fmtDate(r.decide_by)}
              </Muted>
            </View>
            <Button label="Geri al" variant="quiet" onPress={() => cancel(r.id)} />
          </View>
        ))}
        {d?.outcomes.map((o: any) => (
          <View key={`o-${o.id}`} style={st.row}>
            <View style={{ flex: 1, gap: 2 }}>
              <Kicker>{o.area_name}</Kicker>
              <Text style={[st.expiry, { color: paper.seal }]}>
                {o.target} · {o.label} · {fmtDate(o.at)}
              </Text>
            </View>
          </View>
        ))}
        {d && d.given.length === 0 && d.pending_given.length === 0 ? (
          <Muted>Yürürlükte havaleniz yok; oyunuzu kendiniz kullanıyorsunuz.</Muted>
        ) : null}
      </Section>

      <Section title="Size gelen havaleler">
        {d?.received.map((r: any) => (
          <Body key={r.area_id ?? 'genel'}>
            {r.area_name}: <Text style={{ fontFamily: fonts.monoBold }}>{r.count}</Text>
          </Body>
        ))}
        {d?.received_list.map((r: any) => (
          <View key={`${r.from}-${r.area_id ?? 'genel'}`} style={[st.row, { paddingVertical: 6 }]}>
            <Text style={[st.expiry, { flex: 1 }, r.expiring && { color: paper.seal }]}>
              {r.from} · {r.area_name} · bitiş {fmtDate(r.expires_at)} · {daysLeftLabel(r.days_left)}
            </Text>
            <Button label="İade et" variant="quiet" onPress={() => giveBack(r.from, r.area_id)} disabled={d?.locked} />
          </View>
        ))}
        {d && d.received.length === 0 ? <Muted>Size doğrudan havale veren yok.</Muted> : null}
      </Section>
    </>
  );
  const newDelegation = (
    <>
      <Section title="Yeni havale">
        <Field label="Takma ad" value={target} onChangeText={setTarget} autoCapitalize="none" />
        <View style={{ marginBottom: 14, gap: 8 }} accessibilityRole="radiogroup" accessibilityLabel="Alan">
          <Kicker>Alan</Kicker>
          <ChoiceChip label="Genel (tüm alanlar)" on={area === ''} onPress={() => setArea('')} />
          <AreaGroups
            areas={areas.data ?? []}
            renderItem={(a) => <ChoiceChip label={a.name} on={area === a.id} onPress={() => setArea(a.id)} />}
          />
        </View>
        <ErrorNotice error={error} />
        {notice ? <InfoNotice>{notice}</InfoNotice> : null}
        <Button label="Havale et" onPress={give} disabled={!target.trim() || d?.locked} />
        <Muted style={{ marginTop: 8, fontSize: 13 }}>
          Döngü oluşturacak havale reddedilir (R4); mirasla alt alanlarda oluşan döngüler de denetlenir.
        </Muted>
      </Section>
    </>
  );

  return (
    <Page>
      <PageHead kicker="Oy hakkının devri" title="Havale">
        <Muted>
          Oyunuzu genel olarak ya da bir alan için güvendiğiniz birine devredebilirsiniz. Alan havalesi o
          alanda genel havaleyi ezer; alt alanlar üst alanın havalesini miras alır. Zincir son kişiye kadar
          akar. Havale ettiğiniz alanda kendiniz oy kullanamazsınız. Her havale kabul edildiği ya da
          yenilendiği andan {d?.havale_suresi_gun ?? 180} gün sonra kendiliğinden sona erer ve oy size döner
          (havale_suresi); süreyi dilediğiniz an baştan başlatabilirsiniz.
        </Muted>
        <Muted style={{ marginTop: 6 }}>
          Havale, alan kişi kabul edince yürürlüğe girer: temsilcinin oyu açıktır, bu yüzden kimse onayı
          olmadan temsilci yapılamaz. Kabul edilene kadar oyunuz sizde kalır; {d?.kabul_suresi_gun ?? 7} gün
          içinde kabul edilmezse havale düşer (havale_kabul_suresi). Alan kişi kabul ettiği havaleyi
          istediği zaman iade edebilir.
        </Muted>
      </PageHead>
      {d ? <DelegationNotices data={d} onChanged={mine.reload} /> : null}
      {d?.refuses ? (
        <InfoNotice>Havale kabul etmiyorsunuz; size yeni havale verilemez. Profilinizden değiştirebilirsiniz.</InfoNotice>
      ) : null}
      {d?.locked ? (
        <InfoNotice>
          <Text style={{ fontFamily: fonts.serifBold, color: paper.seal }}>
            Karar Saati penceresi açık: havale grafı bu oturum için kilitli.
          </Text>
        </InfoNotice>
      ) : null}
      {/* Geniş ekranda havaleler ana sütunda, yeni havale formu yan sütunda. */}
      {wide ? (
        <Columns sideWidth={400} main={lists} side={newDelegation} />
      ) : (
        <>
          {lists}
          {newDelegation}
        </>
      )}
    </Page>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline },
  chain: { fontFamily: fonts.monoMedium, fontSize: 15, color: paper.ink },
  expiry: { fontFamily: fonts.mono, fontSize: 12, color: paper.inkSoft },
});
