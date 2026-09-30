/**
 * Kılavuzun koruma şekilleri: baskın tespiti, defter zinciri, Mahzen (çürüme ve ifşa).
 */
import { Animated, Text, View } from 'react-native';

import { DecayText, LifeBar } from '@/components/cellar';
import { Figure, Segment, Swap, guide, hidden, k, shown, useTimeline } from '@/components/guide/kit';
import { cellar, fonts, paper } from '@/theme/tokens';

const SEAL = paper.seal;

// --- 9. baskın --------------------------------------------------------------------------------------

const OLD: [number, number][] = [
  [14, 20], [42, 62], [22, 112], [72, 30], [90, 92], [58, 130], [122, 16], [112, 72], [140, 124], [150, 48],
];
const OLD_LINKS: [number, number][] = [[0, 1], [1, 4], [3, 6], [7, 9], [5, 4], [2, 1]];
const NEW: [number, number][] = [[192, 46], [230, 50], [242, 90], [208, 112], [184, 84]];
const NEW_LINKS: [number, number][] = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 0], [0, 2], [1, 3], [0, 3]];
const CANVAS = { width: 262, height: 150 };

export function RaidFigure({ no }: { no: number }) {
  const t = useTimeline(7500);
  const dot = (x: number, y: number, color: string, style?: any, key?: string) => (
    <Animated.View
      key={key}
      style={[{ position: 'absolute', left: x - 5, top: y - 5, width: 10, height: 10, borderRadius: 5, backgroundColor: color }, style]}
    />
  );
  return (
    <Figure
      no={no}
      title="Baskın tespiti: yeni ve birbirine bağlı hesaplar"
      height={182}
      label="Eski üyeler dağınık ve seyrek bağlıdır. Birkaç saat içinde beş yeni hesap açılır, aynı konuya yazar ve birbirine yanıt verir. Yoğun bağlı bu küme baskın şüphesiyle işaretlenir ve oyları sayılmaz."
      caption="Karar Saati açılışında yeni hesapların etkileşim grafı taranır: kısa sürede katılan, birbirine yoğun bağlı bir küme seçmen listesinden çıkar. Kişiler adıyla listelenmez; dışlanan kendi pusulasında gerekçeyi görür. Eşikler yönetmeliktedir."
    >
      <View style={{ alignSelf: 'center', ...CANVAS }}>
        {OLD_LINKS.map(([a, b]) => (
          <Segment key={`o${a}-${b}`} x1={OLD[a][0]} y1={OLD[a][1]} x2={OLD[b][0]} y2={OLD[b][1]} color={paper.hairline} />
        ))}
        {OLD.map(([x, y], i) => dot(x, y, paper.muted, undefined, `o${i}`))}
        {NEW_LINKS.map(([a, b], i) => (
          <Segment
            key={`n${a}-${b}`}
            x1={NEW[a][0]}
            y1={NEW[a][1]}
            x2={NEW[b][0]}
            y2={NEW[b][1]}
            color={SEAL}
            style={{ opacity: shown(t, 0.38 + i * 0.02) }}
          />
        ))}
        {NEW.map(([x, y], i) => {
          const at = 0.08 + i * 0.06;
          return dot(x, y, SEAL, { opacity: shown(t, at), transform: [{ scale: k(t, [at - 0.03, at], [0.2, 1]) }] }, `n${i}`);
        })}
        <Animated.View
          style={{
            position: 'absolute',
            left: 213 - 50,
            top: 79 - 50,
            width: 100,
            height: 100,
            borderRadius: 50,
            borderWidth: 1.5,
            borderStyle: 'dashed',
            borderColor: SEAL,
            opacity: shown(t, 0.6),
            transform: [{ scale: k(t, [0.57, 0.62], [0.7, 1]) }],
          }}
        />
        <Text style={[guide.lane, { position: 'absolute', left: 0, bottom: 0, fontSize: 9 }]}>eski üyeler</Text>
      </View>
      <Swap
        t={t}
        box={{ marginTop: 6 }}
        style={[guide.monoBold, { fontSize: 10, color: SEAL }]}
        steps={[
          [0, ' '],
          [0.1, 'YENİ HESAPLAR KATILIYOR…'],
          [0.4, 'BİRBİRİNE YANIT VERİYORLAR…'],
          [0.64, '5 YENİ HESAP · YOĞUN BAĞLI → OYLARI SAYILMADI'],
        ]}
      />
    </Figure>
  );
}

// --- 10. defter -------------------------------------------------------------------------------------

const BLOCKS: [string, string, string][] = [
  ['#621', '⌗a1f3', '⌗a1f3'],
  ['#622', '⌗7c20', '⌗91d8'],
  ['#623', '⌗e94b', '⌗e94b'],
  ['#624', '⌗3b06', '⌗3b06'],
];
const NODES = ['ledger-1', 'ledger-2', 'ledger-3'];

export function LedgerFigure({ no }: { no: number }) {
  const t = useTimeline(8500);
  return (
    <Figure
      no={no}
      title="Defter: her kayıt bir öncekine mühürlü"
      label="Defterde her kayıt bir öncekinin hash'ini taşır. Yeni kayıt zincire eklenir. Bir düğümde 622 numaralı kayıt değiştirilince onun ve sonrakilerin hash'i tutmaz; doğrulama o düğümü bütünlüğü bozuk diye işaretler, diğer iki düğüm tutarlı kalır."
      caption="Kararlar, oylar, silinen içerikler ve yönetmeliğin hâli üç düğümlü, yalnızca eklenen bir zincire yazılır. Bir kaydı değiştirmek sonraki bütün bağları koparır; Defter sayfasındaki Doğrula bunu herkese gösterir. Oylamasız bir kural değişikliği de böyle yakalanır ve Karar Saati'nde geri alınır."
    >
      <View style={{ height: 76 }}>
        {BLOCKS.map(([seq, hash, forged], i) => {
          const tampered = i === 1;
          const incoming = i === 3;
          return (
            <Animated.View
              key={seq}
              style={{
                position: 'absolute',
                top: 26,
                left: `${i * 26.5}%`,
                width: '20.5%',
                height: 46,
                borderWidth: 1.5,
                borderColor: tampered ? k(t, [0.4, 0.44], [paper.ink, SEAL]) : paper.ink,
                backgroundColor: tampered ? k(t, [0.4, 0.44], [paper.sheet, '#F0DCDC']) : paper.sheet,
                alignItems: 'center',
                justifyContent: 'center',
                gap: 1,
                opacity: incoming ? shown(t, 0.1) : 1,
                transform: incoming ? [{ translateX: k(t, [0.08, 0.22], [40, 0]) }] : undefined,
              }}
            >
              <Text style={[guide.monoBold, { fontSize: 11 }]}>{seq}</Text>
              <Swap
                t={t}
                style={[guide.mono, { fontSize: 10, color: tampered ? SEAL : paper.inkSoft }]}
                steps={tampered ? [[0, hash], [0.44, forged]] : [[0, hash]]}
              />
            </Animated.View>
          );
        })}
        {[0, 1, 2].map((i) => {
          const broken = i >= 1;
          const at = 0.5 + (i - 1) * 0.05;
          return (
            <Animated.View key={i} style={{ position: 'absolute', top: 47, left: `${20.5 + i * 26.5}%`, width: '6%', alignItems: 'center' }}>
              <Animated.View
                style={{
                  height: 2,
                  alignSelf: 'stretch',
                  backgroundColor: broken ? k(t, [at - 0.02, at], [paper.ink, SEAL]) : paper.ink,
                  opacity: i === 2 ? shown(t, 0.22) : 1,
                }}
              />
              {broken ? (
                <Animated.Text style={[guide.monoBold, { color: SEAL, position: 'absolute', top: -20, opacity: shown(t, at) }]}>✗</Animated.Text>
              ) : null}
            </Animated.View>
          );
        })}
        <Animated.Text style={[guide.monoBold, { position: 'absolute', top: 6, left: '26.5%', width: '20.5%', textAlign: 'center', fontSize: 9, color: SEAL, opacity: shown(t, 0.44) }]}>
          DEĞİŞTİ
        </Animated.Text>
      </View>
      <Animated.Text style={[guide.small, { color: SEAL, opacity: shown(t, 0.64) }]}>
        Doğrula: #622&apos;nin hash&apos;i tutmuyor, sonraki bağlar kopuk.
      </Animated.Text>
      <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {NODES.map((n, i) => (
          <Animated.View
            key={n}
            style={{
              borderWidth: 1,
              borderColor: i === 1 ? k(t, [0.7, 0.73], [paper.ink, SEAL]) : paper.ink,
              paddingHorizontal: 6,
              paddingVertical: 2,
            }}
          >
            <Swap
              t={t}
              style={[guide.mono, { fontSize: 10, color: i === 1 ? SEAL : paper.ink }]}
              steps={i === 1 ? [[0, `${n} · tutarlı`], [0.73, `${n} · bütünlük bozuk`]] : [[0, `${n} · tutarlı`]]}
            />
          </Animated.View>
        ))}
      </View>
    </Figure>
  );
}

// --- 11. Mahzen -------------------------------------------------------------------------------------

const THREADS: [string, number][] = [
  ['Sokak kedileri kimindir?', 0.1],
  ['Oy vermemek de bir oy mudur?', 0.45],
  ['Anonimlik dürüstlüğü mü artırır?', 0.68],
  ["Theseus'un gemisi hâlâ aynı mı?", 0.86],
  ['Ses çıkar mı, kimse duymazsa?', 0.97],
];
const ROW = 24;

export function CellarFigure({ no }: { no: number }) {
  const t = useTimeline(9500);
  const shift = k(t, [0.08, 0.2], [0, ROW]);
  const paperOn = k(t, [0.6, 0.72], [0, 1]);
  const paperOff = k(t, [0.6, 0.72], [1, 0]);
  return (
    <Figure
      no={no}
      dark
      title="Mahzen: anonim, geçici, çürüyen"
      label="Mahzen listesinde yeni bir başlık en üste girer, diğerleri bir sıra aşağı iner, en alttaki kapasite dolduğu için silinir. Alt sıralardaki başlıkların yazısı soluklaşır ve bozulur. Bir başlıkta ifşa oylaması eşiği geçince zemin kâğıda döner ve Gölge kimliğinin yerine takma ad yazılır."
      caption="Başlıklar sıralarına göre yaşlanır: alt sıralar soluklaşır, son çeyrekte karakterleri bozulur, kapasite dolunca en alttaki kalıcı olarak silinir. İçerik kuralı ve silme oylaması yoktur. Yazanların yarısından fazlası EVET derse başlık ifşa edilir: takma adlar açılır, başlık Meydan'a taslak öneri olarak geçer."
    >
      <View style={{ height: ROW * 6 }}>
        <Animated.View
          style={{ position: 'absolute', left: 0, right: 0, top: k(t, [0.08, 0.2], [-ROW, 0]), opacity: shown(t, 0.12) }}
        >
          <CellarRow title="Sessizlik bir cevap sayılır mı?" decay={0} />
        </Animated.View>
        {THREADS.map(([title, decay], i) => {
          const last = i === THREADS.length - 1;
          return (
            <Animated.View
              key={title}
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: i * ROW,
                transform: [{ translateY: shift }],
                opacity: last ? hidden(t, 0.3) : 1,
              }}
            >
              <CellarRow title={title} decay={decay} />
            </Animated.View>
          );
        })}
        <Animated.Text
          style={{ position: 'absolute', left: 0, right: 0, top: ROW * 5 + 4, fontFamily: fonts.mono, fontSize: 10, color: cellar.amber, opacity: shown(t, 0.32) }}
        >
          kapasite doldu → en alttaki başlık kalıcı olarak silindi
        </Animated.Text>
      </View>
      <Animated.View
        style={{
          marginTop: 8,
          borderWidth: 1,
          borderColor: k(t, [0.6, 0.72], [cellar.amberDim, paper.ink]),
          backgroundColor: k(t, [0.6, 0.72], ['#000000', paper.bg]),
          padding: 8,
          gap: 3,
        }}
      >
        <Swap
          t={t}
          style={{ fontFamily: fonts.mono, fontSize: 10, color: cellar.amber }}
          steps={[
            [0, 'ifşa oylaması · 2/5 EVET · eşik yarıdan fazla'],
            [0.5, '3/5 EVET · eşik aşıldı'],
            [0.62, ' '],
          ]}
        />
        <View>
          <Animated.Text style={{ fontFamily: fonts.monoBold, fontSize: 12, color: cellar.amber, opacity: paperOff }}>
            Gölge·9ea3f7f8
          </Animated.Text>
          <Animated.Text
            style={{ position: 'absolute', fontFamily: fonts.serifBold, fontSize: 14, color: paper.ink, opacity: paperOn, textDecorationLine: 'underline' }}
          >
            pinar
          </Animated.Text>
        </View>
        <View>
          <Animated.Text style={{ fontFamily: fonts.mono, fontSize: 12, lineHeight: 17, color: cellar.amber, opacity: paperOff }}>
            Oylama doğruyu değil, birlikte yaşama biçimini belirler.
          </Animated.Text>
          <Animated.Text
            style={{ position: 'absolute', top: 0, left: 0, right: 0, fontFamily: fonts.serif, fontSize: 14, lineHeight: 17, color: paper.ink, opacity: paperOn }}
          >
            Oylama doğruyu değil, birlikte yaşama biçimini belirler.
          </Animated.Text>
        </View>
      </Animated.View>
    </Figure>
  );
}

function CellarRow({ title, decay }: { title: string; decay: number }) {
  return (
    <View style={{ height: ROW, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
      <DecayText text={title} decay={decay} seed={title.length} numberOfLines={1} style={{ fontSize: 12, flexShrink: 1 }} />
      <LifeBar lifetime={1 - decay} />
    </View>
  );
}
