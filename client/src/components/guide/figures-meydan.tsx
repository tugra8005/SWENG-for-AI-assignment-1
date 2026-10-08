/**
 * Kılavuzun Meydan şekilleri: önerinin yolculuğu, Karar Saati penceresi, R2 daraltma, havale,
 * yönetmelik, Hâtif, silme, kapanış. Örnekler tohumdaki senaryolardan alınır (README).
 */
import { useState } from 'react';
import { Animated, Text, View } from 'react-native';

import { Figure, MiniStamp, Swap, guide, hidden, k, shown, useTimeline } from '@/components/guide/kit';
import { LockIcon } from '@/components/paper';
import { fonts, paper } from '@/theme/tokens';

const SEAL = paper.seal;

// --- 1. önerinin yolculuğu ------------------------------------------------------------------------

export function JourneyFigure({ no }: { no: number }) {
  const t = useTimeline(8000);
  const CARD = 56;
  const aLeft = k(t, [0.04, 0.5], ['0%', '44%']);
  const bLeft = k(t, [0.04, 0.18, 0.42, 0.76], ['0%', '22%', '22%', '44%']);
  const bTop = k(t, [0.3, 0.4], [87, 159]);
  return (
    <Figure
      no={no}
      title="Önerinin yolculuğu: hızlı şerit ve yavaş şerit"
      height={196}
      label="Hızlı şeritte iki öneri. İtiraz almayan №22 sessiz onay süresi dolunca kabul edilir. Eşik kadar itiraz alan №9 yavaş şeride geçer ve Pazar 20:00 Karar Saati'nde oylanır."
      caption="№22'ye süre boyunca eşik kadar itiraz gelmedi: süre dolunca kendiliğinden kabul edildi. №9 eşiğe ulaştı: yavaş şeride geçti, ilk uygun Karar Saati'nde oylanacak."
    >
      <Text style={[guide.lane, { position: 'absolute', top: 0 }]}>Hızlı şerit · sessiz onay süresi</Text>
      <View style={[guide.track, { top: 40 }]} />
      <Animated.View style={[guide.track, { top: 39, height: 3, right: undefined, width: aLeft, backgroundColor: SEAL }]} />
      <Animated.View style={[guide.card, { top: 28, left: aLeft, width: CARD }]}>
        <Text style={guide.monoBold}>№22</Text>
      </Animated.View>
      <MiniStamp text="KABUL" style={{ right: 6, top: 24, opacity: shown(t, 0.53) }} />

      <Text style={[guide.lane, { position: 'absolute', top: 60 }]}>Hızlı şerit</Text>
      <View style={[guide.track, { top: 99 }]} />
      <Animated.View
        style={[guide.track, { top: 98, height: 3, right: undefined, width: k(t, [0.04, 0.18], ['0%', '22%']), backgroundColor: SEAL }]}
      />
      <Swap
        t={t}
        box={{ position: 'absolute', top: 62, left: '46%' }}
        style={[guide.monoBold, { color: SEAL }]}
        steps={[
          [0, ' '],
          [0.12, 'itiraz 1/3'],
          [0.2, 'itiraz 2/3'],
          [0.28, 'itiraz 3/3 · eşik'],
        ]}
      />

      <Text style={[guide.lane, { position: 'absolute', top: 132 }]}>Yavaş şerit → Karar Saati</Text>
      <View style={[guide.track, { top: 171 }]} />
      <Animated.View
        style={[guide.track, { top: 170, height: 3, left: '22%', right: undefined, width: k(t, [0.42, 0.76], ['0%', '22%']), backgroundColor: SEAL }]}
      />
      <Animated.View style={[guide.card, { top: bTop, left: bLeft, width: CARD }]}>
        <Text style={guide.monoBold}>№9</Text>
      </Animated.View>
      <Animated.View
        style={{
          position: 'absolute',
          right: 0,
          top: 157,
          borderWidth: 1.5,
          borderColor: SEAL,
          paddingHorizontal: 6,
          paddingVertical: 3,
          opacity: shown(t, 0.78),
          backgroundColor: paper.sheet,
        }}
      >
        <Text style={[guide.monoBold, { color: SEAL, fontSize: 10 }]}>PAZAR 20:00</Text>
      </Animated.View>
    </Figure>
  );
}

// --- 2. Karar Saati penceresi ---------------------------------------------------------------------

const DAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];
const SEALED = ['EVET', 'HAYIR', 'EVET', 'EVET', 'HAYIR', 'EVET'];
const LOCKED = ['seçmen listesi', 'havale grafı', 'yönetmelik'];

export function WindowFigure({ no }: { no: number }) {
  const t = useTimeline(9000);
  return (
    <Figure
      no={no}
      title="Karar Saati: haftalık oylama penceresi"
      label="Hafta boyunca birikenler Pazar 20:00'de açılan pencerede oylanır. Açılışta seçmen listesi, havale grafı ve yönetmelik kilitlenir. Oylar mühürlü verilir, 21:00'de açılır ve sayılır."
      caption="Açılışta anlık görüntü alınır: pencere boyunca kimse seçmen listesine giremez, havalesini değiştiremez, kural değişmez. Oylar mühürlüdür (commit); kapanışta açılır (reveal) ve herkes mührü yeniden hesaplayabilir."
    >
      <View style={{ flexDirection: 'row', height: 28 }}>
        {DAYS.map((d, i) => {
          const last = i === DAYS.length - 1;
          return (
            <Animated.View
              key={d}
              style={{
                flex: 1,
                borderWidth: 1,
                borderColor: last ? SEAL : paper.hairline,
                marginLeft: i ? -1 : 0,
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: last ? k(t, [0.33, 0.37], [paper.sheet, SEAL]) : paper.sheet,
              }}
            >
              <Animated.Text
                style={[guide.monoBold, { fontSize: 10, color: last ? k(t, [0.33, 0.37], [SEAL, paper.sheet]) : paper.inkSoft }]}
              >
                {d}
              </Animated.Text>
            </Animated.View>
          );
        })}
      </View>
      <View style={{ height: 12 }}>
        <Animated.View style={{ position: 'absolute', top: 2, width: 2, height: 8, backgroundColor: SEAL, left: k(t, [0, 0.34], ['1%', '93%']) }} />
      </View>
      <Animated.Text style={[guide.monoBold, { color: SEAL, opacity: shown(t, 0.38) }]}>20:00 AÇILIŞ · ANLIK GÖRÜNTÜ</Animated.Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
        {LOCKED.map((l, i) => (
          <Animated.View
            key={l}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 5,
              borderWidth: 1,
              borderColor: paper.ink,
              paddingHorizontal: 6,
              paddingVertical: 2,
              opacity: shown(t, 0.43 + i * 0.05),
            }}
          >
            <LockIcon size={11} color={paper.ink} />
            <Text style={[guide.mono, { fontSize: 10 }]}>{l}</Text>
          </Animated.View>
        ))}
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 12 }}>
        {SEALED.map((c, i) => {
          const at = 0.58 + i * 0.025;
          const flip = 0.8 + i * 0.02;
          return (
            <Animated.View
              key={i}
              style={{
                width: 40,
                height: 24,
                borderWidth: 1,
                borderColor: paper.ink,
                backgroundColor: k(t, [flip - 0.01, flip], [paper.bgDeep, paper.sheet]),
                justifyContent: 'center',
                opacity: shown(t, at),
                transform: [{ translateY: k(t, [at - 0.03, at], [-10, 0]) }],
              }}
            >
              <Swap
                t={t}
                box={{ alignSelf: 'center' }}
                style={[guide.monoBold, { fontSize: 9, textAlign: 'center', color: c === 'EVET' ? SEAL : paper.ink }]}
                steps={[
                  [0, '⌗'],
                  [flip, c],
                ]}
              />
            </Animated.View>
          );
        })}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 10 }}>
        <Animated.Text style={[guide.small, { flex: 1, opacity: shown(t, 0.78) }]}>
          21:00 kapanış: mühürler açılır, oylar sayılır; sonuç oy verenlerin zile düşer.
        </Animated.Text>
        <MiniStamp text="KABUL" style={{ position: 'relative', opacity: shown(t, 0.93) }} />
      </View>
    </Figure>
  );
}

// --- 3. R2 daraltma -------------------------------------------------------------------------------

const SHARES: [string, string, number][] = [
  ['İstanbul', '4.000', 4],
  ['Ankara', '6.000', 6],
  ['İzmir', '5.000', 5],
  ['Bursa', '5.000', 5],
];

export function NarrowingFigure({ no }: { no: number }) {
  const t = useTimeline(7000);
  return (
    <Figure
      no={no}
      title="Kapsam ve R2: talep değil, etki oylanır"
      label="İstanbul seçmeni etkinlik bütçesinin tamamını istiyor. Bütçe Genel kapsamın ve şehir paylarına bölünebilir. Talep üstü çizilir, öneri yalnızca İstanbul payına daralır."
      caption="Bütçenin sahibi Genel kapsam; şehir paylarına bölünebilir. İstanbul seçmeni yalnızca kendi payına karar verebilir: öneri açılırken kendiliğinden daralır. Kaynak bölünemeseydi (ör. ortak toplantı salonu) öneri hiç açılmazdı."
    >
      <View style={{ gap: 6 }}>
        <View>
          <Animated.Text style={[guide.serif, { opacity: hidden(t, 0.3) }]}>
            <Text style={guide.monoBold}>Talep: </Text>Etkinlik bütçesinin tamamı İstanbul&apos;a
          </Animated.Text>
          <Animated.Text
            style={[
              guide.serif,
              { position: 'absolute', top: 0, left: 0, right: 0, color: paper.muted, textDecorationLine: 'line-through', opacity: shown(t, 0.3) },
            ]}
          >
            <Text style={[guide.monoBold, { color: paper.muted }]}>Talep: </Text>Etkinlik bütçesinin tamamı İstanbul&apos;a
          </Animated.Text>
        </View>
        <Animated.Text style={[guide.serif, { fontFamily: fonts.serifMedium, fontSize: 17, opacity: shown(t, 0.42) }]}>
          <Text style={{ color: SEAL }}>Etki: </Text>Etkinlik bütçesinin İstanbul payı
        </Animated.Text>
        <View style={{ flexDirection: 'row', gap: 2, height: 14, marginTop: 6 }}>
          {SHARES.map(([city, , w], i) => (
            <Animated.View
              key={city}
              style={{ flex: w, backgroundColor: i === 0 ? SEAL : k(t, [0.24, 0.4], [SEAL, paper.hairline]) }}
            />
          ))}
        </View>
        <View style={{ flexDirection: 'row', gap: 2 }}>
          {SHARES.map(([city, amount, w]) => (
            <View key={city} style={{ flex: w }}>
              <Text style={[guide.mono, { fontSize: 9 }]} numberOfLines={1}>
                {city}
              </Text>
              <Text style={[guide.monoBold, { fontSize: 9 }]}>{amount}</Text>
            </View>
          ))}
        </View>
        <Swap
          t={t}
          style={[guide.monoBold, { fontSize: 10, color: SEAL }]}
          steps={[
            [0, 'SEÇMEN: İSTANBUL · TALEP: BÜTÇENİN TAMAMI'],
            [0.44, 'R2 · 4.000 / 20.000 PUAN (%20) · DARALTILDI'],
          ]}
        />
      </View>
    </Figure>
  );
}

// --- 4. havale ------------------------------------------------------------------------------------

const NODES = [
  { name: 'aylin', note: '→ baris (genel)' },
  { name: 'baris', note: '→ ceren (Ulaşım)' },
  { name: 'ceren', note: 'temsilci' },
];

export function DelegationFigure({ no }: { no: number }) {
  const t = useTimeline(8000);
  const weights: [number, string][][] = [
    [
      [0, 'oy 1'],
      [0.3, 'devretti'],
    ],
    [
      [0, 'oy 1'],
      [0.3, 'oy 2'],
      [0.6, 'devretti'],
    ],
    [
      [0, 'ağırlık ×1'],
      [0.6, 'ağırlık ×3'],
    ],
  ];
  const token = (left: any, dx: number, key: string) => (
    <Animated.View
      key={key}
      style={{ position: 'absolute', top: 80, left, marginLeft: dx, width: 11, height: 11, borderRadius: 6, backgroundColor: SEAL }}
    />
  );
  return (
    <Figure
      no={no}
      title="Havale: oy güvenilen kişiye akar"
      height={182}
      label="Ulaşım alanındaki bir öneride aylin'in oyu genel havaleyle baris'e, baris'in oyu Ulaşım havalesiyle ceren'e gider. ceren'in ağırlığı 3 olur ve oyu açık görünür. elif'in aylin'e verdiği havale kabul edilmediği için sayılmaz."
      caption="Ulaşım'daki bir öneride aylin'in oyu baris'e, oradan ceren'e akar: ceren üç oy taşır ve başkalarının oyunu taşıdığı için oyu açıktır. Havale alan kişi kabul etmedikçe yürürlüğe girmez, süresi dolunca kendiliğinden düşer; döngü kurulamaz (R4)."
    >
      {NODES.map((n, i) => (
        <Animated.View
          key={n.name}
          style={{
            position: 'absolute',
            top: 8,
            left: `${i * 36}%`,
            width: '28%',
            height: 60,
            borderWidth: i === 2 ? 1.5 : 1,
            borderColor: i === 2 ? k(t, [0.6, 0.64], [paper.ink, SEAL]) : paper.ink,
            backgroundColor: paper.sheet,
            alignItems: 'center',
            justifyContent: 'center',
            gap: 2,
          }}
        >
          <Text style={[guide.serif, { fontFamily: fonts.serifMedium }]}>{n.name}</Text>
          <Swap t={t} style={[guide.mono, { fontSize: 10, textAlign: 'center' }]} steps={weights[i]} />
        </Animated.View>
      ))}
      {[0, 1].map((i) => (
        <Text key={i} style={[guide.monoBold, { position: 'absolute', top: 26, left: `${28 + i * 36}%`, width: '8%', textAlign: 'center', fontSize: 14 }]}>
          →
        </Text>
      ))}
      {token(k(t, [0.1, 0.3, 0.4, 0.6], ['14%', '50%', '50%', '86%']), -18, 'a')}
      {token(k(t, [0.4, 0.6], ['50%', '86%']), -5, 'b')}
      {token('86%', 8, 'c')}
      {NODES.map((n, i) => (
        <Text
          key={n.name}
          style={[guide.small, { position: 'absolute', top: 98, left: `${i * 36}%`, width: '28%', textAlign: 'center', fontSize: 12 }]}
        >
          {n.note}
        </Text>
      ))}
      <Animated.Text style={[guide.monoBold, { position: 'absolute', top: 116, left: '72%', width: '28%', textAlign: 'center', color: SEAL, fontSize: 10, opacity: shown(t, 0.66) }]}>
        OYU AÇIK
      </Animated.Text>
      <Animated.View
        style={{
          position: 'absolute',
          top: 140,
          left: 0,
          right: 0,
          borderWidth: 1,
          borderStyle: 'dashed',
          borderColor: paper.muted,
          paddingHorizontal: 8,
          paddingVertical: 5,
          opacity: shown(t, 0.72),
        }}
      >
        <Text style={[guide.mono, { fontSize: 10, color: paper.inkSoft }]}>
          elif → aylin (Kent) · kabul bekliyor: kabul edilene kadar oy elif&apos;te kalır
        </Text>
      </Animated.View>
    </Figure>
  );
}

// --- 5. yönetmelik ----------------------------------------------------------------------------------

export function RegulationFigure({ no }: { no: number }) {
  const t = useTimeline(8500);
  const shake = k(t, [0.64, 0.66, 0.68, 0.7, 0.72, 0.74], [0, -6, 6, -4, 4, 0]);
  return (
    <Figure
      no={no}
      title="Yönetmelik veridir: oylanır, tabanı oylanamaz"
      label="Sessiz onay süresini 24 saatten 36 saate çıkaran öneri 30 oyun 20'sini alır, üçte iki eşiğini geçer ve madde değişir. Şerh hakkını kaldırmak isteyen öneri değiştirilemez maddeye çarpar ve açılışta reddedilir."
      caption="Eşikler, süreler ve sınırlar koda değil yönetmeliğe yazılıdır; yönetmelik önerisiyle değişir ve üçte iki ister. Yedi temel ilke (D1–D7) ve her sayının izinli aralığı oylamanın dışındadır: onlara dokunan öneri açılmaz (R8)."
    >
      <View style={{ borderWidth: 1, borderColor: paper.ink, padding: 8, gap: 6 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <Text style={[guide.mono, { flexShrink: 1 }]}>sessiz_onay_suresi</Text>
          <Swap
            t={t}
            style={[guide.monoBold, { fontSize: 13 }]}
            steps={[
              [0, '24 saat'],
              [0.46, '36 saat'],
            ]}
          />
        </View>
        <View style={{ height: 10, backgroundColor: paper.bgDeep }}>
          <Animated.View style={{ height: 10, width: k(t, [0.08, 0.4], ['0%', '66.7%']), backgroundColor: SEAL }} />
          <View style={{ position: 'absolute', left: '66.67%', top: -3, width: 2, height: 16, backgroundColor: paper.ink }} />
        </View>
        <Swap
          t={t}
          style={[guide.mono, { fontSize: 10 }]}
          steps={[
            [0, 'yonetmelik_esigi ≥ 2/3'],
            [0.4, '20/30 EVET · ≥ 2/3 · geçti'],
          ]}
        />
        <MiniStamp text="KABUL" style={{ right: 8, top: 34, opacity: shown(t, 0.42) }} />
      </View>
      <Animated.View
        style={{ marginTop: 12, borderWidth: 1, borderColor: paper.ink, padding: 8, gap: 4, transform: [{ translateX: shake }] }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <LockIcon size={13} />
          <Text style={[guide.monoBold, { color: SEAL }]}>D3</Text>
          <Text style={[guide.serif, { fontSize: 14, flexShrink: 1 }]}>Kaybeden taraf Şerh ekleyebilir; Şerh silinemez.</Text>
        </View>
      </Animated.View>
      <Animated.View
        style={{
          alignSelf: 'flex-end',
          marginTop: 8,
          borderWidth: 1,
          borderColor: k(t, [0.74, 0.76], [paper.ink, SEAL]),
          paddingHorizontal: 8,
          paddingVertical: 3,
          opacity: shown(t, 0.52),
          transform: [{ translateX: k(t, [0.52, 0.63], [60, 0]) }],
        }}
      >
        <Swap
          t={t}
          style={[guide.monoBold, { fontSize: 10 }]}
          steps={[
            [0, "ÖNERİ: D3'Ü KALDIR"],
            [0.76, 'R8 · AÇILIŞTA REDDEDİLDİ'],
          ]}
        />
      </Animated.View>
    </Figure>
  );
}

// --- 6. Hâtif --------------------------------------------------------------------------------------

const CHECKS: [string, string, number, boolean][] = [
  ['R1–R9 · açılış kuralları', 'geçti', 0.12, true],
  ["H1 · alan: 'belgesel' ×2", 'uyuşmuyor', 0.28, false],
  ['H2 · etiketlenmemiş kaynak', 'yok', 0.42, true],
  ['H3 · şehir', 'uyumlu', 0.52, true],
];

export function OracleFigure({ no }: { no: number }) {
  const t = useTimeline(7500);
  const scan = k(t, [0.04, 0.12, 0.2, 0.28, 0.36, 0.42, 0.48, 0.52, 0.58], [0, 0, 26, 26, 52, 52, 78, 78, 104]);
  return (
    <Figure
      no={no}
      title="Hâtif: kural tabanlı bilirkişi"
      label="Hâtif Belgesel film gösterimleri önerisini denetler. Açılış kuralları geçer, ama metin belgeselden söz ederken alan Edebiyat seçilmiştir. Uyuşmazlık olduğu için Hâtif HAYIR der; iki kişi ona havale ettiği için ağırlığı 3'tür."
      caption="Hâtif bir yapay zekâ değil, yazılı kurallardır: her öneride aynı denetimi yapar, biri bile geçmezse HAYIR der. Ona havale eden oyunu bu kurallara emanet eder."
    >
      <Text style={[guide.serif, { fontFamily: fonts.serifMedium }]}>№16 Belgesel film gösterimleri</Text>
      <Text style={[guide.small, { marginBottom: 6 }]}>
        seçilen alan Edebiyat, metin Belgesel&apos;i anlatıyor · Kültür&apos;de 2 kişi Hâtif&apos;e havale etti
      </Text>
      <View>
        <Animated.View
          style={{ position: 'absolute', left: -4, right: -4, height: 24, top: scan, backgroundColor: paper.sealWash, opacity: hidden(t, 0.62) }}
        />
        {CHECKS.map(([label, verdict, at, ok]) => (
          <View key={label} style={{ height: 26, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <Text style={[guide.mono, { flexShrink: 1 }]} numberOfLines={1}>
              {label}
            </Text>
            <Animated.Text style={[guide.monoBold, { color: ok ? paper.ink : SEAL, opacity: shown(t, at) }]}>
              {ok ? '✓' : '✗'} {verdict}
            </Animated.Text>
          </View>
        ))}
      </View>
      <Animated.View
        style={{
          alignSelf: 'flex-start',
          marginTop: 8,
          borderWidth: 1.5,
          borderColor: SEAL,
          paddingHorizontal: 8,
          paddingVertical: 3,
          opacity: shown(t, 0.66),
        }}
      >
        <Text style={[guide.monoBold, { color: SEAL, fontSize: 12 }]}>HÂTİF: HAYIR ×3</Text>
      </Animated.View>
    </Figure>
  );
}

// --- 7. silme ---------------------------------------------------------------------------------------

export function DeletionFigure({ no }: { no: number }) {
  const t = useTimeline(8500);
  const [w, setW] = useState(0);
  return (
    <Figure
      no={no}
      title="Silme: içerik kuralı, alıntı ve üçte iki"
      label="Bir reklam mesajı için IK-1 içerik kuralına dayanan, ihlal eden kısmı alıntılayan silme önerisi açılır. Otuz oyun yirmisini alarak üçte iki eşiğini geçer. Mesajın üstüne siyah sansür şeridi iner; metin defterde kalır."
      caption="Başkasının mesajını silmek için bir içerik kuralı (IK-1 spam, IK-2 hakaret, IK-3 kişisel bilgi) ve ihlal eden kısmın aynen alıntısı gerekir (R7); eşik üçte ikidir. Yazar kendi mesajını basit çoğunlukla sildirebilir. Silinen metin sitede gizlenir, defterde durur."
    >
      <View onLayout={(e) => setW(e.nativeEvent.layout.width)} style={{ borderWidth: 1, borderColor: paper.hairline, padding: 8, gap: 3 }}>
        <Text style={[guide.mono, { fontSize: 10, color: paper.inkSoft }]}>kaba_kul · #34</Text>
        <Text style={[guide.serif, { fontSize: 14 }]}>
          Kaçırmayın! Katlanır bisiklette büyük indirim kampanyası, sipariş için profilime tıklayın.
        </Text>
        <Animated.View
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            overflow: 'hidden',
            backgroundColor: paper.strip,
            width: k(t, [0.62, 0.72], ['0%', '100%']),
          }}
        >
          <View style={{ width: w, flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2 }}>
            <Text style={[guide.monoBold, { color: paper.stripText }]} numberOfLines={1}>
              #11 · IK-1 gereğince silindi
            </Text>
            <Text style={[guide.mono, { fontSize: 10, color: paper.stripText }]}>defterde: ⌗ 5c887bbf</Text>
          </View>
        </Animated.View>
      </View>
      <Animated.View
        style={{ marginTop: 8, borderWidth: 1, borderColor: paper.ink, paddingHorizontal: 6, paddingVertical: 3, opacity: shown(t, 0.14) }}
      >
        <Text style={[guide.mono, { fontSize: 10 }]} numberOfLines={2}>
          №11 SİLME · IK-1 Spam ve reklam · alıntı: &quot;büyük indirim kampanyası, sipariş için profilime tıklayın&quot;
        </Text>
      </Animated.View>
      <View style={{ height: 10, backgroundColor: paper.bgDeep, marginTop: 10 }}>
        <Animated.View style={{ height: 10, width: k(t, [0.25, 0.5], ['0%', '66.7%']), backgroundColor: SEAL }} />
        <View style={{ position: 'absolute', left: '66.67%', top: -3, width: 2, height: 16, backgroundColor: paper.ink }} />
      </View>
      <Swap
        t={t}
        box={{ marginTop: 4 }}
        style={[guide.mono, { fontSize: 10 }]}
        steps={[
          [0, 'silme_esigi ≥ 2/3'],
          [0.5, '20/30 EVET · ≥ 2/3 · kabul'],
        ]}
      />
    </Figure>
  );
}

// --- 8. kapanış ve Şerh -----------------------------------------------------------------------------

const RIVALS: [string, string, number][] = [
  ["Parklar her gün 20:00'de kapansın", 'zeynep', 55],
  ["Parklar her gün 22:00'de kapansın", 'burak', 100],
  ["Yazın 24:00'te, kışın 22:00'de kapansın", 'ilker', 64],
];

export function ClosureFigure({ no }: { no: number }) {
  const t = useTimeline(8000);
  return (
    <Figure
      no={no}
      title="Kapanış: onay oylaması, Karar ve Şerh"
      label="Parkların kapanış saati konusunda üç rakip metin onay oylamasına girer. En çok onayı alan 22:00 metni Karar olur. Kaybeden metnin sahibi ilker karara silinemez bir Şerh ekler."
      caption="Konuyu kapatmak için rakip metinler yarışır; seçmen istediği kadar metni onaylar, en çok onay alan Karar olur. Kaybeden metnin sahibi ya da onu onaylayan, karara bir Şerh ekleyebilir: Şerh düzenlenemez, silinemez, defterde durur (D3). Örnek sayılar temsilidir."
    >
      {RIVALS.map(([text, who, pct], i) => {
        const win = i === 1;
        return (
          <Animated.View
            key={who}
            style={{
              marginBottom: 8,
              padding: 5,
              borderWidth: 1.5,
              borderColor: win ? k(t, [0.54, 0.58], ['rgba(0,0,0,0)', SEAL]) : 'rgba(0,0,0,0)',
              gap: 3,
            }}
          >
            {win ? (
              <Animated.Text style={[guide.monoBold, { fontSize: 10, color: SEAL, opacity: shown(t, 0.58) }]}>KARAR</Animated.Text>
            ) : null}
            <Text style={[guide.serif, { fontSize: 14 }]}>
              {text} <Text style={guide.small}>— {who}</Text>
            </Text>
            <View style={{ height: 7, backgroundColor: paper.bgDeep }}>
              <Animated.View
                style={{
                  height: 7,
                  width: k(t, [0.08, 0.5], ['0%', `${pct}%`]),
                  backgroundColor: win ? SEAL : k(t, [0.54, 0.58], [SEAL, paper.inkSoft]),
                }}
              />
            </View>
          </Animated.View>
        );
      })}
      <Animated.View
        style={{ borderLeftWidth: 3, borderLeftColor: SEAL, paddingLeft: 8, paddingVertical: 2, gap: 1, opacity: shown(t, 0.7) }}
      >
        <Text style={[guide.monoBold, { fontSize: 10, color: SEAL }]}>ŞERH · ilker</Text>
        <Text style={[guide.serif, { fontSize: 14 }]}>Yazın parklar gece yarısına kadar açık kalmalıydı.</Text>
        <Text style={[guide.mono, { fontSize: 9, color: paper.inkSoft }]}>silinemez · düzenlenemez · defterde</Text>
      </Animated.View>
    </Figure>
  );
}
