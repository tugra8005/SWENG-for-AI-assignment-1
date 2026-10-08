/**
 * Kılavuzun "kararlar dünyaya dokunur" şekilleri: muhatap ve R9 tablosu, dilekçenin yolu,
 * etkinliğin yolu. Örnekler tohumdan alınır: İBB'ye giden semt pazarı dilekçesi, Dekalog I.
 */
import { Animated, StyleSheet, Text, View } from 'react-native';

import { Figure, MiniStamp, guide, shown, useTimeline } from '@/components/guide/kit';
import { fonts, paper } from '@/theme/tokens';

const SEAL = paper.seal;

// --- R9: kim kime yazar --------------------------------------------------------------------------

const COLS = ['Takvim', 'Kendi belediyesi', 'Başka belediye', 'Bakanlık'];
const ROWS: [string, boolean[]][] = [
  ['Genel', [true, true, true, true]],
  ['Şehir (İstanbul)', [true, true, false, false]],
  ['İlgi (Sinema)', [true, false, false, true]],
  ['Yaş grubu', [true, false, false, true]],
];

export function AddresseeFigure({ no }: { no: number }) {
  const t = useTimeline(5200);
  return (
    <Figure
      no={no}
      title="Muhatap: hangi kapsam kime yazabilir (R9)"
      label="Tablo. Genel kapsam takvime, bütün belediyelere ve bakanlıklara yazabilir. Şehir kapsamı yalnızca takvime ve kendi belediyesine. İlgi ve yaş kapsamları takvime ve bakanlıklara; belediyeye yazamaz."
      caption="Kapsam yalnızca yetki alanındaki kuruma yazar. İstanbul kapsamı Ankara Büyükşehir Belediyesi'ne dilekçe gönderemez; öneri açılışta R9 gerekçesiyle reddedilir."
    >
      <View style={st.row}>
        <Text style={[st.cellHead, { flex: 1.4 }]}>Seçmen kapsamı</Text>
        {COLS.map((c) => (
          <Text key={c} style={st.cellHead}>
            {c}
          </Text>
        ))}
      </View>
      {ROWS.map(([scope, marks], i) => (
        <Animated.View key={scope} style={[st.row, { opacity: shown(t, 0.08 + i * 0.16) }]}>
          <Text style={[st.cellScope, { flex: 1.4 }]}>{scope}</Text>
          {marks.map((ok, j) => (
            <Text key={j} style={[st.cell, { color: ok ? paper.ok : SEAL }]}>
              {ok ? '✓' : '✗'}
            </Text>
          ))}
        </Animated.View>
      ))}
    </Figure>
  );
}

// --- dilekçenin yolu ------------------------------------------------------------------------------

const STEPS = [
  ['Kabul', 'konu sessiz onayla kabul edildi'],
  ['MŞV-2026-0001', 'İBB’ye iletildi · deftere mühürlendi'],
  ['30 gün', '3071 sayılı Kanun: yasal yanıt süresi'],
  ['Yanıt', 'katılımcı yazıyı işledi: tarih, sayı, taranmış belge'],
];

export function PetitionFigure({ no }: { no: number }) {
  const t = useTimeline(7000);
  return (
    <Figure
      no={no}
      title="Dilekçenin yolu: talep, iletim, süre, yanıt"
      label="Zaman çizgisi. Kurum muhataplı konu kabul edilir, MŞV-2026-0001 sayılı dilekçe İstanbul Büyükşehir Belediyesi'ne iletilir, otuz günlük yanıt süresi başlar, belediyenin yanıtı bir katılımcı tarafından işlenir. Yanıt gelmeseydi dilekçe süresinde yanıt verilmedi olarak görünecekti."
      caption="Konu karara bağlanınca Karar da aynı kuruma karar bildirimi olarak gider. Yanıt gelmezse süre dolunca dilekçe “süresinde yanıt verilmedi” olur ve gazetede haber çıkar."
    >
      <View style={st.flow}>
        {STEPS.map(([head, text], i) => (
          <Animated.View key={head} style={[st.step, { opacity: shown(t, 0.08 + i * 0.22) }]}>
            <View style={st.stepHead}>
              <View style={st.dot} />
              <Text style={guide.monoBold}>{head}</Text>
            </View>
            <Text style={guide.small}>{text}</Text>
          </Animated.View>
        ))}
      </View>
      <MiniStamp text="YANITLANDI" style={[st.inlineStamp, { opacity: shown(t, 0.86) }]} />
    </Figure>
  );
}

// --- etkinliğin yolu ------------------------------------------------------------------------------

const EVENT_STEPS: [string, string, number][] = [
  ['Öneri №20', 'Dekalog I · Cuma 20:00 · salon', 0.05],
  ['Takvimde', '25 Eylül · yaklaşıyor', 0.3],
  ['Geliyorum', 'nazli, leyla, mert, hakan, irem, gizem', 0.55],
  ['Rapor', '“On dört kişi geldik…”', 0.8],
];

export function EventFigure({ no }: { no: number }) {
  const t = useTimeline(7000);
  return (
    <Figure
      no={no}
      title="Etkinliğin yolu: öneri, takvim, Geliyorum, rapor"
      label="Dekalog I gösterimi. Alt konu önerisi tarih, saat ve ortak salonla açılır; kabul edilince takvime yazılır; altı kişi Geliyorum der; etkinlikten sonra nazli raporunu yazar: on dört kişi geldi."
      caption="Salon Genel kapsamın kaynağıdır: salonlu öneriyi yalnızca Genel kapsam açabilir (R2) ve saatleri kesişen ikinci etkinlik açılışta reddedilir. Rapor ve fotoğrafı yalnızca katılımını bildirenler, etkinlik bittikten sonra ekler."
    >
      <View style={st.flow}>
        {EVENT_STEPS.map(([head, text, at], i) => (
          <Animated.View key={head} style={[st.card, { opacity: shown(t, at) }]}>
            <Text style={[guide.monoBold, { color: i === 3 ? SEAL : paper.ink }]}>{head}</Text>
            <Text style={guide.small}>{text}</Text>
          </Animated.View>
        ))}
      </View>
      <MiniStamp text="GERÇEKLEŞTİ" style={[st.inlineStamp, { opacity: shown(t, 0.9) }]} />
    </Figure>
  );
}

const st = StyleSheet.create({
  row: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: paper.hairline, paddingVertical: 5 },
  cellHead: {
    flex: 1,
    fontFamily: fonts.monoMedium,
    fontSize: 10,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    color: paper.inkSoft,
    textAlign: 'center',
  },
  cellScope: { fontFamily: fonts.serifMedium, fontSize: 14, color: paper.ink },
  cell: { flex: 1, textAlign: 'center', fontFamily: fonts.monoBold, fontSize: 15 },
  // Adımlar satıra yayılır, sığmazsa (telefon) alt alta iner; mutlak konum yok.
  flow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  step: { flexGrow: 1, flexBasis: 150, gap: 3, borderTopWidth: 2, borderTopColor: SEAL, paddingTop: 6 },
  stepHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 12, height: 12, borderRadius: 6, borderWidth: 2, borderColor: SEAL, backgroundColor: paper.sheet },
  card: {
    flexGrow: 1,
    flexBasis: 150,
    borderWidth: 1,
    borderColor: paper.ink,
    backgroundColor: paper.bg,
    padding: 6,
    gap: 3,
  },
  inlineStamp: { position: 'relative', alignSelf: 'flex-end', marginTop: 4 },
});
