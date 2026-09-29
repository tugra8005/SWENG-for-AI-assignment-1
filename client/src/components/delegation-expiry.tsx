/**
 * Havale uyarı şeritleri. Bildirim sistemi yoktur; şeritler girişten sonra ana sayfada, profilde ve
 * Havale sayfasında görünür.
 * - Bekleyen havale: size verilen havale kabulünüzü bekler (Kabul et / Reddet). Kabul edilene kadar
 *   ağırlığa sayılmaz, oy verende kalır.
 * - Süre: süresi yakında dolacak havaleler. Verilen havale tek tıklamayla yenilenir (süre baştan
 *   başlar, yeniden kabul gerekmez); alınan havaleyi yalnızca veren yenileyebilir.
 */
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { Button, ErrorNotice, Kicker, Nick } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

export function daysLeftLabel(n: number | null | undefined): string {
  if (n == null) return 'süresiz';
  if (n <= 0) return 'bugün doluyor';
  return `${n} gün kaldı`;
}

export const renewDelegation = (areaId: string | null) =>
  api('/delegations/renew', { method: 'POST', body: { area_id: areaId } });

export const acceptDelegation = (id: number) => api(`/delegations/requests/${id}/accept`, { method: 'POST' });
export const rejectDelegation = (id: number) => api(`/delegations/requests/${id}/reject`, { method: 'POST' });

/** İki şerit tek veriden. ``data`` verilmezse ``/delegations`` kendisi okunur (ana sayfa). */
export function DelegationNotices({ data, onChanged }: { data?: any; onChanged?: () => void }) {
  const { me } = useAuth();
  const own = useApi<any>(me && !data ? '/delegations' : null);
  const d = data ?? own.data;
  if (!me || !d) return null;
  const changed = () => {
    if (!data) own.reload();
    onChanged?.();
  };
  return (
    <>
      <PendingDelegationStrip data={d} onChanged={changed} />
      <DelegationExpiryStrip data={d} onRenewed={changed} />
    </>
  );
}

/** Size verilen ve kabulünüzü bekleyen havaleler. */
export function PendingDelegationStrip({ data: d, onChanged }: { data: any; onChanged: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const pending: any[] = d.pending_received ?? [];
  if (!pending.length) return null;
  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e);
    }
  };
  return (
    <View style={st.strip} accessibilityRole="alert">
      <Kicker style={{ color: paper.seal }}>Size verilen havale · kabulünüzü bekliyor</Kicker>
      {pending.map((r) => (
        <View key={r.id} style={st.row}>
          <Text style={[st.text, { flex: 1, minWidth: 220 }]}>
            <Text style={st.strong}><Nick>{r.from}</Nick></Text> size <Text style={st.strong}>{r.area_name}</Text>{' '}
            için havale verdi. Kabul ederseniz oyu size akar ve bu alandaki oyunuz açık olur. Son kabul:{' '}
            {fmtDate(r.decide_by)}; kabul edilmezse düşer.
          </Text>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Button small label="Kabul et" onPress={() => act(() => acceptDelegation(r.id))} disabled={d.locked} />
            <Button small variant="secondary" label="Reddet" onPress={() => act(() => rejectDelegation(r.id))} />
          </View>
        </View>
      ))}
      {d.locked ? (
        <Text style={st.text}>Karar Saati penceresi açık: kabul pencere kapanınca yapılabilir.</Text>
      ) : null}
      <ErrorNotice error={error} />
    </View>
  );
}

export function DelegationExpiryStrip({ data: d, onRenewed }: { data: any; onRenewed?: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const given: any[] = d.expiring_given ?? [];
  const received: any[] = d.expiring_received ?? [];
  if (!given.length && !received.length) return null;

  const renew = async (areaId: string | null) => {
    setError(null);
    try {
      await renewDelegation(areaId);
      onRenewed?.();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <View style={st.strip} accessibilityRole="alert">
      <Kicker style={{ color: paper.seal }}>Havale süresi · {d.warning_days} gün içinde dolacaklar</Kicker>
      {given.map((g) => (
        <View key={`g-${g.area_id ?? 'genel'}`} style={st.row}>
          <Text style={[st.text, { flex: 1, minWidth: 200 }]}>
            <Text style={st.strong}>{g.area_name}</Text> havaleniz ({g.target}) {fmtDate(g.expires_at)} tarihinde
            doluyor, {daysLeftLabel(g.days_left)}. Dolunca oyunuz size döner.
          </Text>
          <Button small label="Yenile" onPress={() => renew(g.area_id)} disabled={d.locked} />
        </View>
      ))}
      {received.length ? (
        <Text style={st.text}>
          Size verilen {received.length} havalenin süresi doluyor:{' '}
          {received.map((r) => `${r.from} (${r.area_name}, ${daysLeftLabel(r.days_left)})`).join(' · ')}.
          Yenilemek havaleyi verenin elindedir.
        </Text>
      ) : null}
      <ErrorNotice error={error} />
    </View>
  );
}

const st = StyleSheet.create({
  strip: {
    borderWidth: 1,
    borderColor: paper.seal,
    borderLeftWidth: 6,
    backgroundColor: paper.sheet,
    paddingVertical: 10,
    paddingHorizontal: 14,
    gap: 8,
    marginVertical: 12,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap' },
  text: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 22, color: paper.ink },
  strong: { fontFamily: fonts.serifBold },
});
