/**
 * Kılavuz: Meşveret'in amacı ve bütün sistemi, terimleri canlandırmalı şekillerle.
 *
 * Sayılar (süreler, eşikler, Karar Saati'nin günü) yönetmelikten canlı okunur; oylamayla
 * değiştiğinde sayfa eskimez. Şekiller örnektir ve tohumdaki senaryolardan alınır.
 */
import { type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import {
  ClosureFigure,
  DelegationFigure,
  DeletionFigure,
  JourneyFigure,
  NarrowingFigure,
  OracleFigure,
  RegulationFigure,
  WindowFigure,
} from '@/components/guide/figures-meydan';
import { CellarFigure, LedgerFigure, RaidFigure } from '@/components/guide/figures-guard';
import { Anchor, Body, Columns, InitialText, Kicker, Page, Rule, useScrollTo } from '@/components/paper';
import { RevealTally } from '@/components/reveal-tally';
import { describeArticleValue } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { fonts, layout, paper } from '@/theme/tokens';

const SECTIONS: [string, string][] = [
  ['modlar', 'İki mod: Meydan ve Mahzen'],
  ['oneri', 'Öneri ve iki şerit'],
  ['karar-saati', 'Karar Saati'],
  ['kapsam', 'Kapsam: kim neye karar verir'],
  ['havale', 'Havale'],
  ['yonetmelik', 'Yönetmelik ve değiştirilemez maddeler'],
  ['hatif', 'Hâtif'],
  ['silme', 'Silme ve sansür şeridi'],
  ['kapanis', 'Kapanış, Karar ve Şerh'],
  ['baskin', 'Baskın tespiti'],
  ['defter', 'Defter'],
  ['mahzen', 'Mahzen'],
  ['aciklar', 'Bilinçli açıklar'],
  ['sozluk', 'Sözlük'],
];
const num = (id: string) => SECTIONS.findIndex(([k]) => k === id) + 1;

/** Tohumdaki №9 "Gece metro seferleri"nin sonucu (README senaryo 2): gerçek sayım bileşeniyle. */
const SAMPLE_TALLY = {
  kind: 'binary',
  eligible: 39,
  abstained: 26,
  passed: true,
  flagged_count: 0,
  flagged_reasons: [],
  threshold: { key: 'basit_cogunluk', oran: '1/2', karsilastirma: '>' },
  note: '8/13 ağırlıklı EVET (%61,5); eşik basit_cogunluk > 1/2.',
  oracle: { choice: 'EVET', reason: 'R1–R8 geçti; etiketler uyumlu.' },
  votes: [
    { ballot_id: 1, open: true, voter: 'Hâtif', choice: 'EVET', weight: 1 },
    { ballot_id: 2, open: false, pseudonym: 'dc230069', choice: 'EVET', weight: 1 },
    { ballot_id: 3, open: false, pseudonym: '2ec58c6f', choice: 'EVET', weight: 1 },
    { ballot_id: 4, open: false, pseudonym: '0940af2b', choice: 'HAYIR', weight: 1 },
    { ballot_id: 5, open: false, pseudonym: '6e3c8eae', choice: 'EVET', weight: 1 },
    { ballot_id: 6, open: false, pseudonym: '8def33d6', choice: 'HAYIR', weight: 1 },
    { ballot_id: 7, open: false, pseudonym: 'ae26911f', choice: 'EVET', weight: 1 },
    { ballot_id: 8, open: false, pseudonym: 'dbe1ee71', choice: 'HAYIR', weight: 1 },
    { ballot_id: 9, open: false, pseudonym: '25da0e42', choice: 'HAYIR', weight: 1 },
    { ballot_id: 10, open: false, pseudonym: 'b5b6c8ed', choice: 'HAYIR', weight: 1 },
    { ballot_id: 11, open: true, voter: 'ceren', choice: 'EVET', weight: 3, delegators: ['aylin', 'baris'] },
  ],
};

const MECHANISMS: [string, string, string, string][] = [
  ['I', 'Kapsam', 'Bir karara yalnızca etkilenen kaynağın sahibi olan topluluk ya da onun bir parçası oy verir.', 'kapsam'],
  ['II', 'Havale', 'Oy hakkı alan alan güvenilen kişilere devredilir; uzmanlık görünür olur, temsilcinin oyu açıktır.', 'havale'],
  ['III', 'Nitelikli çoğunluk', 'Kuralları değiştirmek ve başkasının içeriğini silmek üçte iki ister; bazı kurallar hiç değişmez.', 'yonetmelik'],
  ['IV', 'Azınlık şerhi', 'Kaybeden taraf karara silinemez bir görüş ekler.', 'kapanis'],
];

const PAGES: [string, string][] = [
  ['Meydan', 'ana sayfa: Karar Saati geri sayımı, itiraza açık öneriler, kuyruk, alanlar ve konular'],
  ['Karar Saati', 'açık oturumda oy pusulası; geçmiş oturumların sonuçları ve oyların açılışı'],
  ['Havale', 'oyunuzu devretmek, size gelen havaleleri kabul etmek ya da iade etmek'],
  ['Yönetmelik', 'bütün kurallar, geçmişleri ve değiştirilemez maddeler'],
  ['Defter', 'kayıtlar ve üç düğümün doğrulaması'],
  ['Zil', 'oy verdiğiniz ve açtığınız önerilerin sonuçları'],
  ['Takma adınız', 'profiliniz: kapsam üyelikleri, havaleler, oylarınızı doğrulama'],
];

const GLOSSARY: [string, string][] = [
  ['Meydan', 'Açık, kimlikli, kalıcı forum.'],
  ['Mahzen', 'Anonim, geçici tartışma alanı; teşvik edilmez.'],
  ['Alan', 'Konuların sınıflandığı ağaç: Kent › Ulaşım › Bisiklet.'],
  ['Konu', 'Kabul edilmiş, tartışmaya açık başlık.'],
  ['Öneri', 'Her değişikliğin biçimi: konu, alt konu, düzenleme, silme, yönetmelik, kapanış.'],
  ['Sessiz onay', 'Hızlı şeritteki önerinin itiraz eşiğine ulaşmadan süre sonunda kabul edilmesi.'],
  ['İtiraz', 'Hızlı şeritteki öneriyi Karar Saati\'ne gönderen kişisel karşı çıkış.'],
  ['Yavaş şerit', 'Karar Saati\'nde oylanmayı bekleyen öneriler.'],
  ['Olgunlaşma', 'Önerinin oylanmadan önce yayında kalması gereken en kısa süre.'],
  ['Karar Saati', 'Haftalık oylama penceresi.'],
  ['Kapsam', 'Seçmen topluluğu: Genel, şehir, yaş grubu ya da ilgi alanı.'],
  ['Kaynak', 'Sahibi olan şey: bütçe, salon. Bölünebilir ya da bölünemez.'],
  ['Daralma (R2)', 'Önerinin, kapsamın sahip olduğu paya kendiliğinden küçülmesi.'],
  ['Eşzamanlı çoğunluk', 'Payı orantısız etkilenen kapsamın ayrıca oylaması.'],
  ['Havale', 'Oy hakkının, kabul eden güvenilen kişiye devri.'],
  ['Temsilci', 'Başkalarının oyunu taşıyan kişi; oyu açıktır.'],
  ['Müşavir', 'Çok havale alan kişinin etiketi.'],
  ['Hâtif', 'Kural tabanlı sembolik bilirkişi; yapay zekâ değildir.'],
  ['Yönetmelik', 'Bütün kuralların oylanabilir listesi.'],
  ['Değiştirilemez madde', 'D1–D7: oylamanın dışında kalan temel ilkeler.'],
  ['İçerik kuralı', 'Silmenin dayanabileceği gerekçe: IK-1, IK-2, IK-3.'],
  ['Sansür şeridi', 'Silinen içeriğin yerindeki siyah şerit.'],
  ['Karar', 'Kapanış oylamasını kazanan metin.'],
  ['Şerh', 'Kaybeden tarafın karara eklediği silinemez görüş.'],
  ['Defter', 'Kararların yazıldığı, üç düğümlü, değiştirilemez zincir.'],
  ['Mühür (⌗)', 'Bir kaydın defterdeki hash\'i; dokununca kaydı açar.'],
  ['Baskın', 'Bir oylamayı ele geçirmeye çalışan yeni hesap kümesi.'],
  ['Gölge', 'Mahzen\'de başlığa özel takma kimlik.'],
  ['İfşa', 'Mahzen başlığının oylamayla kimlikli hâle gelmesi.'],
  ['Zil', 'Oy verdiğiniz önerilerin sonuçları.'],
];

/** Yönetmelikten canlı değer: "36 saat", "≥ 2/3". Yüklenene kadar madde anahtarı durur. */
function useReg() {
  const list = useApi<any[]>('/regulation');
  const byKey = new Map((list.data ?? []).map((a: any) => [a.key, a]));
  return function reg(key: string) {
    const a = byKey.get(key);
    return <Text style={st.reg}>{a ? describeArticleValue(a.kind, a.value) : key}</Text>;
  };
}

function Section({ id, children }: { id: string; children: ReactNode }) {
  const title = SECTIONS[num(id) - 1][1];
  return (
    <Anchor id={id}>
      <View style={{ marginTop: 34 }}>
        <Text style={st.sectionNo}>§ {num(id)}</Text>
        <Text style={st.h2}>{title}</Text>
        <Rule style={{ marginTop: 6, marginBottom: 10 }} />
        <View style={{ gap: 10 }}>{children}</View>
      </View>
    </Anchor>
  );
}

const P = ({ children }: { children: ReactNode }) => <Body style={st.p}>{children}</Body>;

/** Sayfa içi bağlantı. Kaydırma bağlamı Page'in içinde kurulduğu için kanca burada çağrılır. */
function Jump({ to, style, children }: { to: string; style?: any; children: ReactNode }) {
  const scrollTo = useScrollTo();
  return (
    <Pressable
      onPress={() => scrollTo(to)}
      accessibilityRole="link"
      style={({ hovered }: any) => [style, hovered && { backgroundColor: paper.sealWash }]}
    >
      {children}
    </Pressable>
  );
}

export default function Guide() {
  const r = useReg();
  const { width } = useWindowDimensions();
  const wide = width >= 640;
  const desktop = width >= layout.wideMin;
  const toc = (
    <View style={[st.toc, desktop && { marginTop: 34 }]}>
      <Kicker>İçindekiler</Kicker>
      {SECTIONS.map(([id, title], i) => (
        <Jump key={id} to={id} style={st.tocRow}>
          <Text style={st.tocNo}>§ {i + 1}</Text>
          <Text style={st.tocTitle}>{title}</Text>
        </Jump>
      ))}
    </View>
  );
  const sections = (
    <>
      <Section id="modlar">
        <P>
          <Text style={st.b}>Meydan</Text> açık, kimlikli ve kalıcıdır. Herkes takma adıyla yazar, her karar
          mühürlenir. Ad soyad, adres ve doğum tarihi yalnızca sahibine görünür; başkaları yalnızca takma adı
          görür.
        </P>
        <P>
          <Text style={st.b}>Mahzen</Text> anonim ve geçicidir. İsim yerine başlığa özel Gölge kimlikleri vardır,
          başlıklar kapasite dolunca silinir. Teşvik edilmez: Meydan&apos;ın en altında sade bir bağlantıdır.
        </P>
        <View style={st.table}>
          {PAGES.map(([page, what]) => (
            <View key={page} style={st.tableRow}>
              <Text style={st.tableKey}>{page}</Text>
              <Text style={st.tableVal}>{what}</Text>
            </View>
          ))}
        </View>
      </Section>

      <Section id="oneri">
        <P>
          Meydan&apos;da her değişiklik bir öneridir: yeni konu, alt konu, düzenleme, silme, yönetmelik değişikliği,
          konunun kapanışı. Öneri açılırken kurallar (R1–R8) denetler; ihlal varsa öneri hiç açılmaz ve gerekçesi
          yazılır. Hâtif her öneriye bir etiket yorumu bırakır (§ {num('hatif')}).
        </P>
        <P>
          Konu, alt konu ve düzenleme <Text style={st.b}>hızlı şeritte</Text> başlar: sessiz onay süresi ({r('sessiz_onay_suresi')})
          boyunca itiraz eşiğine ({r('itiraz_esigi')}) ulaşmazsa kendiliğinden kabul edilir. Eşiğe ulaşan öneri{' '}
          <Text style={st.b}>yavaş şeride</Text> geçer. Silme ve yönetmelik önerileri doğrudan yavaş şeride girer;
          kapanış, rakip metin süresinden sonra.
        </P>
        <JourneyFigure no={1} />
        <P>
          Yavaş şeritteki öneri oylanmadan önce yayında kalır (olgunlaşma): tek şehir ya da yaş grubu gibi dar
          kapsamlarda {r('olgunlasma_dar')}, geniş ilgi alanlarında {r('olgunlasma_genis')}, Genel kapsamda ve yönetmelikte{' '}
          {r('olgunlasma_genel')}. Oylamadan hemen önce açılan bir öneri kimse okumadan geçemez.
        </P>
      </Section>

      <Section id="karar-saati">
        <P>
          Yavaş şeritteki öneriler haftada bir açılan pencerede oylanır ({r('karar_saati')}). Açılış anında seçmen
          listesi, havale grafı ve yönetmelik kilitlenir; pencere boyunca değişmez.
        </P>
        <WindowFigure no={2} />
        <P>
          Oylar mühürlü verilir: deftere yalnızca oyun özeti (commit) yazılır. Kapanışta oylar tuzlarıyla açılır ve
          herkes mührü yeniden hesaplayabilir. Başkalarının oyunu taşıyan temsilcinin ve Hâtif&apos;in oyu açıktır;
          ağırlığı 1 olanınki gizlidir, yalnızca toplama katılır.
        </P>
        <P>
          Eşikler kullanılan oylar içinde hesaplanır; oy vermemek çekimserdir. Konu önerisi {r('basit_cogunluk')},
          yönetmelik {r('yonetmelik_esigi')}, başkasının içeriğini silmek {r('silme_esigi')} ister. Oturum kapanınca
          sonuç, oy verenlerin ve öneri sahiplerinin zilindeki bildirime düşer.
        </P>
        <View style={st.example}>
          <Kicker>Örnek · №9 Gece metro seferleri</Kicker>
          <Text style={st.exampleNote}>
            Uygulamadaki sayım bileşeninin kendisi: ceren üç oy taşıdığı için adıyla görünür, diğer oylar gizlidir.
            Oyların açılışını izleyin.
          </Text>
          <RevealTally result={SAMPLE_TALLY} />
        </View>
      </Section>

      <Section id="kapsam">
        <P>
          Her öneri bir seçmen kapsamında oylanır: Genel (herkes), şehir, yaş grubu ya da ilgi alanı. Şehir ve yaş
          kaydınızdan gelir. Bir ilgi alanına katılınca oy hakkı {r('ilgi_bekleme')} sonra doğar; adres değişince
          yeni şehirde {r('adres_bekleme')} sonra.
        </P>
        <P>
          Kaynakların sahibi vardır: etkinlik bütçesi Genel kapsamındır ve şehir paylarına bölünür. Bir kapsam
          yalnızca sahibi olduğu kaynağa ya da ona düşen paya karar verebilir (R2).
        </P>
        <NarrowingFigure no={3} />
        <P>
          Ters yön de korunur (eşzamanlı çoğunluk, D5): Genel bir öneri bir şehrin payını orantısız etkiliyorsa
          ({r('orantisizlik_esigi')} üstü) o şehir ayrıca oylar; öneri iki oylamada da geçmek zorundadır. Çoğunluk,
          azınlığın payını kendi oyuyla alamaz.
        </P>
      </Section>

      <Section id="havale">
        <P>
          Oyunuzu genel olarak ya da bir alan için güvendiğiniz birine devredebilirsiniz. Alan havalesi genel
          havaleyi ezer, alt alanlar üst alanın havalesini miras alır, zincir son kişiye kadar akar.
        </P>
        <DelegationFigure no={4} />
        <P>
          Havale, alan kişi kabul edince yürürlüğe girer ({r('havale_kabul_suresi')} içinde); temsilcinin oyu açık
          olduğu için kimse onayı olmadan temsilci yapılamaz. Her havale {r('havale_suresi')} sonra kendiliğinden
          düşer, bitmeden {r('havale_uyari_suresi')} önce uyarı şeridi çıkar. {r('musavir_esigi')} ya da daha fazla
          havale alan kişi Müşavir etiketi taşır. Karar Saati penceresinde havale verilemez ve geri alınamaz.
        </P>
      </Section>

      <Section id="yonetmelik">
        <P>
          Eşikler, süreler, Karar Saati&apos;nin günü, Mahzen&apos;in kapasitesi ve içerik kuralları koda değil
          Yönetmelik sayfasına yazılıdır. Değişiklik yönetmelik önerisiyle ve {r('yonetmelik_esigi')} oyla olur; oturum
          kapanınca uygulanır, o oturumun oylamaları açılıştaki değerlerle sayılır.
        </P>
        <RegulationFigure no={5} />
        <P>
          Bazı şeyler oylamanın dışındadır: yedi temel ilke (D1–D7: temel oy, öneri hakkı, Şerh, silmenin yalnızca
          oylamayla olması, eşzamanlı çoğunluk, defterin değiştirilemezliği ve bu listenin kendisi) ve her sayının
          izinli aralığı. Çoğunluk, eşiği kendi lehine yarıya indirip kazanamaz (R8).
        </P>
      </Section>

      <Section id="hatif">
        <P>
          Hâtif sistemin sembolik bilirkişisidir: yazılı kurallardan oluşur, giriş yapamaz. Her yeni öneriye bir
          etiket yorumu bırakır: alan doğru mu, metinde adı geçen kaynak etiketlenmiş mi, şehir uyuyor mu; silmede
          alıntı kuralın karşılığını taşıyor mu.
        </P>
        <OracleFigure no={6} />
        <P>
          Karar Saati&apos;nde oy verir: kurallar ve denetimler geçerse EVET, biri bile geçmezse HAYIR. Kararı her
          zaman aynıdır. Ona havale edenin oyu bu kurallara göre kullanılır.
        </P>
      </Section>

      <Section id="silme">
        <P>
          Moderatör yoktur; içerik yalnızca oylamayla silinir (D4). Başkasının mesajını silme önerisi bir içerik
          kuralına dayanmalı ve ihlal eden kısmı aynen alıntılamalıdır (R7). Eşik {r('silme_esigi')}; yazar kendi
          mesajını basit çoğunlukla sildirebilir.
        </P>
        <DeletionFigure no={7} />
      </Section>

      <Section id="kapanis">
        <P>
          Bir konu kapanış önerisiyle karara bağlanır. Konunun katılımcıları {r('kapanis_rakip_suresi')} içinde rakip
          metin ekleyebilir; Karar Saati&apos;nde onay oylaması yapılır, en çok onayı alan metin Karar olur, eşitlikte
          karar çıkmaz.
        </P>
        <ClosureFigure no={8} />
        <P>
          Kapanan konu salt okunurdur; kapanıştan {r('yeniden_acma')} sonra yeni bir konu önerisiyle yeniden
          açılabilir.
        </P>
      </Section>

      <Section id="baskin">
        <P>
          Kısa sürede açılmış, birbirine yoğun bağlı yeni hesaplar bir oylamayı ele geçirmeye çalışıyor olabilir.
          Karar Saati açılışında son {r('baskin_yeni_uye_suresi')} içinde katılanların etkileşim grafı taranır (yakın
          kayıt, ortak başlık, yanıt, havale).
        </P>
        <RaidFigure no={9} />
        <P>
          En az {r('baskin_min_kume')} kişilik, yoğunluğu {r('baskin_yogunluk_esigi')} olan ve {r('baskin_katilim_araligi')}{' '}
          içinde katılmış bir küme o oylamanın seçmen listesinden çıkar. Aynı tespit Mahzen&apos;in ifşa oylamasında
          da çalışır. Yanlış pozitif olabilir.
        </P>
      </Section>

      <Section id="defter">
        <P>
          Kabul edilen içerik, mesajlar ve sürümleri, öneriler, oy mühürleri ve açılışları, sonuçlar, silmeler,
          havaleler, Kararlar, Şerhler ve ifşa edilen Mahzen başlıkları üç düğümlü bir deftere yazılır. Kayıt
          güncellenemez ve silinemez (D6). Meydan&apos;daki her içeriğin altındaki ⌗ mühür o kaydı açar.
        </P>
        <LedgerFigure no={10} />
        <P>
          Defter sayfasındaki Doğrula, zinciri üç düğümde yeniden hesaplar ve yönetmeliğin son oylanmış hâliyle
          karşılaştırır. Sunucuyu işleten biri bir kuralı oylamasız değiştirirse fark görünür ve bir sonraki Karar
          Saati açılışında geri alınır.
        </P>
      </Section>

      <Section id="mahzen">
        <P>
          Mahzen&apos;de isim yoktur: her yazar her başlıkta ayrı bir Gölge kimliğiyle görünür, başlıklar arasında
          eşleştirilemez. Yeni yanıt başlığı üste çıkarır; başlık sayısı {r('mahzen_kapasite')}&apos;ü aşınca en alttaki
          kalıcı olarak silinir. Yaşayan başlıklar deftere yazılmaz. İçerik kuralı ve silme oylaması yoktur.
        </P>
        <CellarFigure no={11} />
        <P>
          Başlıkta yazanlar ifşa oylaması açabilir: oylama açılmadan önce yazmış olanların yarısından fazlası (
          {r('mahzen_ifsa_esigi')}) EVET derse herkesin takma adı açılır, başlık defterle mühürlenip Meydan
          görünümüne geçer ve oylamayı açan kişi adına taslak bir konu önerisi oluşur. Bu, ilk yazışta uyarıyla
          kabul edilen bir çoğunluk tiranlığıdır.
        </P>
      </Section>

      <Section id="aciklar">
        <P>Sistem her şeyi çözmez. Bilinen açıklar tasarım belgesinde yazılıdır; en önemlileri:</P>
        {[
          ['Sahte hesap', 'E-posta doğrulaması hesap çoğaltmayı yalnızca yavaşlatır; kimlik doğrulaması kapsam dışıdır. Baskın tespiti kısmen hafifletir.'],
          ['Sunucu gizli oyları görebilir', 'Tuzları pencere boyunca sunucu tutar. Defter oyların sonradan değişmediğini kanıtlar, sunucunun dürüst olduğunu kanıtlamaz.'],
          ['Oylar birkaç kişide toplanabilir', 'Havale alma sınırı yoktur; Müşavir etiketi yoğunlaşmayı görünür yapar, süre dolumu unutulmuş gücü sıfırlar.'],
          ['Hâtif kime çalışıyor?', 'Kuralları sistemi yazan yazar; Hâtif\'e havale eden oyunu kural yazarına emanet eder.'],
          ['Kod değiştirilebilir', 'Defter verideki oylamasız değişikliği yakalar ve geri alır; sunucuyu işletenin kodu değiştirmesini geri alamaz.'],
        ].map(([head, text]) => (
          <View key={head} style={st.gap}>
            <Text style={st.gapHead}>{head}</Text>
            <Text style={st.gapText}>{text}</Text>
          </View>
        ))}
      </Section>

      <Section id="sozluk">
        <View style={[wide && { flexDirection: 'row', flexWrap: 'wrap', columnGap: 24 }]}>
          {GLOSSARY.map(([term, def]) => (
            <View key={term} style={[st.term, wide && { width: '47%' }]}>
              <Text style={st.termName}>{term}</Text>
              <Text style={st.termDef}>{def}</Text>
            </View>
          ))}
        </View>
      </Section>
    </>
  );

  return (
    <Page>
      <Kicker style={{ color: paper.seal }}>Ek · Yurttaşın el kitabı</Kicker>
      <Text style={st.title}>Meşveret nasıl işler?</Text>
      <InitialText
        style={st.lede}
        text="Meşveret moderatörü olmayan bir forumdur. Konuyu da, kuralı da, silinecek mesajı da üyeler oylar; her karar değiştirilemez bir deftere yazılır."
      />
      <P>
        Çoğunluk oyu tek başına tehlikelidir: kalabalık olan, azınlığın kaynağına karar verebilir, kuralları
        kendi lehine değiştirebilir, beğenmediği görüşü silebilir. Meşveret çoğunluk tiranlığını ortadan
        kaldırmaz; onu dört mekanizmayla sınırlar.
      </P>

      <View style={[st.claims, wide && { flexDirection: 'row', flexWrap: 'wrap' }]}>
        {MECHANISMS.map(([roman, name, text, target]) => (
          <Jump key={roman} to={target} style={[st.claim, wide && { width: desktop ? '25%' : '50%' }]}>
            <Text style={st.roman}>{roman}</Text>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={st.claimName}>{name}</Text>
              <Text style={st.claimText}>{text}</Text>
              <Text style={st.claimLink}>§ {num(target)} →</Text>
            </View>
          </Jump>
        ))}
      </View>
      <P>
        Hepsi herkesin doğrulayabileceği bir deftere yazılır (§ {num('defter')}). Yanında kuralların bilerek
        işlemediği bir yer de vardır: Mahzen (§ {num('mahzen')}).
      </P>

      {/* Geniş ekranda içindekiler solda yapışık sütunda durur; bölümler sağda akar. */}
      {desktop ? (
        <Columns sideLeft stickySide sideWidth={250} side={toc} main={sections} />
      ) : (
        <>
          {toc}
          {sections}
        </>
      )}
    </Page>
  );
}

const st = StyleSheet.create({
  title: { fontFamily: fonts.serifDisplay, fontSize: 40, lineHeight: 46, color: paper.ink, marginTop: 4 },
  lede: { fontFamily: fonts.serifItalic, fontSize: 20, lineHeight: 28, color: paper.inkSoft, marginVertical: 12 },
  p: { fontSize: 17, lineHeight: 26 },
  b: { fontFamily: fonts.serifBold },
  reg: { fontFamily: fonts.monoBold, fontSize: 13, color: paper.seal },
  claims: { borderTopWidth: 2, borderBottomWidth: 2, borderColor: paper.ink, marginVertical: 16, paddingVertical: 4 },
  claim: { flexDirection: 'row', gap: 12, paddingVertical: 10, paddingRight: 12 },
  roman: { fontFamily: fonts.serifDisplay, fontSize: 30, lineHeight: 34, color: paper.seal, width: 44, textAlign: 'center' },
  claimName: { fontFamily: fonts.serifBold, fontSize: 18, color: paper.ink },
  claimText: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.ink },
  claimLink: { fontFamily: fonts.monoMedium, fontSize: 11, color: paper.seal, marginTop: 2 },
  toc: { borderWidth: 1, borderColor: paper.ink, backgroundColor: paper.sheet, padding: 12, gap: 4, marginTop: 10 },
  tocRow: { flexDirection: 'row', gap: 10, paddingVertical: 3 },
  tocNo: { fontFamily: fonts.monoBold, fontSize: 12, color: paper.seal, width: 38 },
  tocTitle: { fontFamily: fonts.serif, fontSize: 16, color: paper.ink, flex: 1, textDecorationLine: 'underline', textDecorationColor: paper.hairline },
  sectionNo: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 1.2, color: paper.seal },
  h2: { fontFamily: fonts.serifBold, fontSize: 26, lineHeight: 32, color: paper.ink },
  table: { borderTopWidth: 1, borderColor: paper.hairline, marginTop: 4 },
  tableRow: { flexDirection: 'row', gap: 12, paddingVertical: 7, borderBottomWidth: 1, borderColor: paper.hairline, flexWrap: 'wrap' },
  tableKey: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 0.6, color: paper.ink, width: 110, textTransform: 'uppercase' },
  tableVal: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.inkSoft, flex: 1, minWidth: 180 },
  example: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 12, gap: 8, marginTop: 6 },
  exampleNote: { fontFamily: fonts.serifItalic, fontSize: 14, lineHeight: 20, color: paper.inkSoft },
  gap: { borderLeftWidth: 2, borderLeftColor: paper.hairline, paddingLeft: 10, gap: 2 },
  gapHead: { fontFamily: fonts.serifBold, fontSize: 16, color: paper.ink },
  gapText: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.inkSoft },
  term: { paddingVertical: 7, borderBottomWidth: 1, borderColor: paper.hairline, gap: 1 },
  termName: { fontFamily: fonts.monoBold, fontSize: 12, letterSpacing: 0.6, color: paper.seal, textTransform: 'uppercase' },
  termDef: { fontFamily: fonts.serif, fontSize: 15, lineHeight: 21, color: paper.ink },
});
