import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import { CityPicker } from '@/components/city-picker';
import {
  Button,
  ErrorNotice,
  Field,
  Kicker,
  Loading,
  Muted,
  Page,
  Rule,
} from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={st.line}>
      <Text style={st.lineLabel}>{label}</Text>
      <View style={st.leader} />
      <View style={{ flexShrink: 1, alignItems: 'flex-end' }}>
        {typeof children === 'string' ? <Text style={st.lineValue}>{children}</Text> : children}
      </View>
    </View>
  );
}

const REASON: Record<string, string> = {
  KAYIT: 'kayıtla',
  ADRES_DEGISIKLIGI: 'adres değişikliğiyle',
  YAS: 'yaş',
  KATILIM: 'katılımla',
};

function Private({ p, onChanged }: { p: any; onChanged: () => void }) {
  const areas = useApi<any[]>('/areas');
  const [addr, setAddr] = useState({ city: p.address.city ?? '', district: p.address.district ?? '', address_line: p.address.address_line ?? '' });
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const memberOf = new Set(p.memberships.map((m: any) => m.scope_id));

  const toggleInterest = async (areaId: string) => {
    setError(null);
    try {
      await api(`/me/interests/${areaId}`, { method: memberOf.has(`ilgi:${areaId}`) ? 'DELETE' : 'POST' });
      onChanged();
    } catch (e) {
      setError(e);
    }
  };

  return (
    <View style={st.private}>
      <Kicker style={{ color: paper.seal }}>Yalnızca size görünür</Kicker>
      <Line label="Ad soyad">{p.full_name}</Line>
      <Line label="E-posta">{p.email}</Line>
      <Line label="Doğum tarihi">{fmtDate(p.birth_date)}</Line>
      <Line label="Adres">
        {[p.address.address_line, p.address.district, p.address.city].filter(Boolean).join(', ')}
      </Line>
      {editing ? (
        <View style={{ marginTop: 10 }}>
          <CityPicker value={addr.city} onChange={(city) => setAddr({ ...addr, city })} />
          <Field label="İlçe" value={addr.district} onChangeText={(t) => setAddr({ ...addr, district: t })} />
          <Field label="Açık adres" value={addr.address_line} onChangeText={(t) => setAddr({ ...addr, address_line: t })} />
          <Muted>Yeni şehrin kapsamında oy hakkınız 90 gün sonra doğar.</Muted>
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 8 }}>
            <Button
              label="Adresi güncelle"
              small
              onPress={async () => {
                setError(null);
                try {
                  await api('/me/address', { method: 'PUT', body: addr });
                  setEditing(false);
                  onChanged();
                } catch (e) {
                  setError(e);
                }
              }}
            />
            <Button label="Vazgeç" variant="quiet" onPress={() => setEditing(false)} />
          </View>
        </View>
      ) : (
        <View style={{ marginTop: 6 }}>
          <Button label="Adres değiştir" variant="quiet" onPress={() => setEditing(true)} />
        </View>
      )}

      <Rule faint />
      <Kicker>Kapsam üyelikleri ve oy hakkı</Kicker>
      {p.memberships.map((m: any) => (
        <Line key={m.scope_id} label={m.name}>
          <Text style={[st.lineValue, !m.has_vote_right && { color: paper.seal }]}>
            {m.has_vote_right ? 'oy hakkı var' : `oy hakkı ${fmtDate(m.vote_right_from)}`} · {REASON[m.reason] ?? m.reason}{' '}
            {fmtDate(m.since)}
          </Text>
        </Line>
      ))}

      <Rule faint />
      <Kicker style={{ marginBottom: 6 }}>İlgi alanları (katılımdan 14 gün sonra oy hakkı)</Kicker>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {(areas.data ?? []).map((a) => {
          const on = memberOf.has(`ilgi:${a.id}`);
          return (
            <Button
              key={a.id}
              small
              variant={on ? 'primary' : 'secondary'}
              checked={on}
              label={a.name}
              onPress={() => toggleInterest(a.id)}
            />
          );
        })}
      </View>
      <ErrorNotice error={error} />
    </View>
  );
}

export default function Profile() {
  const { nick } = useLocalSearchParams<{ nick: string }>();
  const { me } = useAuth();
  const isSelf = me?.nickname.toLocaleLowerCase('tr-TR') === String(nick).toLocaleLowerCase('tr-TR');
  const pub = useApi<any>(`/users/${encodeURIComponent(String(nick))}`);
  const own = useApi<any>(isSelf ? '/me/profile' : null);
  const p = isSelf ? own.data : pub.data;

  if (!p) return <Page>{pub.error ? <ErrorNotice error={pub.error} /> : <Loading />}</Page>;

  return (
    <Page>
      <View style={st.doc}>
        <View style={st.docInner}>
          <Text style={st.docHead}>MEŞVERET</Text>
          <Text style={st.docTitle}>Yurttaş Kayıt Belgesi</Text>
          <Rule double />
          <Line label="Belge no">{`⌗ ${p.id.slice(0, 8).toUpperCase()}`}</Line>
          <Line label="Takma ad">
            <Text style={[st.lineValue, { fontFamily: fonts.serifBold, fontSize: 20 }]}>{p.nickname}</Text>
          </Line>
          <Line label="Roller">{p.roles.join(' · ')}</Line>
          <Line label="Kayıt tarihi">{fmtDate(p.member_since)}</Line>
          {p.counselor_areas.length ? (
            <Line label="Müşavir olduğu alanlar">
              {p.counselor_areas.map((c: any) => `${c.name} (${c.count})`).join(', ')}
            </Line>
          ) : null}
          <Line label="Aldığı havaleler">
            {p.delegations_received.length
              ? p.delegations_received.map((d: any) => `${d.name}: ${d.count}`).join(' · ')
              : 'yok'}
          </Line>
          {p.counselor_areas.length ? (
            <View style={st.stamp} accessibilityLabel="Müşavir damgası">
              <Text style={st.stampText}>MÜŞAVİR</Text>
              <Text style={st.stampSub}>havaleyle, atamasız</Text>
            </View>
          ) : null}
          {isSelf ? <Private p={p} onChanged={own.reload} /> : null}
          {me && !isSelf && p.roles[0] !== undefined ? (
            <View style={{ marginTop: 16 }}>
              <Button
                label={`${p.nickname} adlı yurttaşa havale et`}
                variant="secondary"
                onPress={() => router.push({ pathname: '/havale', params: { target: p.nickname } })}
              />
            </View>
          ) : null}
          <Muted style={{ marginTop: 16, fontSize: 12 }}>
            Ad soyad, adres ve doğum tarihi yalnızca belge sahibine gösterilir.
          </Muted>
        </View>
      </View>
    </Page>
  );
}

const st = StyleSheet.create({
  doc: { borderWidth: 1.5, borderColor: paper.ink, padding: 4, backgroundColor: paper.sheet },
  docInner: { borderWidth: 0.5, borderColor: paper.ink, padding: 18 },
  docHead: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 4, textAlign: 'center', color: paper.inkSoft },
  docTitle: { fontFamily: fonts.serifBold, fontSize: 28, textAlign: 'center', color: paper.ink },
  line: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, paddingVertical: 6 },
  lineLabel: { fontFamily: fonts.monoMedium, fontSize: 11, letterSpacing: 1.2, textTransform: 'uppercase', color: paper.inkSoft },
  leader: { flex: 1, borderBottomWidth: 1, borderStyle: 'dotted', borderColor: paper.muted, marginBottom: 4, minWidth: 20 },
  lineValue: { fontFamily: fonts.serif, fontSize: 16, color: paper.ink, textAlign: 'right' },
  stamp: {
    position: 'absolute',
    right: 10,
    top: 8,
    borderWidth: 3,
    borderColor: paper.seal,
    paddingHorizontal: 10,
    paddingVertical: 2,
    transform: [{ rotate: '8deg' }],
    alignItems: 'center',
    opacity: 0.85,
  },
  stampText: { fontFamily: fonts.serifDisplay, fontSize: 20, letterSpacing: 3, color: paper.seal },
  stampSub: { fontFamily: fonts.mono, fontSize: 9, color: paper.seal },
  private: { marginTop: 18, borderTopWidth: 2, borderTopColor: paper.seal, paddingTop: 10 },
});
