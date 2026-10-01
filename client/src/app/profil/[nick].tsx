import { router, useLocalSearchParams } from 'expo-router';
import { createContext, useContext, useState } from 'react';
import { StyleSheet, Text, type TextStyle, View, useWindowDimensions } from 'react-native';

import { api } from '@/api/client';
import { AreaGroups } from '@/components/area-groups';
import { CityPicker } from '@/components/city-picker';
import { DelegationNotices, daysLeftLabel } from '@/components/delegation-expiry';
import { MyVotes } from '@/components/my-votes';
import {
  Button,
  ErrorNotice,
  Field,
  Kicker,
  Loading,
  Muted,
  Nick,
  Page,
  Rule,
  useWide,
} from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { fmtDate } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

const StackedCtx = createContext(false);

/** Satırın değeri: yan yana düzende sağa, yığılmış düzende sola yaslı. */
function Value({ style, children }: { style?: TextStyle | (TextStyle | false | null | undefined)[]; children: React.ReactNode }) {
  const stacked = useContext(StackedCtx);
  return <Text style={[st.lineValue, stacked && { textAlign: 'left' }, StyleSheet.flatten(style)]}>{children}</Text>;
}

/** Noktalı satır. Telefonda etiket ya da değer tek satıra sığmazsa ikisi alt alta yığılır. */
function Line({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  const { width } = useWindowDimensions();
  const [stacked, setStacked] = useState(false);
  const narrow = width < 560;
  const value = typeof children === 'string' ? <Value>{children}</Value> : children;
  if (narrow && stacked) {
    return (
      <StackedCtx.Provider value>
        <View style={st.lineStacked}>
          <Text style={st.lineLabel}>{label}</Text>
          <View style={st.stackedValue}>{value}</View>
        </View>
      </StackedCtx.Provider>
    );
  }
  return (
    <View
      style={st.line}
      onLayout={(e) => {
        // Tek satırlık satır 34–38 px (dolgu + 22/26 px satır yüksekliği); değer iki satıra kırılırsa
        // 56 px'i bulur. Bir kez yığılınca öyle kalır.
        if (narrow && e.nativeEvent.layout.height > 46) setStacked(true);
      }}
    >
      <Text style={st.lineLabel}>{label}</Text>
      <View style={st.leader} />
      <View style={{ flexShrink: 1, alignItems: 'flex-end' }}>{value}</View>
    </View>
  );
}

const REASON: Record<string, string> = {
  KAYIT: 'kayıtla',
  ADRES_DEGISIKLIGI: 'adres değişikliğiyle',
  KATILIM: 'katılımla',
};

/** Üyeliğin nasıl doğduğu. Yaş grubu üyeliği kayıt gününde başladıysa "kayıtla" denir. */
function reasonLabel(m: any, memberSince: string): string {
  if (m.reason === 'YAS') {
    return fmtDate(m.since) === fmtDate(memberSince) ? 'kayıtla' : 'yaş grubuna geçişle';
  }
  return REASON[m.reason] ?? m.reason;
}

function Private({ p, onChanged, part }: { p: any; onChanged: () => void; part?: 'identity' | 'activity' }) {
  const areas = useApi<any[]>('/areas');
  const [addr, setAddr] = useState({ city: p.address.city ?? '', district: p.address.district ?? '', address_line: p.address.address_line ?? '' });
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const memberOf = new Set(p.memberships.map((m: any) => m.scope_id));

  const toggleRefusal = async () => {
    setError(null);
    try {
      await api('/delegations/preference', { method: 'PUT', body: { refuses: !p.refuses_delegations } });
      onChanged();
    } catch (e) {
      setError(e);
    }
  };

  const toggleInterest = async (areaId: string) => {
    setError(null);
    try {
      await api(`/me/interests/${areaId}`, { method: memberOf.has(`ilgi:${areaId}`) ? 'DELETE' : 'POST' });
      onChanged();
    } catch (e) {
      setError(e);
    }
  };

  const delegations = (
    <>
      <Kicker style={{ marginTop: 6 }}>Verdiğiniz havaleler (kalan süre)</Kicker>
      {p.delegations_given.length ? (
        p.delegations_given.map((g: any) => (
          <Line key={`g-${g.area_id ?? 'genel'}`} label={<>{g.area_name} → <Nick>{g.target}</Nick></>}>
            <Value style={[g.expiring && { color: paper.seal }]}>
              {fmtDate(g.expires_at)} · {daysLeftLabel(g.days_left)}
            </Value>
          </Line>
        ))
      ) : (
        <Muted style={{ fontSize: 14 }}>Havale vermediniz.</Muted>
      )}
      <Kicker style={{ marginTop: 6 }}>Aldığınız havaleler (kalan süre)</Kicker>
      {p.delegations_received_list.length ? (
        p.delegations_received_list.map((r: any) => (
          <Line key={`r-${r.from}-${r.area_id ?? 'genel'}`} label={<><Nick>{r.from}</Nick> · {r.area_name}</>}>
            <Value style={[r.expiring && { color: paper.seal }]}>
              {fmtDate(r.expires_at)} · {daysLeftLabel(r.days_left)}
            </Value>
          </Line>
        ))
      ) : (
        <Muted style={{ fontSize: 14 }}>Size doğrudan havale veren yok.</Muted>
      )}
      <View style={{ marginTop: 10, gap: 4 }}>
        <Button
          small
          variant={p.refuses_delegations ? 'primary' : 'secondary'}
          checked={p.refuses_delegations}
          label="Havale kabul etmiyorum"
          onPress={toggleRefusal}
        />
        <Muted style={{ fontSize: 13 }}>
          Açıkken size yeni havale verilemez. Bekleyen ve kabul ettiğiniz havaleler kendiliğinden düşmez;
          onları Havale sayfasında reddedebilir ya da iade edebilirsiniz.
        </Muted>
      </View>
    </>
  );
  const identity = (
    <>
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
    </>
  );
  const votes = (
    <>
      <Kicker style={{ marginTop: 6 }}>Oylarım</Kicker>
      <MyVotes />
    </>
  );
  const memberships = (
    <>
      <Kicker>Kapsam üyelikleri ve oy hakkı</Kicker>
      {p.memberships.map((m: any) => (
        <Line key={m.scope_id} label={m.name}>
          <Value style={[!m.has_vote_right && { color: paper.seal }]}>
            {m.has_vote_right ? 'oy hakkı var' : `oy hakkı ${fmtDate(m.vote_right_from)}`} ·{' '}
            {reasonLabel(m, p.member_since)} {fmtDate(m.since)}
          </Value>
        </Line>
      ))}
    </>
  );
  const interestList = (
    <>
      <Kicker style={{ marginBottom: 6 }}>İlgi alanları (katılımdan 14 gün sonra oy hakkı)</Kicker>
      <AreaGroups
        areas={areas.data ?? []}
        renderItem={(a) => {
          const on = memberOf.has(`ilgi:${a.id}`);
          return (
            <Button
              small
              variant={on ? 'primary' : 'secondary'}
              checked={on}
              label={a.name}
              onPress={() => toggleInterest(a.id)}
            />
          );
        }}
      />
    </>
  );

  // Geniş ekranda kimlik bilgileri belgede, kayıtlar (havale, oy, üyelik, ilgi) yanındaki belgede durur.
  if (part === 'identity') {
    return (
      <View style={st.private}>
        <Kicker style={{ color: paper.seal }}>Yalnızca size görünür</Kicker>
        {identity}
        <ErrorNotice error={error} />
      </View>
    );
  }
  if (part === 'activity') {
    return (
      <View style={{ gap: 2 }}>
        {delegations}
        <Rule faint />
        {votes}
        <Rule faint />
        {memberships}
        <Rule faint />
        {interestList}
        <ErrorNotice error={error} />
      </View>
    );
  }
  return (
    <View style={st.private}>
      <Kicker style={{ color: paper.seal }}>Yalnızca size görünür</Kicker>
      {delegations}
      <Rule faint />
      {identity}
      {votes}
      <Rule faint />
      {memberships}
      <Rule faint />
      {interestList}
      <ErrorNotice error={error} />
    </View>
  );
}

/** Dar ekranda mühür başlığın üstüne binmez: başlığın altında, sağda ve daha küçük durur. */
function CounselorStamp({ small }: { small?: boolean }) {
  return (
    <View style={small ? st.stampSmall : st.stamp} accessibilityLabel="Müşavir damgası">
      <Text style={[st.stampText, small && { fontSize: 15, letterSpacing: 2 }]}>MÜŞAVİR</Text>
      <Text style={st.stampSub}>havaleyle, atamasız</Text>
    </View>
  );
}

export default function Profile() {
  const { nick } = useLocalSearchParams<{ nick: string }>();
  const { width } = useWindowDimensions();
  const narrow = width < 560;
  const wide = useWide();
  const { me } = useAuth();
  const isSelf = me?.nickname.toLocaleLowerCase('tr-TR') === String(nick).toLocaleLowerCase('tr-TR');
  const pub = useApi<any>(`/users/${encodeURIComponent(String(nick))}`);
  const own = useApi<any>(isSelf ? '/me/profile' : null);
  const p = isSelf ? own.data : pub.data;

  if (!p) return <Page>{pub.error ? <ErrorNotice error={pub.error} /> : <Loading />}</Page>;

  const doc = (part?: 'identity') => (
    <View style={st.doc}>
      <View style={st.docInner}>
        <Text style={st.docHead}>MEŞVERET</Text>
        <Text style={st.docTitle}>Yurttaş Kayıt Belgesi</Text>
        {p.counselor_areas.length && narrow ? <CounselorStamp small /> : null}
        <Rule double />
        <Line label="Belge no">{`⌗ ${p.id.slice(0, 8).toUpperCase()}`}</Line>
        <Line label="Takma ad">
          <Value style={{ fontFamily: fonts.serifBold, fontSize: 20, lineHeight: 26 }}>{p.nickname}</Value>
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
        {p.counselor_areas.length && !narrow ? <CounselorStamp /> : null}
        {isSelf ? <Private p={p} onChanged={own.reload} part={part} /> : null}
        {me && !isSelf && p.roles[0] !== undefined ? (
          <View style={{ marginTop: 16 }}>
            <Button
              label="Bu yurttaşa havale et"
              variant="secondary"
              disabled={p.refuses_delegations}
              onPress={() => router.push({ pathname: '/havale', params: { target: p.nickname } })}
            />
            {p.refuses_delegations ? (
              <Muted style={{ fontSize: 13, marginTop: 4 }}>Bu yurttaş havale kabul etmiyor.</Muted>
            ) : (
              <Muted style={{ fontSize: 13, marginTop: 4 }}>Havale, bu yurttaş kabul edince yürürlüğe girer.</Muted>
            )}
          </View>
        ) : null}
        <Muted style={{ marginTop: 16, fontSize: 12 }}>
          Ad soyad, adres ve doğum tarihi yalnızca belge sahibine gösterilir.
        </Muted>
      </View>
    </View>
  );
  const notices = isSelf ? <DelegationNotices data={p} onChanged={own.reload} /> : null;

  // Geniş ekranda kendi profiline bakan kişi iki belge görür: solda kimlik belgesi, sağda yalnızca
  // ona görünen kayıtlar. Başkasının profili okuma sütununda tek belgedir.
  if (wide && isSelf) {
    return (
      <Page>
        {notices}
        <View style={{ flexDirection: 'row', gap: 28, alignItems: 'flex-start' }}>
          <View style={{ flex: 1 }}>{doc('identity')}</View>
          <View style={[st.doc, { flex: 1 }]}>
            <View style={st.docInner}>
              <Text style={st.docHead}>MEŞVERET</Text>
              <Text style={st.docTitle}>Kişisel Kayıtlar</Text>
              <Kicker style={{ color: paper.seal, textAlign: 'center' }}>yalnızca size görünür</Kicker>
              <Rule double />
              <Private p={p} onChanged={own.reload} part="activity" />
            </View>
          </View>
        </View>
      </Page>
    );
  }

  return (
    <Page reading={wide}>
      {notices}
      {doc()}
    </Page>
  );
}

const st = StyleSheet.create({
  doc: { borderWidth: 1.5, borderColor: paper.ink, padding: 4, backgroundColor: paper.sheet },
  docInner: { borderWidth: 0.5, borderColor: paper.ink, padding: 18 },
  docHead: { fontFamily: fonts.monoMedium, fontSize: 12, letterSpacing: 4, textAlign: 'center', color: paper.inkSoft },
  docTitle: { fontFamily: fonts.serifBold, fontSize: 28, textAlign: 'center', color: paper.ink },
  line: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, paddingVertical: 6 },
  lineLabel: { fontFamily: fonts.monoMedium, fontSize: 11, lineHeight: 16, letterSpacing: 1.2, textTransform: 'uppercase', color: paper.inkSoft },
  lineStacked: { paddingVertical: 6, gap: 2 },
  stackedValue: {
    alignItems: 'flex-start',
    borderBottomWidth: 1,
    borderStyle: 'dotted',
    borderColor: paper.muted,
    paddingBottom: 3,
  },
  leader: { flex: 1, borderBottomWidth: 1, borderStyle: 'dotted', borderColor: paper.muted, marginBottom: 4, minWidth: 20 },
  lineValue: { fontFamily: fonts.serif, fontSize: 16, lineHeight: 22, color: paper.ink, textAlign: 'right' },
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
  stampSmall: {
    alignSelf: 'flex-end',
    marginTop: 6,
    borderWidth: 2,
    borderColor: paper.seal,
    paddingHorizontal: 8,
    paddingVertical: 1,
    transform: [{ rotate: '4deg' }],
    alignItems: 'center',
    opacity: 0.85,
  },
  stampText: { fontFamily: fonts.serifDisplay, fontSize: 20, letterSpacing: 3, color: paper.seal },
  stampSub: { fontFamily: fonts.mono, fontSize: 9, color: paper.seal },
  private: { marginTop: 18, borderTopWidth: 2, borderTopColor: paper.seal, paddingTop: 10 },
});
