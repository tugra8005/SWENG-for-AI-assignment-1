# Meşveret — Tasarım Belgesi

> Durum: uygulamayla güncellenmiş son sürüm. Kurulum ve demo adımları için [README.md](README.md).

## 1. Amaç ve temel iddia

Meşveret, herkesin konu önerebildiği, konuların ve yapısal değişikliklerin oylamayla kabul edildiği bir forumdur. İki modu vardır:

- **Meydan** — açık, kimlikli, kalıcı forum.
- **Mahzen** — anonim, geçici, isteğe bağlı felsefe tartışma alanı (diskur). Teşvik edilmez.

Temel iddia: sistem çoğunluk tiranlığını ortadan kaldırmaz. Onu dört mekanizmayla sınırlar:

1. **Kapsam** — bir karara yalnızca etkilenen kaynağın sahibi olan kapsam (ya da onun alt kümesi) oy verir.
2. **Havale** — oy hakkı, alan bazında güvenilen kişilere devredilebilir; uzmanlık görünür olur.
3. **Nitelikli çoğunluk** — kuralların kendisini değiştirmek 2/3 ister.
4. **Azınlık şerhi** — kaybeden taraf, karara silinemez bir görüş ekler.

Kalan açıklar §15'te bilinçli olarak belgelenmiştir.

## 2. Mimari

```mermaid
flowchart LR
  subgraph Istemci["İstemci (Expo: web + Android)"]
    M[Meydan ekranları]
    Z[Mahzen ekranları]
  end
  Istemci -- "HTTP/JSON + JWT" --> API
  subgraph Sunucu
    API["api (FastAPI, Python 3.12)"]
    SCH["zamanlayıcı (sahte saat, tick)"]
    API --- SCH
  end
  API -- SQLAlchemy --> PG[(PostgreSQL)]
  API -- Cypher --> NEO[(Neo4j)]
  API -- "outbox → HTTP" --> L1["ledger-1 (lider)"]
  L1 -- "/replicate" --> L2[ledger-2]
  L1 -- "/replicate" --> L3[ledger-3]
  CLI["meşveret-dev (yalnızca geliştirme)"] --> PG
  CLI --> NEO
```

| Bileşen | Sorumluluk |
|---|---|
| `api/` | Kimlik, öneri motoru, şeritler, havale, Karar Saati, Mahzen, Hâtif, zamanlayıcı, geliştirme CLI'ı |
| `ledger/` | Sadece eklenebilir, hash zincirli log; üç düğüm, sabit lider, HTTP çoğaltma, `/verify` |
| `client/` | Expo + expo-router + TypeScript; tek kod tabanı (web + Android) |
| PostgreSQL | Kimlik, içerik, sürümler, öneriler, itirazlar, oturumlar, oylar ve tuzlar, anlık görüntüler, Mahzen, defter outbox'ı, sahte saat |
| Neo4j | Kullanıcı grafı, havale grafı, etkileşim grafı, alan hiyerarşisi, kapsam ve kaynak sahipliği, yönetmelik maddeleri |

### 2.1 Katmanlar (api)

- `domain/` — saf fonksiyonlar: havale çözümleme, döngü kontrolü, ağırlık ve sayım, R1–R8, Hâtif etiket denetimi, baskın tespiti, başlık kimliği, diff. Veritabanı bilmez; testlerin büyük kısmı burada.
- `graph/` — Neo4j erişimi. `OntologyView` protokolünün Neo4j uygulaması (Cypher).
- `db/` — SQLAlchemy 2 modelleri.
- `services/` — iş akışları; domain fonksiyonlarını veri katmanlarıyla birleştirir.
- `routers/` — HTTP uç noktaları.

`OntologyView` protokolünün bir bellek içi, bir de Neo4j uygulaması vardır. İkisi aynı sözleşme testlerinden geçer. Böylece kurallar Docker olmadan test edilir, Cypher sorguları da aynı beklentilere karşı doğrulanır.

### 2.2 Tutarlılık

- Üç depo arasında dağıtık işlem yoktur. PostgreSQL işlemsel çekirdektir.
- Bir servis çağrısı önce PostgreSQL işlemini tamamlar, ardından Neo4j'yi günceller.
- Deftere gidecek kayıt, aynı PostgreSQL işlemi içinde `ledger_outbox` tablosuna yazılır. İstek sonunda lidere senkron gönderilir; başarısız olursa arka planda sırayla yeniden denenir. Defterdeki sıra böylece PostgreSQL'deki sırayla aynı kalır.
- Neo4j yazımı PostgreSQL commit'inden sonra başarısız olursa iki depo ayrışabilir. Ödev ölçeğinde bu kabul edilmiştir. `meşveret-dev seed --reset` her şeyi yeniden kurar.

## 3. Veri yerleşimi

| Veri | Depo | Not |
|---|---|---|
| Kullanıcı kimliği, şifre özeti (argon2), adres, doğum tarihi | PostgreSQL | Ad soyad, adres ve doğum tarihi yalnızca sahibine döner |
| `User` düğümü (id, takma ad) | Neo4j | Graf ilişkileri için |
| Konu, mesaj, mesaj sürümleri | PostgreSQL | Her satır kendi defter hash'ini taşır |
| Öneri kaydı, durum, itirazlar | PostgreSQL | `Oneri` düğümü + `ETKILER`/`SECMEN` Neo4j'de |
| Oylar, tuzlar, anlık görüntüler | PostgreSQL | Commit ve açılış deftere de yazılır |
| Alan ağacı, Kapsam, UYE, Kaynak, SAHIBI | Neo4j | Ontoloji |
| HAVALE, ETKILESIM | Neo4j | Karar Saati'nde PostgreSQL'e anlık görüntü alınır |
| YonetmelikMaddesi (değerler) | Neo4j | Kod eşik ya da süre sabiti içermez |
| Mahzen başlıkları ve mesajları | PostgreSQL | `Diskur` düğümü + yazar ilişkileri Neo4j'de (baskın tespiti için) |
| Defter kayıtları | ledger-1..3 (her birinde ayrı SQLite) | Silinmez |

## 4. Ontoloji (Neo4j)

### 4.1 Düğümler

| Etiket | Temel özellikler |
|---|---|
| `User` | `id`, `takma_ad`, `rol` (`CITIZEN` / `ORACLE`), `created_at` |
| `Alan` | `id`, `ad`, `anahtar_kelimeler` (Hâtif için) |
| `Kapsam` | `id`, `tur` (`GENEL` / `NITELIK` / `ILGI`), `alt_tur` (`SEHIR` / `YAS_GRUBU`), `deger` (ör. "İstanbul", "25-34", alan id) |
| `Kaynak` | `id`, `tur` (`ALAN` / `KONU` / `YONETMELIK_MADDESI` / `ORTAK`), `ad`, `bolunebilir`, `bolunme_turu` (ör. `SEHIR`), `paylar` (ör. şehir → puan) |
| `Konu` | `id`, `baslik`, `alan_id`; aynı zamanda bir `Kaynak` |
| `Oneri` | `id`, `tur`, `durum` |
| `Karar` | `id`, `konu_id`, `metin_id` |
| `YonetmelikMaddesi` | `anahtar`, `deger` (tipli JSON), `sema`, `aciklama`; aynı zamanda bir `Kaynak` |
| `Diskur` | `id` (Mahzen başlığı; başlık silinince düğüm de silinir) |

`Konu` ve `YonetmelikMaddesi` düğümleri ek olarak `Kaynak` etiketini taşır. Böylece sahiplik kuralları her kaynak türüne aynı biçimde uygulanır.

### 4.2 İlişkiler

| İlişki | Anlam |
|---|---|
| `(Alan)-[:ALT_ALANI]->(Alan)` | Ağaç. Ok alttan üste gider: `(alt)-[:ALT_ALANI]->(üst)` ("alt, üstün alt alanıdır"); `ALT_KUMESI` ve `ALT_KONUSU` ile aynı yön |
| `(User)-[:UYE {since, neden}]->(Kapsam)` | `neden`: `KAYIT`, `ADRES_DEGISIKLIGI`, `YAS`, `KATILIM` |
| `(Kapsam)-[:ALT_KUMESI]->(Kapsam)` | Ontolojik alt küme ilişkisi. Her NITELIK ve ILGI kapsamı GENEL'in alt kümesidir |
| `(Kaynak)-[:SAHIBI]->(Kapsam)` | Kaynağın sahibi olan kapsam |
| `(User)-[:HAVALE {alan_id \| null, since}]->(User)` | `alan_id = null` genel havale |
| `(Oneri)-[:ETKILER]->(Kaynak)` | Önerinin etkilediği kaynaklar |
| `(Oneri)-[:SECMEN]->(Kapsam)` | Önerinin seçmen kapsamı (tek) |
| `(User)-[:ETKILESIM {agirlik}]->(User)` | Türetilmiş ilişki grafı (§9) |
| `(User)-[:YAZDI {ilk}]->(Diskur)` | Mahzen başlığına ilk yazış anı |
| `(Konu)-[:ALANINDA]->(Alan)`, `(Konu)-[:ALT_KONUSU]->(Konu)` | Konu yerleşimi |

### 4.3 Kapsam türleri

- **GENEL** — e-postası doğrulanmış herkes. Oy hakkı hemen doğar.
- **NITELIK** — profil verisinden sistem hesaplar; kullanıcı katılamaz ya da ayrılamaz.
  - Şehir: adresin `il` alanından.
  - Yaş grubu: doğum tarihinden (18-24, 25-34, 35-49, 50+), o anki sahte saate göre hesaplanır.
  - Adres değişikliğinde eski şehir üyeliği hemen biter. Yeni şehirde oy hakkı `adres_bekleme` (90 gün) sonra doğar. Kayıttaki ilk şehirde oy hakkı hemen doğar (bkz. §15.3).
- **ILGI** — bir Alan'a üyelik. Kullanıcı katılır ya da ayrılır. Oy hakkı `ilgi_bekleme` (14 gün) sonra doğar.

**Alt küme ilişkisi ontolojiktir.** "İstanbul ⊂ GENEL" bir `ALT_KUMESI` kenarıyla tanımlanır, iki kapsamın o anki üye listeleri karşılaştırılarak hesaplanmaz. Üye listesi zamanla değişir; kimin kimin parçası olduğu ise yapısal bir iddiadır. İlgisiz iki kapsam (ör. İstanbul ve ILGI:Sinema) birbirinin alt kümesi değildir.

### 4.4 Kaynaklar ve sahiplik

| Kaynak | Sahibi | Bölünebilir |
|---|---|---|
| Alan | GENEL | Hayır |
| YonetmelikMaddesi | GENEL | Hayır |
| Konu | Konuyu kabul eden önerinin seçmen kapsamı | Hayır |
| "Etkinlik bütçesi" (tohum) | GENEL | Evet, şehir bazında; puan cinsinden paylar (İstanbul 4.000, Ankara 6.000, İzmir 5.000, Bursa 5.000) |
| "Ortak toplantı salonu" (tohum) | GENEL | Hayır |

Bütçe yalnızca paylarıyla temsil edilir; kaynağın toplamı payların toplamıdır (tohumda 20.000 puan). Bir dağıtım motoru yoktur; kararın hangi payı etkilediği öneride ve kararda gösterilir. Bütün adına (sahip kapsamda) oylanan öneri etkisini kapsam başına yeni paylarla bildirir (§6, R2); kabul edilen önerinin yeni payları kaynağa işlenir ve deftere `PAY_DEGISTI` olarak yazılır. Sonraki öneriler güncel paylarla hesaplanır.

## 5. Yönetmelik = veri

Tüm eşikler ve süreler `YonetmelikMaddesi` düğümlerinde durur. Kod bunları `regulation.get(anahtar)` ile okur; sabit yazılmış eşik yoktur.

- Oranlar kesir olarak saklanır (`"2/3"`). Böylece 20/30 gibi sınır durumları kayan nokta hatası olmadan karşılaştırılır.
- Her maddenin bir değer şeması vardır. YONETMELIK önerisi açılırken yeni değer bu şemaya göre doğrulanır.

| Madde | Varsayılan | Anlam |
|---|---|---|
| `sessiz_onay_suresi` | 24 saat | Hızlı şerit açık kalma süresi |
| `itiraz_esigi` | `{min: 3, oran: 1/20, aktiflik_gun: 30}` | max(3, kapsamdaki aktif üyelerin %5'i); aktif = son 30 günde giriş |
| `basit_cogunluk` | `{oran: 1/2, karsilastirma: ">"}` | Kullanılan oyların yarısından fazlası |
| `yonetmelik_esigi` | `{oran: 2/3, karsilastirma: ">="}` | Kullanılan oyların en az 2/3'ü |
| `silme_esigi` | `{oran: 2/3, karsilastirma: ">="}` | Başkasının içeriğini silmek için kullanılan oyların en az 2/3'ü (§7.4) |
| `orantisizlik_esigi` | 10 yüzde puanı | Bir alt kapsamın payındaki göreli azalma ortalama göreli değişimden en az bu kadar fazlaysa o kapsam ayrıca oylar (§7.7) |
| `red_bekleme` | 30 gün | Reddedilen hedefe yeniden öneri yasağı |
| `musavir_esigi` | 5 | Alan bazında doğrudan alınan havale sayısı |
| `ilgi_bekleme` | 14 gün | ILGI kapsamında oy hakkı beklemesi |
| `adres_bekleme` | 90 gün | Adres değişikliğinden sonra yeni şehirde oy hakkı beklemesi |
| `karar_saati` | `{gun: PAZAR, saat: "20:00", tz: "Europe/Istanbul", pencere_dakika: 60}` | Haftalık oylama oturumu |
| `kapanis_rakip_suresi` | 48 saat | KAPANIS'a rakip metin ekleme süresi |
| `yeniden_acma` | 90 gün | Kararlı konunun yeniden açılabilmesi için geçmesi gereken süre |
| `mahzen_kapasite` | 100 başlık | Aşılınca en alttaki başlık kalıcı silinir |
| `mahzen_ust_sinir` | 300 yanıt | Sonrasında başlık yükselemez |
| `mahzen_ifsa_esigi` | `{oran: 1/2, karsilastirma: ">"}` | İfşa için EVET sayısı / seçmen listesi |
| `baskin_yeni_uye_suresi` | 7 gün | Anlık görüntüden bu kadar önce ya da sonra katılanlar "yeni" sayılır |
| `baskin_katilim_araligi` | 24 saat | Bir kümenin katılım anlarının en fazla yayılabileceği aralık |
| `baskin_min_kume` | 4 | İşaretlenecek en küçük küme |
| `baskin_yogunluk_esigi` | 1/2 | Kümedeki kenar yoğunluğu eşiği |
| `baskin_min_agirlik` | 1 | Kümeleme için en düşük ETKILESIM ağırlığı |
| `etkilesim_agirliklari` | `{yanit: 1, havale: 2, yakin_kayit: 1, yakin_kayit_dk: 60, ortak_baslik: 0.5, ortak_baslik_dk: 30}` | ETKILESIM sinyal ağırlıkları |
| `olgunlasma_dar` | 48 saat | Dar etkili önerinin Karar Saati'nden önce yayında kalma süresi (§7.2) |
| `olgunlasma_genis` | 72 saat | Geniş etkili öneri için aynı süre |
| `olgunlasma_genel` | 7 gün | Genel kapsamlı ve yönetmelik önerileri için aynı süre |

**İçerik kuralları.** Yönetmelikte parametrelerin yanında ikinci bir madde türü vardır: içerik kuralı (`icerik_kurali`). Bir içerik kuralı sayı değil metindir: başlık, kuralın metni ve Hâtif'in denetimde kullandığı anahtar kelimeler. Başkasının içeriğini silme önerisi en az birine dayanmak zorundadır (R7, §7.4).

| Kural | Başlık | Kapsadığı |
|---|---|---|
| `IK-1` | Spam ve reklam | Tartışmayla ilgisi olmayan ticari tanıtım, reklam, aynı iletinin tekrarı |
| `IK-2` | Hakaret ve tehdit | Kişiyi ya da grubu aşağılayan söz, küfür, zarar verme tehdidi. Sert eleştiri hakaret değildir |
| `IK-3` | Başkasının kişisel bilgilerini ifşa etme | Başkasının telefonu, adresi, kimlik numarası gibi bilgilerini rızası olmadan paylaşmak |

"Konu dışı" gibi geniş bir kural bilerek yoktur: neyin konu dışı olduğunu çoğunluk belirler ve böyle bir kural, çoğunluğun beğenmediği her görüşü silmenin gerekçesi olur. Tohumdaki bu dar küme bir başlangıçtır, sınır değildir. Kural kümesi de oylanır (bkz. §15):

- **Değiştirme:** kuralın başlığı, metni ve anahtar kelimeleri YONETMELIK önerisiyle değişir.
- **Ekleme:** YONETMELIK önerisi (`article_action: ekle`) yeni kuralın başlığını, metnini ve anahtar kelimelerini taşır. Kod (IK-<n>) öneri açılırken verilir: yürürlükteki, kaldırılmış ve önerilmiş kodların en büyüğünün bir fazlası. Reddedilen ekleme yeni bir kodla hemen geri gelemez; R6'nın hedef anahtarı kuralın başlığıdır.
- **Kaldırma:** YONETMELIK önerisi (`article_action: kaldir`) yürürlükteki bir kuralı kaldırır. Kaldırılan kurala dayanan yeni silme önerisi R7'de reddedilir; kuyruktaki silme önerilerinde Hâtif HAYIR der (R7 oylama anında yeniden çalışır). Kaldırılan kodun geçmişi yönetmelik sayfasında kalır ve kod bir daha kullanılmaz; böylece eski sansür şeritlerindeki "IK-3 gereğince silindi" ifadesi başka bir kuralı göstermeye başlamaz.

Üçü de diğer yönetmelik değişiklikleri gibi Genel kapsamda, yavaş şeritte, `yonetmelik_esigi` (2/3) ile oylanır. Parametre maddeleri eklenemez ve kaldırılamaz; yalnızca değerleri değişir, çünkü kod onları okur.

Belgede verilen ilk 13 madde aynen alınmıştır. `mahzen_ifsa_esigi`, baskın ve etkileşim maddeleri belgenin "eşikler yönetmelik maddesi olarak durur" gereği eklenmiştir. `olgunlasma_*` maddeleri sonradan istenen olgunlaşma kuralından, `silme_esigi` ve içerik kuralları silmenin sıkılaştırılmasından gelir.

**Değişiklik kuralları:**

- Değiştirilemez maddeler (§5.1) dışında her madde yalnızca YONETMELIK önerisiyle, GENEL kapsamda, yavaş şeritte, `yonetmelik_esigi` ile değişir (R3). İçerik kuralı eklemek ve kaldırmak da buna dahildir; kural ekleme önerisinin ETKILER etiketi kural kümesidir (`madde:icerik_kurallari`).
- `yonetmelik_esigi` maddesinin kendisi de aynı eşikle değişir; muafiyet yoktur (kendini koruma). Oylama o anki değerle yapılır. Değer yalnızca değiştirilemez izinli aralığı olan ≥ 2/3 – ≥ 3/4 içinde değişir (R8, §5.2).
- Karar Saati penceresi açılırken tüm madde değerlerinin anlık görüntüsü alınır. O oturumda kabul edilen bir değişiklik bir sonraki oturumdan itibaren geçerlidir. Böylece aynı oturumdaki başka bir oylamanın eşiği sayım sırasında değişmez.

### 5.1 Değiştirilemez maddeler (yönetmeliğin tabanı)

Her şey 2/3 ile değiştirilebilseydi azınlık güvenceleri kalıcı olmazdı. Şerh hakkı, gerekçeli silme, eşzamanlı çoğunluk: hepsi yeterince büyük bir çoğunluğun iki oylamasıyla (önce eşiği düşürüp sonra güvenceyi kaldırarak) ortadan kalkabilirdi. Yönetmeliğin bu yüzden bir tabanı vardır. `YonetmelikMaddesi` düğümünde `degistirilemez: bool` alanı bulunur; değiştirilemez maddeler şunlardır:

| Madde | İlke |
|---|---|
| **D1** | Her yurttaşın bir temel oyu vardır. |
| **D2** | Her yurttaş öneri açabilir. |
| **D3** | Kaybeden taraf Şerh ekleyebilir; Şerh silinemez. |
| **D4** | İçerik yalnızca oylamayla silinebilir. |
| **D5** | Eşzamanlı çoğunluk ilkesi (§7.7). |
| **D6** | Defter değiştirilemez. |
| **D7** | Bu listenin kendisi: listeye madde eklenemez, listeden madde çıkarılamaz, bir madde değiştirilebilir yapılamaz, sayısal parametrelerin izinli aralıkları (§5.2) genişletilemez. |

- **R8** (§6): değiştirilemez bir maddeyi etkileyen (değiştirme ya da kaldırma) ya da bir parametreyi izinli aralığının dışına çıkaran YONETMELIK önerisi açılışta reddedilir: "Bu madde değiştirilemez" / "… değiştirilemez izinli aralığın dışında". Öneri kuyruğa hiç girmez; D7'deki "değiştirilmesi önerilemez" ilkesi budur. Yönetmelik servisi değiştirilemez bir maddeye ya da aralık dışı bir değere yazmayı ayrıca reddeder (ikinci savunma hattı).
- **Önceki eşik tabanları** (`yonetmelik_esigi ≥ 2/3`, `silme_esigi ≥ 2/3`) ayrı maddeler olarak kalkmıştır; artık bu iki parametrenin izinli aralığının alt ucudur (§5.2).
- **İlkeleri kod uygular.** D1–D6 metinleri bilgilendiricidir: oy ağırlığı, R5, Şerh kuralları, silme akışı, eşzamanlı çoğunluk ve defter kodun kendisidir. Bu maddeler, o davranışları yöneten yönetmelik yolunun oylamayla kapatılamayacağını kayda geçirir.
- **Arayüz:** yönetmelik sayfasının başında, çift çerçeveli ve kilit işaretli bir "Değiştirilemez Maddeler" bölümü vardır (anayasa sayfası düzeni). Her sayısal parametrenin değerinin altında kilitli "izinli: …" satırı görünür.

**"Her şey oylamayla" şartıyla bilinçli çelişki.** Gereksinim 11 forumda her şeyin oylamayla yürümesini ister. Değiştirilemez maddeler bu şartı bilerek çiğner. Tamamen oylanabilir bir sistemde azınlık güvencesi yalnızca daha yüksek bir çıtadır, taban değildir. 2/3'lük bir güvence, 2/3'lük bir çoğunluğa karşı hiçbir şey korumaz. Eşiği yükseltmek bunu değiştirmez; yalnızca gereken çoğunluğu büyütür (bkz. §15, 10. madde). Bir güvencenin güvence olabilmesi için en az bir şeyin oylamanın dışında kalması gerekir. Meşveret o şeyi olabildiğince dar tutar: yedi ilke ve her sayısal parametrenin izinli aralığı. Geri kalan her şey, eşiklerin aralık içindeki değerleri de dahil, oylamayla değişir.

**Anayasal benzerler.**

- **Türkiye Cumhuriyeti Anayasası, madde 4:** Devletin şeklinin Cumhuriyet olduğunu belirten 1. madde, Cumhuriyetin niteliklerini sayan 2. madde ve 3. madde hükümleri değiştirilemez ve değiştirilmesi teklif edilemez. "Teklif edilemez" ifadesi R8'in açılışta reddetmesinin karşılığıdır: değişiklik oylamaya sunulmaz, oylamada reddedilmez.
- **Almanya Federal Cumhuriyeti Temel Yasası, madde 79(3) ("sonsuzluk maddesi"):** Federasyonun eyaletlere bölünmesine, eyaletlerin yasamaya ilke olarak katılımına ya da 1. madde (insan onuru) ile 20. madde (demokratik ve sosyal federal devlet, hukuk devleti) ilkelerine dokunan anayasa değişikliği kabul edilemez. Meşveret'teki D5 (eşzamanlı çoğunluk), eyaletlerin yasamaya katılım güvencesinin küçük ölçekli bir karşılığıdır: bütün, parçanın ayrı sesini oylamayla kaldıramaz.

İki benzerin de bedeli aynıdır: bugünün kurucuları yarının çoğunluklarını bağlar. Bu bedel §15'te açık olarak yazılıdır.

### 5.2 İzinli aralıklar

Açık 29'daki sorun şuydu: taban ilkeleri korur ama onları çevreleyen parametreleri korumaz. `ilgi_bekleme` yıllara çıkarılırsa D2, `orantisizlik_esigi` 100'e çıkarılırsa D5 fiilen boşalır. Bu yüzden her sayısal parametrenin değiştirilemez bir izinli aralığı (en küçük, en büyük; uçlar dahil) vardır. Aralık, parametre tanımının bir parçasıdır (`Article.allowed`) ve D7 kapsamında değiştirilemez. Değer aralığın içinde oylamayla değişir; aralık dışına çıkan öneri R8'le açılışta reddedilir. Oranlarda karşılaştırma katılık üzerinden yapılır: "> 1/2" ile "≥ 2/3" arasındaki bir eşik, "> 1/2"den gevşek ve "≥ 2/3"ten katı olamaz.

**Bu aralıklar benim, yani tasarımcının seçimidir ve keyfîdir.** Hiçbiri bir ölçüme, deneye ya da kaynağa dayanmaz; gerekçeler sezgiseldir. Sessiz onay için 12 saat yerine 10 saat, itiraz oranı için %20 yerine %25 de aynı ölçüde savunulabilirdi. Aralıkların amacı doğru değeri bulmak değil, en kötü değerleri dışarıda bırakmaktır: bir ilkeyi fiilen boşaltan ya da sistemi kilitleyen uçları. Bir aralığın yanlış seçildiği anlaşılırsa oylamayla düzeltilemez (bkz. §15, 31. madde).

| Parametre | Varsayılan | İzinli aralık | Gerekçe |
|---|---|---|---|
| `basit_cogunluk` | > 1/2 | > 1/2 – ≥ 2/3 | 1/2'nin altı azınlık yönetimi olur; 2/3'ün üstü sıradan kararları nitelikli çoğunluğa çevirir |
| `yonetmelik_esigi`, `silme_esigi` | ≥ 2/3 | ≥ 2/3 – ≥ 3/4 | 2/3 önceki tabandır; 3/4'ün üstü fiilen kilitler (açık 10) |
| `sessiz_onay_suresi` | 24 saat | 12 saat – 72 saat | 12 saatten kısası bir gecelik yoklukla kaçırılır; 72 saatten uzunu hızlı şeridi yavaşlatır |
| `itiraz_esigi` | en az 3, %5, 30 gün | oran %2 – %20; en az 3–20 itiraz; aktiflik 7–90 gün | %2'nin altında tek kişi her şeyi durdurur, %20'nin üstünde itiraz fiilen imkânsızlaşır. Asgari sayı 3'ün altına inemez: küçük bir kapsamda oran eşiği 1'e düşer ve asgari sayı 1 olursa tek bir itiraz her hızlı şerit önerisini yavaş şeride iter; hızlı şerit tek kişinin vetosuna dönüşür. 20'nin üstü küçük kapsamlarda itirazı fiilen imkânsızlaştırır. Aktiflik penceresinin aralığını uygulama sırasında ben seçtim: bir haftadan kısa pencere tatildeki üyeleri düşürür, üç aydan uzun pencere ayrılmış üyelerle eşiği şişirir |
| `red_bekleme` | 30 gün | 7 – 90 gün | Bir haftadan kısası yıpratmayı engellemez; üç aydan uzunu reddedilen fikri fiilen yasaklar |
| `olgunlasma_dar/genis/genel` | 48 saat / 72 saat / 7 gün | 24 saat – 14 gün | Bir günden kısası son dakika sıkıştırmayı geri getirir; iki haftadan uzunu kararları durdurur |
| `ilgi_bekleme` | 14 gün | 0 – 30 gün | Bekleme bir koruma önlemidir, hak değildir; kaldırılabilir. 30 günden uzunu D2'yi yeni gelenler için boşaltır |
| `adres_bekleme` | 90 gün | 0 – 180 gün | Aynı mantık; şehir değiştirmek ilgi alanı değiştirmekten ağır olduğu için üst sınır daha yüksek |
| `orantisizlik_esigi` | 10 yüzde puanı | 5 – 30 yüzde puanı | 5'in altında her yuvarlama farkı bir veto doğurur; 30'un üstü D5'i boşaltır |
| `musavir_esigi` | 5 | 3 – 50 havale | 3'ün altında etiket anlamsızlaşır; 50'nin üstünde küçük bir toplulukta kimse Müşavir olamaz |
| `kapanis_rakip_suresi` | 48 saat | 24 saat – 7 gün | Rakip metin yazmaya en az bir gün; bir haftadan uzunu kapanışı sürüncemede bırakır |
| `yeniden_acma` | 90 gün | 30 – 365 gün | Bir aydan kısası kararı anlamsızlaştırır; bir yıldan uzunu kararı fiilen kalıcı yapar |
| `karar_saati` (pencere) | 60 dakika | 30 – 180 dakika | Uygulamada ben seçtim: yarım saatten kısası oy vermeyi zorlaştırır; üç saatten uzunu "saat" olmaktan çıkar. Gün ve saat sayısal değildir, aralıkları yoktur |
| `mahzen_kapasite` | 100 başlık | 30 – 300 başlık | Uygulamada ben seçtim. 30'dan azı başlıkları tartışma olgunlaşmadan siler ve başlık yağdırmayı (§15, 2. madde) ucuzlatır; geçicilik silme aracına döner. 300'den fazlası çürümeyi fiilen kaldırır |
| `mahzen_ust_sinir` | 300 yanıt | 50 – 1000 yanıt | Uygulamada ben seçtim. 50'den azı canlı bir tartışmayı erken dondurur; 1000'den fazlası tek bir başlığın Mahzen'in tepesinde süresiz kalmasına izin verir |
| `mahzen_ifsa_esigi` | > 1/2 | > 1/2 – ≥ 3/4 | Uygulamada ben seçtim. Yarının altında bir azınlık herkesi ifşa eder; 3/4'ün üstünde ifşa fiilen imkânsızlaşır |
| `baskin_*`, `etkilesim_agirliklari` | §9 | yeni üye 1–30 gün; katılım aralığı 1 saat – 7 gün; en küçük küme 3–20; yoğunluk ≥ 1/3 – ≥ 1; en düşük ağırlık 0,5–10; ağırlıklar 0,1–10; pencereler 5–240 dakika | Uygulamada ben seçtim. Tespitin tamamen kapatılmasını (ör. en küçük küme 1000) ya da herkesin işaretlenmesini (ör. en küçük küme 1) engeller |

Görevde anılan `havale_suresi` Meşveret'te yoktur: havale geri alınana kadar geçerlidir. Bu yüzden aralığı da yoktur.

### 5.3 Yönetmeliğin defterdeki izi

Değiştirilemezlik bir yazılım kuralıdır (§15, 30. madde): sunucuyu işleten, kodu ya da veriyi değiştirerek R8'i ve aralıkları atlatabilir. Bu engellenemez, ama tespit edilebilir kılınabilir.

- **Kayıt.** Yönetmeliğin tam hâli kurulumda (başlangıç kaydı) ve her Karar Saati oturumunun sonunda, o oturumda kabul edilen değişiklikler uygulandıktan sonra `YONETMELIK_DURUMU` kaydı olarak deftere yazılır. Tam hâl, madde başına değer, `degistirilemez` bayrağı ve izinli aralıktır; aralık hem metniyle hem uygulanan sınırlarıyla girer, böylece metnine dokunmadan genişletilen bir sınır da hash'i değiştirir. Kayıt tam hâli ve kanonik JSON'unun SHA-256 hash'ini taşır.
- **Doğrulama.** `/ledger/verify`, çalışan kodun uyguladığı yönetmeliğin hash'ini yeniden hesaplar ve defterdeki son `YONETMELIK_DURUMU` kaydıyla karşılaştırır. Değerler graftan, bayraklar graf düğümlerinden, aralıklar çalışan koddan okunur. Durumlar "tutarlı", "farklı" ve "kayıt yok"tur. "Farklı" durumunda hangi maddelerin değiştiği listelenir. Defter ekranında bu sonuç "Yönetmelik bütünlüğü" kutusunda görünür.
- **Neyi yakalar.** Oturumlar arasında oylamasız yapılan her yönetmelik değişikliğini: grafa ya da veritabanına doğrudan yazılan bir değer, kaldırılan bir `degistirilemez` bayrağı, kodda genişletilen bir aralık. Meşru değişiklikler yalnızca oturum sonunda uygulandığı ve hemen ardından kaydedildiği için, iki oturum arasındaki her fark oylamasızdır. Tespit penceresi bir sonraki oturum kapanışına kadardır: kapanış kaydı yönetmeliğin o anki hâlini, sessiz değişiklik dahil, olduğu gibi yazar ve ondan sonra doğrulama "tutarlı" der (§15, 30. madde).
- **Demo.** `meşveret-dev tamper-regulation` bir değeri oylamasız değiştirir (§12); README senaryo 12.
- **Neyi yakalamaz.** §15, 30. maddede.

## 6. Denetim kuralları

Her öneri açılırken kurallar çalışır. İhlal varsa öneri kaydedilmez ve Türkçe gerekçe döner. Kurallar saf fonksiyonlardır, `OntologyView` üzerinden çalışır.

| Kural | İçerik | Gerekçe |
|---|---|---|
| **R1** | ALT_KONU'nun alanı, üst konunun alanının kendisi ya da alt ağacında olmalı | Konu ağacı alan ağacıyla çelişmez; alt konu üst konunun konusundan kopamaz |
| **R2** | Seçmen kapsamı S, etkilenen her kaynağın sahibi O için: S = O ise geçer. S ⊂ O ise: kaynak S'nin türüne göre bölünebiliyorsa etki S'nin payına daraltılır ve öneride gösterilir ("Bu karar yalnızca İstanbul payını etkiler"); bölünemiyorsa red. S ⊄ O ise (üst küme ya da ilgisiz) red ("Bu kapsam bu kaynak hakkında karar veremez: kaynağın sahibi X"). **Ters yön:** S = O ve kaynak bölünebilirse öneri etkisini yapılandırılmış olarak bildirmeli: kapsam başına yeni pay (`{kapsam: yeni_pay}`); metin tek başına yetmez, bildirmeyen öneri reddedilir. Payları değiştirmeyen öneri boş etki bildirir. Daraltılmış öneri (S ⊂ O) yalnızca kendi payını değiştirebilir | Karar veren grup, kaynağa sahipliğini ontolojide göstermek zorundadır (ispat yükünün tersine çevrilmesi). Çoğunluk, azınlığa ait kaynak hakkında karar veremez. Ters yönde bütün, bir alt kapsamın payını gasp edemez: etkinin yapılandırılmış olması orantısızlığın ölçülebilmesini sağlar (§7.7) |
| **R3** | YonetmelikMaddesi'ni etkileyen öneri YONETMELIK türünde olmalı; seçmeni GENEL, şeridi yavaş, eşiği `yonetmelik_esigi` | Kurallar herkesi bağlar; hızlı ve sessiz değişemez |
| **R4** | Havale döngüsü yasak (alan başına; mirası da kapsar, §8.2) | Döngüde oy hiçbir yere varmaz |
| **R5** | Oy hakkı = kapsam üyeliği + ilgili bekleme süresinin dolmuş olması. Öneri sahibi de seçmen kapsamında oy hakkına sahip olmalı | Bir gruba, o grubun parçası olmayan biri öneri getiremez; yeni katılanlar hemen karar veremez |
| **R6** | Aynı hedefe oylamayla reddedilmiş öneri `red_bekleme` süresince yeniden açılamaz | Aynı öneriyi üst üste açarak yıpratmayı önler |
| **R7** | Başkasının içeriğini silme önerisi en az bir içerik kuralına (IK-1…) dayanmalı ve kuralı ihlal eden kısmı hedef metinden aynen alıntılamalı. Alıntı hedefin güncel metninde bütün kelimelerle, art arda geçmeli (büyük/küçük harf ve noktalama farkı yok sayılır). Yazarın kendi mesajı için gerekçe gerekmez; konu silme hiçbir zaman "kendi" sayılmaz | Silme istisnadır; gerekçesiz silme, çoğunluğun beğenmediği görüşü gizlemesinin yoludur (§7.4) |
| **R8** | Değiştirilemez bir maddeyi (D1–D7) etkileyen ya da bir sayısal parametreyi değiştirilemez izinli aralığının (§5.2) dışına çıkaran YONETMELIK önerisi açılışta reddedilir ("Bu madde değiştirilemez") | Tamamen oylanabilir bir sistemde azınlık güvencesi yalnızca daha yüksek bir çıtadır; taban için bir şeyin oylamanın dışında kalması gerekir (§5.1) |

**red_bekleme hedef anahtarı:** KONU → (alan, normalize başlık); ALT_KONU → (üst konu, normalize başlık); DUZENLEME ve SILME → içerik; YONETMELIK → madde; KAPANIS → konu. Yalnızca oylamayla reddedilen öneriler sayılır; açılışta denetimden dönenler kayda girmez.

**Daralmanın sunumu.** Daralan öneride oylanan şey talep değil etkidir; arayüz bunu başlıkta gösterir. Başlık alanı iki satırdır: üstte küçük ve üstü çizili "Talep: Etkinlik bütçesinin tamamı İstanbul'a", altta büyük "Etki: Etkinlik bütçesinin İstanbul payı". Etki başlığı otomatik üretilir: kaynak adının tamlayan hâli + kapsam adı + "payı". Daralma kutusu oranı ("4.000 / 20.000 puan (%20)") ve bir çubuğu gösterir: kaynağın tamamı gri, etkilenen pay bordo. Etkilenen kaynaklar listesinde kaynak "Etkinlik bütçesi — yalnızca İstanbul payı (4.000 / 20.000)" diye yazılır. Hâtif'in yorumu da daralmayı anar: "Talep kaynağın tamamını hedefliyordu; seçmen kapsamı yalnızca İstanbul payına karar verebilir, daraltma uygulandı." Öneri listelerindeki kartlar aynı düzeni kullanır. Daralan öneri kabul edilip konu olduğunda konu sayfası ve konu listeleri de aynı iki satırlı başlığı ve daralma kutusunu gösterir; konunun kapsamı talep değil etkidir.

**Türe özgü geçerlilik:** hedef mevcut ve açık olmalı; kendi tartışma mesajı için DUZENLEME açılamaz (serbest sürümleme var); Şerh hiçbir önerinin hedefi olamaz; aynı konuda ikinci KAPANIS açılamaz (rakip metin olarak eklenir); yeniden açma `yeniden_acma` süresine bağlıdır.

**Etiketleri öneri sahibi seçer.** Seçmen kapsamını ve KONU'da etkilenen kaynakları öneriyi açan kişi belirler. Otomatik bağlanan etiketler: SILME, DUZENLEME ve KAPANIS'te hedef konu; YONETMELIK'te madde.

### 6.1 Hâtif'in etiket denetimi

Hâtif her yeni öneriye bir "etiket önerisi" yorumu bırakır. Denetim kural tabanlı ve deterministiktir:

- **H1 — Alan:** başlık ve metindeki kelimeler alanların `anahtar_kelimeler` listeleriyle eşlenir. En çok eşleşen alan (en az 2 eşleşme) seçilen alan değilse ve seçilen alan onun atası da değilse, uyuşmazlık sayılır.
- **H2 — Etiketlenmemiş kaynak:** metin bir kaynağın adını ya da eş adını geçiriyor ama öneri o kaynağı ETKILER olarak etiketlememişse uyuşmazlık sayılır. Bu denetim, R2'den kaçmak için kaynak etiketini atlama manipülasyonunu yakalamaya yöneliktir.
- **H3 — Şehir:** metin tek bir şehrin adını geçiriyor, seçmen kapsamı ise başka bir şehrin kapsamıysa uyuşmazlık sayılır.
- **H4 — İçerik kuralı (yalnızca SILME):** dayanılan her içerik kuralının anahtar kelimelerinden en az biri, ihlal edildiği söylenen alıntıda geçmeli. Karşılığı olmayan kural varsa HAYIR. Hâtif hangi kelimeyi bulduğunu ya da bulamadığını yorumuna yazar: "İçerik kuralı IK-2 (Hakaret ve tehdit): belirtilen kısımda karşılığı var ('cahil')." Kendi mesajının silinmesinde bu denetim yapılmaz.

**Hâtif'in oyu:** oylama anında R1–R8 yeniden çalışır ve H1–H4 değerlendirilir. Hepsi geçerse EVET, biri bile geçmezse HAYIR. R1–R8'i ihlal eden öneriler açılışta zaten reddedildiği için, H1–H4 olmasa Hâtif pratikte her öneriye EVET derdi. R7 oylama anında hedefin güncel metniyle yeniden çalışır: yazar ihlal eden kısmı oylamadan önce düzeltirse alıntı artık metinde geçmez ve Hâtif HAYIR der.

## 7. Öneri yaşam döngüsü

```mermaid
stateDiagram-v2
  [*] --> DRAFT: Mahzen ifşasından taslak
  [*] --> SILENT: KONU / ALT_KONU / DUZENLEME açılır
  [*] --> QUEUED: SILME / YONETMELIK açılır
  [*] --> RIVAL_PERIOD: KAPANIS açılır
  DRAFT --> SILENT: sahibi etiketleri seçip gönderir
  SILENT --> ACCEPTED: süre doldu, itiraz < eşik
  SILENT --> QUEUED: itiraz ≥ eşik (hemen)
  RIVAL_PERIOD --> QUEUED: kapanis_rakip_suresi doldu
  QUEUED --> VOTING: Karar Saati penceresi açıldı ve öneri olgunlaştı
  VOTING --> ACCEPTED
  VOTING --> REJECTED
```

### 7.1 Hızlı şerit (sessiz onay)

- KONU, ALT_KONU ve DUZENLEME `sessiz_onay_suresi` boyunca açık kalır.
- Seçmen kapsamında R5'e göre oy hakkı olan herkes bir kez itiraz edebilir. İtiraz kişiseldir; havale uygulanmaz.
- Eşik `itiraz_esigi`dir ve kapsamdaki aktif üye sayısına göre itiraz anında hesaplanır.
- Eşiğe ulaşan öneri hemen yavaş şeride düşer. Olgunlaştıktan sonraki ilk Karar Saati'nde `basit_cogunluk` ile oylanır (§7.2).

### 7.2 Yavaş şerit ve Karar Saati

- Haftalık oturum `karar_saati` maddesine göre açılır. Pencere açılırken kuyrukta bekleyen ve olgunlaşmış öneriler (KAPANIS için rakip süresi de dolmuş olanlar) oturuma alınır.
- **Anlık görüntü** (pencere açılırken, öneri başına):
  - seçmen listesi (R5 + baskın dışlaması, §9),
  - önerinin alanı için çözülmüş havale haritası,
  - yönetmelik değerleri.

  Hepsi PostgreSQL'e JSONB olarak yazılır. Sayım yalnızca bu görüntüyü kullanır.
- **Kilit:** pencere açıkken havale verme ve geri alma reddedilir ("Karar Saati penceresi açık; havaleler bu oturum için kilitli").
- **Mühürlü oy (commit-reveal):**
  - Oy anında deftere yalnızca `commit = sha256(kanonik_json(oturum, öneri, seçmen, seçim) ‖ tuz)` yazılır. Tuzu ve seçimi sunucu PostgreSQL'de tutar.
  - Pencere kapanınca tüm seçimler ve tuzlar deftere açılır; herkes her commit'i yeniden hesaplayabilir.
  - Meydan'da oy bir kez verilir ve pencere boyunca değiştirilemez.
- **Eşikler:** YONETMELIK için `yonetmelik_esigi`; başkasının içeriğini silen SILME için `silme_esigi`; kendi mesajını silen SILME ve itiraz almış hızlı şerit önerileri için `basit_cogunluk`. Oranlar yalnızca kullanılan (çekimser olmayan) ağırlıklar üzerinden hesaplanır. Yeter sayı (kuorum) yoktur; hiç oy kullanılmamışsa öneri reddedilir.
- **Sonuç açıklama ekranı:** açılan oylar tek tek düşer (takma ad, ağırlık, seçim); yanında çubuk ve eşik çizgisi ilerler.

**Olgunlaşma.** Bir öneri Karar Saati'nde ancak yeterince uzun süre yayında kaldıktan sonra oylanır. Süre önerinin etkisiyle ölçeklenir; etki, seçmen kapsamının genişliğiyle ölçülür:

| Sınıf | Seçmen kapsamı | Madde | Süre |
|---|---|---|---|
| dar | Tek bir NITELIK kapsamı (şehir, yaş grubu) ya da yaprak alanın ILGI kapsamı | `olgunlasma_dar` | 48 saat |
| geniş | Yaprak olmayan alanın ILGI kapsamı | `olgunlasma_genis` | 72 saat |
| genel | GENEL kapsam ve tüm YONETMELIK önerileri | `olgunlasma_genel` | 7 gün |

- Süre, önerinin yavaş şeritte yayına girdiği andan sayılır. Yavaş şeritte doğan türlerde (SILME, YONETMELIK, KAPANIS) bu açılış anıdır. Hızlı şeritten itirazla düşen önerilerde düştüğü andır (`queued_at`); sessiz onayda geçen süre olgunlaşmaya sayılmaz.
- Pencere açıldığında olgunlaşmamış öneri o oturuma alınmaz. Kuyrukta kalır ve olgunlaştıktan sonraki ilk oturuma kayar. Arayüz öneri sayfasında, kartlarda ve Karar Saati kuyruğunda bunu "Olgunlaşıyor — 11 Ekim Pazar 20:00 oturumunda oylanacak" diye gösterir. `run-karar-saati` de oturuma alınmayan önerileri listeler.
- Olgunlaşma maddeleri de pencere açılırken okunur. Süreyi değiştiren bir karar sonraki oturumdan itibaren uygulanır.

*Gerekçe.* Önlenen şey son dakika öneri sıkıştırmadır: pencereden hemen önce açılan bir öneri, seçmenler okuyup tartışamadan oylanır. Takvime bağlı bir kesim ("Pazar 18:00'den sonra açılanlar sonraki haftaya") bunu çözmez. Kesimden bir dakika önce açılan öneri yine yalnızca birkaç saat yayında kalır. Kesim, etkisi tek bir şehirle sınırlı bir öneriye de herkesi bağlayan bir yönetmelik değişikliğine de aynı süreyi tanır. Öneri başına süre, sıkıştırmayı açılış anından bağımsız olarak engeller ve etkisi geniş olan öneriye daha uzun inceleme süresi verir. Son dakikada oy kaydırmak için ayrıca bir önlem gerekmez. Oylar pencere boyunca mühürlüdür; kimse ara sonucu görüp ona göre oy veremez (yalnızca kimin oy verdiği görülür; bkz. §15, 17. madde).

### 7.3 Kapanış, Karar ve Şerh

- Konunun herhangi bir katılımcısı (konuyu açan ya da tartışmada yazmış olan) KAPANIS önerisi ve karar metni açabilir.
- `kapanis_rakip_suresi` boyunca diğer katılımcılar rakip metin ekleyebilir.
- Karar Saati'nde **onay oylaması** yapılır: her seçmen kabul edebileceği tüm metinleri işaretler. Metnin puanı, onu işaretleyen seçmenlerin ağırlıkları toplamıdır.
- **En yüksek puanı alan tek metin Karar olur.** Eşitlik varsa ya da hiç onay yoksa Karar çıkmaz ve öneri reddedilmiş sayılır.
- Kaybeden bir metnin sahibi ya da o metni onaylamış bir seçmen Karar'a bir **Şerh** ekleyebilir. Kişi başına Karar başına bir Şerh hakkı vardır. Şerh düzenlenemez, hiçbir önerinin hedefi olamaz ve deftere yazılır.
- Kararlı konunun tartışma alanı salt okunur olur.
- **Yeniden açma:** `yeniden_acma` süresi geçtikten sonra, yeni bir öneri türü eklemeden, `reopens_topic_id` alanlı bir KONU önerisiyle yapılır. Karar ve Şerhler geçmişte kalır.

### 7.4 Silme

Hocanın ana şartı "tartışmalar silinmez"dir. Silme bu yüzden günlük bir araç değil istisnadır:

- **Gerekçe (R7):** başkasının içeriğini silme önerisi en az bir içerik kuralına (IK-1 spam ve reklam, IK-2 hakaret ve tehdit, IK-3 başkasının kişisel bilgilerini ifşa etme) dayanır ve kuralı ihlal eden kısmı metinden aynen alıntılar. Gerekçesiz öneri açılışta reddedilir.
- **Eşik:** `silme_esigi`, kullanılan oyların en az 2/3'ü.
- **İstisna:** kendi mesajının silinmesi için gerekçe gerekmez ve basit çoğunluk yeter. Konu silme bu istisnadan yararlanmaz; konu başkalarının mesajlarını da götürür.
- **Hâtif:** dayanılan kuralın anahtar kelimelerini alıntıda arar (H4, §6.1); bulamazsa HAYIR oyu verir ve nedenini yorumuna yazar.
- **Sonuç:** içerik sitede gizlenir; yerine tam genişlikte bir sansür şeridi konur. Şerit dayanılan kuralı anar: "#11 · IK-1 gereğince silindi"; kendi mesajında "#12 · yazarının isteğiyle silindi". İçerik defterde kalır ve defter ekranından hash ile görüntülenebilir.

*Neden 2/3 ve gerekçe.* Basit çoğunlukla ve gerekçesiz silme, çoğunluğun rahatsız olduğu her görüşü oylamayla gizlemesine izin verir; bu, oylamayla işleyen bir sansürdür (çoğunluk sansürü). Önlem iki katmanlıdır:

1. **Gerekçe, neyin silinebileceğini daraltır.** Silme ancak yönetmelikte yazılı, dar bir ihlale dayanabilir, ve ihlal metinde gösterilmelidir. Kural kümesini genişletmek (kural eklemek ya da metnini genişletmek) de bir yönetmelik değişikliğidir ve 2/3 ister (§5). "Yanlış", "konu dışı", "beğenmedim" silme gerekçesi değildir. Alıntı zorunluluğu tartışmayı görüşten ihlale çeker: seçmenler "bu görüş doğru mu?" diye değil, "bu cümle hakaret mi?" diye oy verir.
2. **2/3, kimin silebileceğini daraltır.** Konu açmak ve bir fikri kabul etmek geri alınabilir kararlardır (yeniden açma, yeni öneri). Silme ise bir sesi tartışmadan çıkarır ve çoğunlukla azınlığın sesidir. Nitelikli çoğunluk, silmeyi yalnızca geniş bir uzlaşının olduğu durumlarla sınırlar. Seçmenlerin üçte birinden fazlası bir içeriğin kalmasını istiyorsa, o içerik tartışmanın meşru bir parçası sayılır. Yönetmelik değişikliğiyle aynı eşik bilinçlidir: ikisi de oyun kuralına dokunur.

Kendi mesajında yazarın rızası vardır. Silinen ses, silinmesini isteyen sestir; çoğunluk sansürü riski yoktur. Bu yüzden basit çoğunluk yeter. Oylama yine de gerekir, çünkü başkalarının verdiği yanıtlar o mesaja dayanır (bkz. §15).

### 7.5 Düzenleme

- Kendi tartışma mesajını düzenlemek serbesttir; her düzenleme yeni bir sürüm olarak eklenir ve geçmiş herkese açıktır.
- Başkasının mesajı ya da bir konunun açılış metni (oylanarak kabul edilmiş metin; sahibi için de geçerli) DUZENLEME önerisinden geçer.
- Her iki durumda da satır ve kelime bazlı diff görünümü vardır.

### 7.6 Tartışma alanı

Kabul edilmiş her konunun altında kalıcı, oylamasız yazılan bir tartışma alanı vardır. Yanıtlar bir mesaja referans verebilir; bu, ETKILESIM sinyalidir.

### 7.7 Eşzamanlı çoğunluk (bölünebilir kaynakta orantısız etki)

R2 bir alt kapsamın bütünün kaynağı hakkında karar vermesini engeller. Bu bölüm ters yönü ele alır: bütünün (ör. Genel) bir alt kapsamın payını gasp etmesi. İstanbul 20.000 puanlık bütçenin 4.000'ine sahipse, Genel'deki bir çoğunluk bu payın yarısını Ankara'ya aktarmayı oylayabilir. Sayıca azınlık olan İstanbul seçmenleri Genel oylamasında her zaman yenilir.

**Kural.**

- **Pay etkisi zorunludur (R2, ters yön).** Bölünebilir kaynağı etkileyen ve bütün adına oylanan öneri etkisini kapsam başına yeni paylarla bildirir. Göreli değişim her alt kapsam için (yeni − eski) / eski'dir.
- **Orantısızlık.** Bir alt kapsamın payı azalıyor ve bu azalma, payı olan tüm alt kapsamların ortalama göreli değişiminden en az `orantisizlik_esigi` (varsayılan 10) yüzde puanı fazlaysa, o kapsam *orantısız etkilenen* sayılır. Herkese eşit oranda kesinti orantısız değildir: her şehrin payında %10 kesinti ortalamayla aynıdır. "İstanbul payının yarısı Ankara'ya" önerisinde İstanbul %-50, ortalama %-4,2'dir; fark 45,8 puan.
- **Ayrı oylama.** Orantısız etkilenen her alt kapsam için aynı Karar Saati'nde ayrı bir oylama açılır. Seçmenleri o kapsamda oy hakkı olanlardır. Havale yalnızca o kapsamın seçmenleri arasında çözülür: dışarıya giden havale bu oylamada uygulanmaz ve üye oyunu kendisi verir. Pusulada ayrı bir satırdır ve oy ayrı mühürlenir; aynı kişi iki oylamada farklı oy verebilir.
- **Eşzamanlı çoğunluk.** Öneri ancak hem kendi seçmen kapsamında hem de orantısız etkilenen her alt kapsamda gerekli çoğunluğu alırsa geçer. Sonuç ekranı her sayımı ayrı gösterir: "Genel: %64 EVET ✓ · İstanbul: %22 EVET ✗ → Reddedildi".
- **Yavaş şerit.** Orantısız etkilenen kapsamı olan öneri sessiz onayla geçemez (veto atlanmış olurdu); doğrudan Karar Saati kuyruğuna girer. Orantısız etkisi olmayan pay değişikliği (eşit kesinti) normal hızlı şeritte kalır.
- **Muafiyet.** R2 ile daraltılmış öneriler (yalnızca kendi payını etkileyenler) bu kuraldan muaftır; kendi payı üzerinde karar veren zaten o kapsamdır.
- **Hâtif** orantısız etkilenen kapsamları önerinin altındaki yorumunda sayılarıyla listeler. Alt kapsam oylamalarında oy vermez; şehir kapsamlarının üyesi değildir.

**Veto yalnızca kendi payı üzerindedir ve geçersiz kılınamaz.** Alt kapsamın ayrı oylaması bir vetodur. Kapsamı dardır: yalnızca o kapsamın payını orantısız azaltan önerileri durdurabilir. Başka kapsamların payları, konunun kendisi ya da orantılı bir kesinti bu vetoya tabi değildir. Vetoyu aşmanın bir yolu (ör. Genel'de 3/4 ile geçersiz kılma) bilinçli olarak yoktur. Böyle bir mekanizma, korunmak istenen durumu (bütünün sayısal çoğunluğunun bir parçayı ezmesi) yalnızca daha yüksek bir eşikle yeniden mümkün kılar; gasp daha pahalı hâle gelir ama yasallaşır. Payını kaybetmek istemeyen kapsamın "hayır"ı kesin kabul edilmiştir. Bedeli §15'te: orantısız ama haklı bir yeniden dağıtım da engellenebilir.

**Neden: hocanın "bölme" ipucu.** Gereksinim 16, çoğunluğun azınlığı ezmesini "uzmanlar ve bölme" ile engellemeyi ister. Kapsam ve R2 bölmenin bir yüzüdür: karar kararı etkilenenlere daraltılır. Eşzamanlı çoğunluk öbür yüzüdür: karar bütünde alınır ama etkilenen parçanın ayrıca onayı gerekir. Fikir yeni değildir:

- **Calhoun'un eşzamanlı çoğunluğu (concurrent majority).** John C. Calhoun (*A Disquisition on Government*, 1851), sayısal çoğunluğun yanında, kararın ağır etkilediği her çıkar grubunun kendi çoğunluğunun da onayını şart koşar. Meşveret bu fikri yalnızca ölçülebilir bir koşulda uygular: payın orantısız azalması. Calhoun'un genel veto hakkına, yani her grubun her karara itiraz edebilmesine dönüşmez. (Calhoun'un fikri tarihte köleliği koruma aracı olarak savunuldu; genel veto azınlık korumasını bir azınlık ayrıcalığına çevirebilir. Veto kapsamının dar ve ölçülebilir tutulmasının bir nedeni de budur.)
- **ABD'nin iki meclisli yapısı.** Bir yasa hem nüfusa göre seçilen Temsilciler Meclisi'nden hem de her eyaletin eşit temsil edildiği Senato'dan geçmelidir. Nüfus çoğunluğu tek başına yetmez; birimlerin ayrı sesi vardır.
- **AB Konseyi'nde çifte çoğunluk (nitelikli çoğunluk).** Karar için üye devletlerin %55'i ve AB nüfusunun %65'i gerekir. Aynı oy iki farklı sayımda çoğunluk almalıdır.

Meşveret'teki biçim bunların en dar olanıdır: ikinci sayım yalnızca orantısız etkilenen kapsam(lar) için ve yalnızca o kapsamın payı söz konusu olduğunda açılır.

## 8. Havale

### 8.1 Çözümleme

- Kullanıcının alan başına en fazla bir çıkan havalesi ve en fazla bir genel havalesi vardır. Yeni havale aynı alandaki eskisinin yerine geçer.
- Kullanıcının A alanındaki etkin temsilcisi şöyle bulunur: A'dan köke doğru ilk alan havalesi; yoksa genel havale; o da yoksa kimse.
- YONETMELIK önerilerinin alanı yoktur; yalnızca genel havale uygulanır.
- Zincir, etkin temsilciler boyunca son kişiye kadar izlenir.

### 8.2 Döngü kontrolü (R4)

- Havale kaydedilirken, kaydedenin etkin temsilcisinin değiştiği her alan için zincir yeni duruma göre izlenir. Bu alanlar, X alanındaki bir havale için X'in alt ağacı; genel havale için tüm alanlar ve alansız durumdur.
- Zincir kaydedene geri dönüyorsa havale reddedilir ve döngünün oluştuğu alan gerekçede adıyla belirtilir.
- Yalnızca X'e bakan bir kontrol yetmez. Örnek: v'nin Sinema'da u'ya havalesi var, u da Kültür'de v'ye havale eklemek istiyor. Sinema, Kültür'ün alt alanı olduğu için u'nun Sinema'daki etkin temsilcisi v olur ve Sinema'da döngü oluşur.

### 8.3 Oy hakkı ve ağırlık

- Etkin temsilcisi olan kişi o alanda oy kullanamaz.
- Ağırlık anlık görüntü üzerinden hesaplanır: oy verenin ağırlığı = 1 + zinciri kendisinde biten ve o öneride oy hakkı olan havale edenlerin sayısı.
- Zincirde o öneride oy hakkı olmayan ara halkalar (başka şehirden biri, baskın işaretli bir hesap) geçirgendir; zincir onların üzerinden devam eder.
- Zincirin sonundaki kişi oy vermediyse ya da oy hakkı yoksa, oraya varan oylar çekimser sayılır.

### 8.4 Müşavir

Bir alanda doğrudan `musavir_esigi` sayıda havale alan kişi o alanın Müşaviri olarak görünür. Atama yoktur; etiket, eşik altına düşünce kendiliğinden kalkar. Rütbe değildir, bir görünürlük etiketidir.

### 8.5 Hâtif

Hâtif sembolik bir bilirkişidir: kural tabanlı bir servis hesabıdır, gerçek bir yapay zekâ API'si kullanmaz.

- Kendi oyu 1'dir ve havale alabilir.
- GENEL ve tüm ILGI kapsamlarının üyesidir; NITELIK kapsamlarının üyesi değildir (adresi ve yaşı yoktur).
- Giriş yapamaz. Oyunu pencere açılırken kendiliğinden verir (§6.1).
- Kapanış onay oylamasında EVET tüm metinleri onaylamak, HAYIR hiçbirini onaylamamak demektir. Tüm metinlere eşit puan eklediği için sıralamayı değiştirmez.
- Oy gerekçesi oturum sonucunda yayımlanır; pencere açıkken gösterilmez.

## 9. İlişki grafı ve baskın tespiti

**ETKILESIM sinyalleri** (ağırlıklar `etkilesim_agirliklari` maddesinden okunur):

- birbirine yanıt verme (Meydan tartışması ve Mahzen),
- havale (karşılıklı havale iki kez sayılır),
- aynı `yakin_kayit_dk` içinde açılmış hesaplar,
- aynı başlığa (konu ya da Mahzen başlığı) `ortak_baslik_dk` içinde ilk kez katılma.

**Algoritma** (seçmen anlık görüntüsü alınırken çalışır):

1. Adaylar: katılım anı anlık görüntüden en fazla `baskin_yeni_uye_suresi` önce olan seçmenler. Katılım anı Meydan'da kapsam üyeliğinin başladığı andır (`UYE.since`; GENEL'de kayıt anı). Mahzen'de hesabın açılış anıdır: başlığa katılım o başlıktaki herkes için yenidir ve ortak başlık sinyali tüm katılımcıları birbirine bağlar. Başlığa katılım anı kullanılsaydı genç bir başlıktaki herkes baskın sayılırdı.
2. Adaylar arasında, iki yönlü toplam ağırlığı en az `baskin_min_agirlik` olan kenarlardan yönsüz bir graf kurulur.
3. Bağlı bileşenler bulunur. Bir bileşen şu üç koşulu birlikte sağlıyorsa işaretlenir:
   - boyutu en az `baskin_min_kume`,
   - kenar yoğunluğu (kenar sayısı / olası kenar sayısı) en az `baskin_yogunluk_esigi`,
   - katılım anlarının yayılımı en fazla `baskin_katilim_araligi`.
4. İşaretli hesaplar o oylamanın seçmen listesinden ve paydasından çıkar. Kendilerine ve sonuç ekranında gerekçesiyle gösterilir. İçerikleri silinmez; başka oylamalarda yeniden değerlendirilirler.

## 10. Mahzen

- **Başlık kimliği:** `HMAC-SHA256(sunucu_anahtarı, user_id ‖ ":" ‖ thread_id)` değerinin ilk 8 hex karakteri. Aynı başlıkta takip edilebilir, başlıklar arasında eşleştirilemez. Yazar etiketi "Gölge"dir. Sunucu gerçek kimliği saklar.
- **Uyarı:** kullanıcı Mahzen'e ilk girdiğinde ve her başlığa ilk yazışında şu metin gösterilir: "Bu başlık katılımcılarının oylamasıyla öneriye dönüştürülürse, burada yazan herkesin takma adı açığa çıkar." Sunucu, başlıktaki ilk mesajı uyarı onayı olmadan kabul etmez.
- **Geçicilik:**
  - Yeni yanıt başlığı üste çıkarır.
  - Başlık sayısı `mahzen_kapasite`yi aşınca en alttaki başlık, mesajları ve oylamasıyla birlikte kalıcı olarak silinir.
  - `mahzen_ust_sinir` yanıta ulaşan başlık artık yükselemez.
  - Yaşayan başlıklar deftere yazılmaz.
- **İmza:** kullanıcı kendi mesajını imzalayabilir; o mesaj için takma adını gönüllü açar. Geri alınamaz. Mahzen'de bilirkişi işareti yoktur.
- **Erişim:** Başlığı okumak ve yanıt yazmak herkese açıktır. Yanıt yazan kişi katılımcı olur. Başlıkta yazmamış biri o başlıkta başka hiçbir işlem yapamaz. Başlığa dışarıdan referans verilemez: sunucu, Meydan'daki ve diğer Mahzen başlıklarındaki metinlerde Mahzen başlık bağlantısını reddeder.
- **"Öneriye dönüştür" oylaması:**
  - Açılış: katılımcılardan biri açar; bir başlıkta aynı anda yalnızca bir oylama açık olabilir.
  - Seçmenler: oylama açılmadan önce başlıkta en az bir mesaj yazmış olanlar (anlık görüntü), eksi baskın işaretliler. Her birinin 1 oyu vardır; havale yoktur.
  - Oylar gizlidir; sunucu sayar. Oy değiştirilebilir. Ara sayım gösterilmez; seçmen yalnızca kendi oyunu görür.
  - Süre yoktur, sonuçlanma zorunluluğu yoktur. EVET sayısı `mahzen_ifsa_esigi` × seçmen sayısını **aştığı an** oylama geçer; aşılmazsa açık kalır.
  - Başlık kapasiteden düşerse oylama da onunla birlikte ölür. Silinme koruması yoktur; olsaydı oylama açmak başlığı ölümsüz yapardı.
- **İfşa:** oylama geçince:
  - başlık dondurulur,
  - tüm yazarların takma adları açığa çıkar,
  - başlık kimlikleriyle birlikte deftere yazılır (bireysel oylar yazılmaz, yalnızca sayılar),
  - oylamayı açan kişi adına içerikten TASLAK bir KONU önerisi oluşturulur. Sahibi alanı ve kapsamı seçip gönderince normal öneri akışına girer.

  Dondurulmuş başlık kapasite havuzundan çıkar ve öneriden bağlantıyla Meydan görünümünde okunur.
- **Teşvik edilmez:** Meydan'da altta sade bir metin bağlantısı olarak durur. Bildirim, sayaç yoktur; akışta Mahzen içeriği görünmez.

## 11. Defter

- **Kayıt:** `{seq, prev_hash, ts, type, payload, payload_hash, hash}`.
  - `payload_hash = sha256(kanonik_json(payload))`.
  - `hash = sha256(prev_hash ‖ payload_hash ‖ ts ‖ type)`. `prev_hash` ve `payload_hash` 64 karakter hex, `ts` sabit biçimli ISO-8601 (mikrosaniye, `Z`) olduğu için birleştirme belirsiz değildir.
  - Genesis kaydının `prev_hash` değeri 64 sıfırdır.
- **Zaman:** `ts` değerini API sahte saatten verir; defter azalmayan `ts` şartı koyar.
- **Yazılanlar:** kabul edilmiş içerik (tam metin), tartışma mesajları ve sürümleri, öneriler, oy commit'leri, açılan oylar, sonuçlar, silme olayları, havale olayları, Karar ve Şerhler, açığa çıkarılmış Mahzen başlıkları. Silinen içerik defterden silinmez.
- **Depolama:** her düğümde ayrı SQLite dosyası. UPDATE ve DELETE, SQLite tetikleyicileriyle reddedilir.
- **Çoğaltma:**
  - ledger-1 sabit liderdir. API yalnızca lidere yazar.
  - Lider kaydı yazar ve takipçilere `/replicate` ile gönderir.
  - Takipçi, `prev_hash` ve `seq` kendi ucuyla uyuşuyorsa ve hash'i yeniden hesapladığında aynı değeri buluyorsa kaydı ekler.
  - Geride kalan takipçi `GET /records?from=` ile liderden yetişir.
  - Oylama algoritması (Raft vb.) ya da lider devri yoktur.
- **Doğrulama:**
  - Her düğümdeki `/verify` zinciri baştan yeniden hesaplar; ilk bozuk seq'i ve nedenini döner.
  - API'deki `/ledger/verify` üç düğümü toplar ve durumu üçe ayırır: **bütünlük bozuk** (hash tutmuyor), **geride** (kısa ama önek aynı), **tutarsız** (aynı seq'te farklı hash).
- **İstemci:** Meydan'da her içeriğin altında kısaltılmış hash (mühür) gösterilir. "Defteri doğrula" ekranı üç düğümün durumunu gösterir ve hash ile kayıt görüntüler.
- **Geliştirme aracı:** `docker compose exec ledger-2 python -m ledger.tamper --seq N` bir düğümün kaydını bozar. Yalnızca doğrulamanın bozulmayı yakaladığını göstermek içindir.

## 12. Zaman ve geliştirme CLI'ı

- **Sahte saat:** PostgreSQL'de tek satırlık ofset tutulur, `now = gerçek_utc + ofset`. Tüm zaman karşılaştırmaları bu saatle yapılır.
- **Zamanlayıcı:** API içindeki arka plan iş parçacığı 5 saniyede bir `tick(now)` çağırır. CLI ile eşzamanlı çalışmayı bir PostgreSQL advisory lock engeller.
- **`meşveret-dev`** (ASCII takma adı `mesveret-dev`), yalnızca `ENV=dev` iken çalışır:
  - `advance-time --hours N | --days N | --to ISO` — ofseti ilerletir; aradaki işleri (sessiz onay bitişi, rakip süresi bitişi, haftalık Karar Saati açılış ve kapanışı) sırayla, her birini kendi vade anında işler.
  - `run-karar-saati` — hemen bir oturum açar: anlık görüntü, kilit, baskın tespiti, Hâtif oyu, ardından tohumdaki oy planına göre tohum kullanıcılarının oyları (`--no-scripted-votes` ile kapatılır). Olgunlaşmamış öneriler oturuma alınmaz; komut bunları ve oylanacakları ilk oturumu listeler.
  - `run-karar-saati --close` — saati pencere sonuna ilerletir, oyları açar, sayar ve sonuçları uygular.
  - `tamper-regulation MADDE JSON` — bir yönetmelik değerini oylamasız, doğrudan graf deposuna yazar; öneri, R8, değişiklik geçmişi ve defter kaydı yoktur. Biçim yine doğrulanır (uygulama okuyamayacağı bir değerle çökmesin), izinli aralık bilerek atlanır. Operatörün sessiz değişikliğini taklit eder (§5.3, README senaryo 12).
  - `seed [--reset]`, `now`.
- CLI komutları `services/devtools.py` üzerinden çalışır. Docker'sız geliştirme modunda (`scripts/dev_local.sh`, bellek içi graf) aynı işlemler yalnızca o modda açılan `/_dev` uç noktalarından sunulur; CLI ayrı süreçte bellek içi grafa erişemez.
- **Tohum** (`services/seed.py`) geçmiş tarihli içeriği bir zaman çizelgesine yazar ve zaman sırasıyla oluşturur; defter kayıtlarının zaman damgaları içeriğin zamanıyla aynı olur. Karar Saati senaryolarındaki yüzdeler, Hâtif'in oyu ve havale ağırlıkları hesaba katılarak kurulmuş bir geliştirme oy planına (`dev_vote_plan`) dayanır; `test_seed.py` senaryoların sonuçlarını doğrular. Oylanacak senaryo önerileri 21–22 Eylül'de açılır ve son planlı oturumdan (Pazar 27 Eylül) sonra olgunlaşır; böylece o oturumu kaçırıp kuyrukta beklemeleri tutarlıdır. Senaryo 9'un önerisi tohum anından 10 dakika önce açılır ve olgunlaşmamıştır.

## 13. Tasarım dili

### 13.1 Meydan

- **Renkler:** kırık beyaz kâğıt zemin (#F4EFE4, hafif doku), mürekkep (#1B1A17), tek vurgu mühür bordosu (#7A1E2B).
- **Yazı:** metin ve başlıklarda Newsreader; hash ve sayılarda IBM Plex Mono.
- **Mesaj:** takma ad, zaman damgası, mühür gibi duran küçük mono defter hash'i.
- **Sansür şeridi:** tam genişlikte siyah şerit, üzerinde mono yazıyla oylama numarası. Bordo #7A1E2B siyah üstünde 2,0:1 kontrast verdiği için şeritteki yazıda aynı tonun açık hâli (#D4576B, 5,4:1) kullanılır.
- **Karar Saati:** büyük geri sayım; sonuç açıklamasında oylar sayılarak düşer.
- **Profil:** resmî kayıt belgesi düzeni.

### 13.2 Mahzen

- **Renkler:** tam siyah (#000) zemin, fosfor amberi (#FFB000, 11,5:1). Sönük amber (#7A5500, 3,1:1) yalnızca çerçeve, çubuk ve büyük yazıda kullanılır.
- **Yazı:** her yerde IBM Plex Mono, başlıklarda VT323.
- **Kimlik:** isim yok; yalnızca başlık kimlikleri ve "Gölge" etiketi.
- **Çürüme:** başlık kapasitede alt sıralara indikçe yazı soluklaşır ve bazı karakterler deterministik olarak bozulur. Kontrast 4,5:1'in altına inmez. Bozulan metnin erişilebilir etiketi özgün metni taşır. Yanında bir ömür çubuğu vardır.
- **CRT:** hafif tarama çizgileri; tek katman, kapatılabilir, tercih saklanır.
- **Giriş:** ekran kararma geçişi ve uyarı.

### 13.3 İfşa geçişi

Yaklaşık 1,5 saniyelik geçişte:

- siyah zemin kâğıda döner,
- amber yazı mürekkebe döner,
- mono font serife geçer,
- başlık kimliklerinin üzerine takma adlar yazılır.

Geçiş, ifşadan sonra başlığı ilk açan herkeste bir kez oynar.

### 13.4 Genel

Ekranlar 360 px genişlikte düzgün çalışır. Tüm animasyonlar (kararma, oyların düşmesi, mühür, ifşa geçişi) `prefers-reduced-motion` açıkken kapanır; web'de `matchMedia`, Android'de sistem ayarı `AccessibilityInfo.isReduceMotionEnabled` ile okunur. Bu durumda son hâl anında gösterilir. Büyük harf dönüşümünün Türkçe kurallarla (i → İ) yapılması için web'de sayfa dili `tr` olarak ayarlanır. Seçim ve aç/kapa durumları `aria-checked`, pasif düğmeler `aria-disabled`, form alanları etiketleriyle (`aria-label`) duyurulur; react-native-web 0.21 eski `accessibilityState` nesnesini DOM'a aktarmadığı için `aria-*` özellikleri kullanılır (React Native'de de geçerlidir). Sayılar Türkçe yazılır: ondalık virgül ("%61,5") ve sayıya göre ek ("#7'ye", "#19'a").

## 14. Belgede cevabı olmayan noktalar ve verilen kararlar

| Nokta | Karar |
|---|---|
| R2'de üst küme ya da ilgisiz kapsam | Red (kullanıcı kararı) |
| Hâtif'in HAYIR ölçütü | R1–R8 + H1–H4 (kullanıcı kararı; R7 ve H4 silmenin sıkılaştırılmasıyla, R8 yönetmeliğin tabanıyla eklendi) |
| Taban kuralının numarası | R8. İstekte R7 olarak geçiyordu, ama R7 silme gerekçesi kuralıdır; mevcut referanslar bozulmasın diye yeni kural R8 oldu |
| Değiştirilemez maddenin değiştirilme önerisi | Kuyruğa girmez, açılışta reddedilir ("teklif edilemez"); kaldırma ve değer değiştirme aynı biçimde |
| İzinli aralıklar | Parametre tanımının parçasıdır (`Article.allowed`), graf değeri değildir; çalışan kodla gelir ve yönetmelik hash'ine girer. Önceki iki taban maddesi aralıkların alt ucuna dönüştü. Oranlarda karşılaştırma katılıkla yapılır |
| Süre sıfır olabilir mi | Biçim olarak evet (`ilgi_bekleme` 0 gün); alt sınırı aralık belirler |
| Yönetmelik hash'inin zamanı | Kurulumda ve her oturum kapanışında; meşru değişiklikler yalnızca oturum kapanışında uygulanır |
| Mahzen ifşa oylamasının süresi ve eşiği | Süresiz; seçmen listesinin yarısı aşılınca anında geçer; oy değiştirilebilir (kullanıcı kararı) |
| Zincirde oy hakkı olmayan ara halka | Geçirgen; ağırlığa yalnızca oy hakkı olanlar katkı verir |
| Miras ile döngü | Alt ağaçtaki tüm alanlar kontrol edilir |
| Pencerede havale verme | Geri alma gibi reddedilir |
| İtirazda havale | Uygulanmaz; itiraz kişiseldir |
| Onay oylamasında eşitlik | Karar çıkmaz, öneri reddedilir |
| Kararlı konunun yeniden açılması | `reopens_topic_id` alanlı KONU önerisi |
| Konu açılış metninin sahibince düzenlenmesi | DUZENLEME önerisinden geçer |
| Öneri sahibinin seçmen kapsamına üyeliği | Gerekli (R5) |
| Doğrulama kanalı | Yalnızca e-posta (kayıtta telefon alanı yok) |
| Yaş sınırı | 18 (yaş grupları 18'den başlar) |
| Bekleme süresi dolan yeni maddeler | Baskın ve etkileşim eşikleri, `mahzen_ifsa_esigi` (§5) |
| Mahzen'de baskın tespitinin katılım anı | Hesabın açılış anı. Başlığa katılım o başlıktaki herkes için yenidir; ortak başlık sinyali tüm katılımcıları birbirine bağladığı için başlığa katılım anı kullanılsaydı genç bir başlıktaki herkes baskın sayılırdı |
| Hâtif'in onay oylamasındaki oyu | EVET = tüm metinleri onaylar (sıralamayı değiştirmez); HAYIR = hiçbirini |
| Haftalık oturum anında elle açılmış bir oturum açıksa | Haftalık oturum o hafta atlanır; aynı anda tek oturum açık olabilir |
| Silinmiş içeriğin mührü | Sansür şeridi içeriğin defter hash'ini taşır; kayıt defterden görüntülenebilir |
| Olgunlaşmada "dar" ve "geniş" | Seçmen kapsamına göre: NITELIK kapsamı ve yaprak alanın ILGI kapsamı dar; yaprak olmayan alanın ILGI kapsamı geniş; GENEL ve YONETMELIK genel. Yaprak olmayan alan, alt alanlarıyla birlikte bir konu ağacını kapsar; o alanın ilgi kapsamındaki bir karar bu ağacın tamamını ilgilendirebilir |
| Olgunlaşmanın başladığı an | Yavaş şeritte doğan türlerde açılış; itirazla düşenlerde düşüş anı |
| Daralma oranındaki toplam | Kaynağın şehir paylarının toplamı; ayrı bir toplam alanı tutulmaz |
| H4'te "metinde karşılık" | Alıntılanan kısımda aranır; alıntının hedef metinde aynen geçtiği R7'de denetlenir. Birden fazla kural seçilirse her biri için karşılık aranır; biri bile yoksa HAYIR (şeritte anılacak her kural gösterilmiş olmalı) |
| Alıntının eşleşmesi | Büyük/küçük harf, noktalama ve kesme işareti farkı yok sayılır; kelimeler bütün ve art arda olmalı |
| Kendi içeriği istisnası | Yalnızca mesajlar için (açılış mesajı dahil). Konu silme hiçbir zaman "kendi" sayılmaz. Kendi mesajında kural ve alıntı isteğe bağlıdır; verilirse doğrulanır |
| R7'nin oylama anında yeniden çalışması | Hedefin güncel metniyle; yazar ihlal eden kısmı düzeltirse Hâtif HAYIR der |
| İçerik kuralı eklemek ve kaldırmak | YONETMELIK önerisiyle ve `yonetmelik_esigi` ile (kullanıcı kararı). Kod öneri açılırken verilir, kaldırılan kod yeniden kullanılmaz; eklemede R6 hedefi kuralın başlığıdır. Bir kuralı değiştiren öneri kabul anında kural kaldırılmışsa uygulanmaz |
| Yapılandırılmış etkinin anlamı | Kapsam başına mutlak yeni pay; bildirilmeyen kapsamın payı aynı kalır. Toplamın korunması gerekmez (kesinti mümkündür). Boş etki "paylar değişmiyor" demektir |
| Orantısızlık hesabı | Göreli değişim (yeni − eski) / eski. Ortalama, payı olan tüm alt kapsamlar üzerinden alınır, değişmeyenler dahil (ağırlıksız). Yalnızca payı azalan kapsam orantısız sayılabilir; eşik dahildir (fark ≥ `orantisizlik_esigi`) |
| Alt kapsam oylamasının pusulası | Ayrı pusula satırı ve ayrı mühür; aynı kişi iki oylamada farklı oy verebilir. Havale yalnızca o kapsamın seçmenleri arasında çözülür; dışarıya giden havale uygulanmaz, üye kendisi oy verir. Eşik ana oylamayla aynıdır |
| Orantısızlığın ne zaman ölçüldüğü | Şerit seçimi ve Hâtif yorumu açılışta; alt oylamalar pencere açılışında güncel paylarla yeniden hesaplanır |
| Kabul edilen etkinin uygulanması | Yeni paylar kaynağa işlenir ve deftere yazılır (`PAY_DEGISTI`) |
| Daraltılmış öneride etki | Yalnızca kendi payı değiştirilebilir; daralmanın kendisi yapılandırılmış etkinin yerini tutar |
| Etki başlığının üretimi | Kaynak adının tamlayan hâli + kapsam adı + "payı". Tamlayan eki ünlü uyumuyla ve kaynaştırma ünsüzüyle eklenir; ünsüz yumuşaması yapılmaz ("kitap" → "kitapın"), kaynak adları buna göre seçilir |

## 15. Bilinçli açıklar

1. **İfşa oylaması bir çoğunluk tiranlığıdır.** Seçmen listesinin yarısından fazlası, karşı oy verenler ve oy vermeyenler dahil başlıkta yazan herkesin kimliğini açığa çıkarır. Bu, her katılımcıya ilk yazışında gösterilen uyarıyla kabul edilmiş bir tiranlıktır; uyarı rızayı belgeler, tiranlığı ortadan kaldırmaz.
2. **Başlık yağdırarak oylamayı öldürme.** İfşa oylamasına silinme koruması yoktur. Oylamanın geçmesini istemeyen biri, kapasiteyi dolduracak kadar yeni başlık açarak başlığı ve oylamayı birlikte silebilir. Koruma verilseydi oylama açmak başlığı ölümsüz yapardı. İki kötü seçenekten geçicilik korunmuştur.
3. **Sahte hesap.** Gerçek çözüm kimlik doğrulaması (e-Devlet) gerektirir; kapsam dışıdır. E-posta doğrulaması hesap çoğaltmayı yalnızca yavaşlatır. Ek olarak, belge bekleme süresini yalnızca adres *değişikliğine* koyduğu için kayıtta seçilen şehirde oy hakkı hemen doğar. Sahte hesaplar şehir kapsamına beklemeden girebilir. Baskın tespiti bunu kısmen hafifletir.
4. **Commit-reveal'da sunucuya güven.** Tuzları ve seçimleri pencere boyunca sunucu tutar. Sunucu, pencere açıkken oyları okuyabilir ya da seçmen adına oy verebilir. Defter, commit'lerin sonradan değiştirilmediğini kanıtlar; sunucunun dürüst olduğunu kanıtlamaz. Gerçek çözüm, tuzun istemcide üretilip saklanmasıdır (istemci kaybolursa oy açılamaz); bu ödevde yapılmamıştır.
5. **Etiketleme öneri sahibinde.** Seçmen kapsamını ve etkilenen kaynakları öneriyi açan seçer. Kaynak etiketini hiç koymayan biri R2'yi atlatabilir. İtiraz eşiği ve Hâtif'in H2 denetimi bunu hafifletir; engellemez.
6. **Havale yoğunlaşması ve süper-delegeler.** Zincirleme serbesttir; oylar birkaç kişide toplanabilir. Müşavir etiketi yoğunlaşmayı görünür yapar ama sınırlamaz. Havale alma üst sınırı yoktur.
7. **Hâtif'e verilen oylar fiilen operatörünün eline geçer.** Hâtif'in davranışı kural tabanlıdır ve kuralları sistemi işleten yazar. Hâtif'e havale eden, oyunu kural yazarına emanet etmiş olur. Hâtif sembolik olsa da havale alabildiği için bu etki gerçektir.
8. **Baskın tespitinin yanlış pozitifleri.** Aynı gün birlikte katılan ve birbirine yanıt veren gerçek bir arkadaş grubu, bir sınıf ya da bir dernek baskın gibi görünür ve oylamadan dışlanabilir. Tespit yalnızca yapıya bakar, niyete bakamaz. Dışlanan hesaplara gerekçe gösterilir, içerikleri silinmez ve eşikler oylamayla değiştirilebilir. Buna karşılık, sabırlı bir baskın (hesapları haftalara yayıp birbirine yanıt vermeyen) tespit edilemez.
9. **Kapsam problemi prensipte çözümsüzdür.** Bir karardan kimin etkilendiğine kimin karar verdiği sorusu sonsuz geriye gider. Meşveret bunu çözmez; ispat yükünü tersine çevirerek hafifletir. Karar veren kapsam, kaynağa sahipliğini ontolojide göstermek zorundadır. Gösteremeyen kapsam karar veremez ya da kendi payına daraltılır. Ontolojinin kendisi (kimin neye sahip olduğu) ise tohumla kurulur ve bu ödevde oylamayla değiştirilemez.
10. **Eşik kilitleme.** `yonetmelik_esigi` o anki değeriyle değiştirilir. 2/3'lük bir çoğunluk eşiği %90'a çıkarırsa, onu geri indirmek artık %90 ister. Kendini koruma kuralı kendini kilitlemeye de izin verir. İzinli aralık (§5.2) bu kilidi sınırlar: eşik en fazla 3/4'e çıkabilir, yani geri indirmek hiçbir zaman 3/4'ten fazlasını istemez.
11. **Sessizlik rıza sayılır.** Hızlı şeritte itiraz eşiğine ulaşmayan öneri kabul edilir; çoğunluğun açık onayı aranmaz. Bu, kalabalık sorununa karşı bilinçli bir ödünleşimdir. 24 saat içinde bakmayan azınlık bir değişikliği kaçırabilir.
12. **Defter lideri tek hata noktasıdır.** Lider düşerse yeni kayıt yazılamaz (API outbox'ta biriktirir). Kötü niyetli bir lider takipçilere farklı zincirler gönderebilir. `/verify` tutarsızlığı yakalar ama hangi zincirin doğru olduğunu seçecek dış bir çapa yoktur.
13. **Onay oylamasında eşik yoktur.** En çok onayı alan metin, seçmenlerin küçük bir kısmının onayıyla da Karar olabilir.
14. **Mahzen anonimliği sunucuya karşı değildir.** Sunucu gerçek kimliği saklar. ETKILESIM grafı Mahzen etkinliğinden de beslenir. Başlıklar arası eşleştirme yalnızca istemci tarafında imkânsızdır.
15. **Düşük katılımda Hâtif belirleyici olur.** Yeter sayı yoktur ve Hâtif her oturumda oy verir. Hiçbir yurttaşın oy vermediği bir oylamada Hâtif'in tek oyu sonucu belirler; denetimlerden geçen bir öneri böylece yalnızca bir kural motorunun onayıyla kabul edilebilir. Hâtif'e havale edenler arttıkça bu etki büyür (bkz. 7. madde).
16. **Silme gizlemedir.** Silinen içerik defterde herkese açık kalır. Silme oylaması içeriği sitenin görünür yüzünden kaldırır, kayıttan kaldırmaz.
17. **Pencere boyunca kimin oy verdiği bellidir.** Oyun içeriği mühürlüdür ama commit kaydı seçmenin takma adıyla deftere hemen yazılır. Pencere kapanmadan kimin oy verdiği, kimin henüz vermediği görülebilir; bu bilgi son dakika baskısına yol açabilir.
18. **Mahzen'de oy değiştirmek bir yarışa dönüşebilir.** İfşa, eşiğin aşıldığı an gerçekleşir ve geri alınamaz. Fikrini değiştirmek isteyen bir seçmenin HAYIR'a dönmesi, eşiği aşan son EVET'ten sonra gelirse etkisizdir.
19. **Olgunlaşma acil kararları geciktirir.** Genel kapsamlı bir öneri en az 7 gün bekler; olgunlaşma Pazar oturumundan hemen sonra dolarsa bu neredeyse iki haftaya çıkar. Acil durumlar için hızlandırılmış bir yol yoktur. Süreler yönetmelik maddesidir ve oylamayla kısaltılabilir, ama kısaltma önerisi de 7 gün olgunlaşır. Ayrıca itiraz bir erteleme aracına dönüşebilir: hızlı şeritteki bir öneriye eşik kadar itiraz eden azınlık, onu en az 48 saat, genel kapsamda en az 7 gün geciktirir.
20. **Hâtif'in içerik denetimi kelimeye bakar, anlama bakmaz.** Anahtar kelime kullanmadan yapılan hakaret (ima, alay, küçümseme) Hâtif'ten HAYIR alır. Bir hakaret kelimesini eleştirmek için anan mesaj ("'cahil' demek yanlış") EVET alabilir. Hâtif tek bir oydur ve gerekçesini açıkça yazar; karar seçmenlerindir.
21. **2/3 gerçek bir hakareti de koruyabilir.** Seçmenlerin üçte birinden fazlası bir içeriğin kalmasını isterse, gerçekten kural ihlali olsa bile içerik görünür kalır (senaryo 4'te %60 ile silinemeyen hakaret). Reddedilen silme `red_bekleme` süresince yeniden açılamaz. Bu bilinçli bir ödünleşimdir: yayında kalan bir hakaretin zararı, çoğunluğun azınlık görüşlerini silebilmesinin zararından küçük sayılmıştır.
22. **İçerik kuralları oylamayla genişletilebilir ya da çoğaltılabilir.** 2/3'lük bir çoğunluk mevcut bir kuralın metnini genişletebilir (IK-1'i "konu dışı iletiler"i kapsayacak biçimde) ya da doğrudan geniş bir kural ekleyebilir ("IK-4 Konu dışı"). Aynı çoğunluk, silmeleri engelleyen bir kuralı da kaldırabilir. Tohumdaki dar küme bir tavsiyedir, güvence değildir: çoğunluk sansürüne karşı koruma, kuralların dar olmasından değil, kural kümesini değiştirmenin 2/3 istemesinden gelir. Dar kural koruması yalnızca `yonetmelik_esigi` kadar güçlüdür; bkz. 10. madde (eşik kilitleme).
23. **Kendi mesajını silmek bağlamı bozar.** Yazar kendi mesajını basit çoğunlukla gizleyebilir; ona verilen yanıtlar bağlamsız kalır, ve yazar sonradan kendisini bağlayan bir sözünü de gizleyebilir. İçerik defterde kalır; sansür şeridi silmenin yazarın isteğiyle olduğunu gösterir.
24. **Salam taktiği.** Kural her öneriyi ayrı ölçer, birikimi izlemez. Her oturumda bir kapsama ortalamadan 9 yüzde puanı fazla kesinti uygulayan öneriler tek tek orantısız sayılmaz; birkaç oturumda payın büyük kısmı erir.
25. **Ortalama sulandırılabilir.** Ortalama ağırlıksızdır ve bütün alt kapsamları içerir. Hedef dışındaki kapsamlara da kesinti eklenerek fark eşiğin altına indirilebilir: bir kapsama %50, diğerlerine %45 kesinti orantısız sayılmaz. Bu, "herkese eşit kesinti orantısız değildir" ilkesinin bedelidir.
26. **Veto haklı bir yeniden dağıtımı da durdurur.** Nüfusu azalan bir şehrin payını küçültmek adil olabilir; o şehrin seçmenleri yine de hayır diyebilir ve geçersiz kılma yoktur (bilinçli tercih, §7.7). Yeter sayı olmadığı için alt oylamada hiç oy verilmezse öneri reddedilir: ilgisizlik de vetodur.
27. **Yalnızca tanımlı paylar korunur.** Koruma, ontolojide payları tanımlı bölünebilir kaynaklarla sınırlıdır. Bir kapsamı dolaylı etkileyen öneri (ör. yalnızca bir şehirde etkinliği yasaklayan) bu kurala girmez.
28. **Etkiyi öneri sahibi bildirir.** Metinle yapılandırılmış etki arasındaki tutarlılığı sistem denetlemez. "İstanbul payı Ankara'ya" yazıp boş etki bildiren öneri R2'yi geçer ve tek oylamayla oylanır. Kabul edildiğinde uygulanan şey metin değil bildirilen etkidir, yani paylar değişmez; ama seçmen metne bakarak oy vermiş olabilir. Hâtif bu uyuşmazlığı yakalamaz.
29. **Parametreler ilkeleri içten zayıflatabilir; aralıklar bunu yalnızca sınırlar.** Her sayısal parametrenin değiştirilemez bir izinli aralığı vardır (§5.2); `ilgi_bekleme` en fazla 30 gün, `orantisizlik_esigi` en fazla 30 yüzde puanı olabilir. İlkeler artık tamamen boşaltılamaz, ama aralık içinde zayıflatılabilir: `adres_bekleme` 180 gün, `orantisizlik_esigi` 30 puan olduğunda D2 ve D5 hâlâ yürürlüktedir ama eskisinden zayıftır. Aralıkların kendisi tasarımcının keyfî seçimidir; hiçbir ölçüme dayanmaz ve yanlış seçildiyse oylamayla düzeltilemez.
30. **Değiştirilemezlik bir yazılım kuralıdır; hafifletme yalnızca tespittir.** R8'i uygulayan kod ve onu işleten kişi dışarıdan bağlanmamıştır. Sunucuyu işleten, kodu ya da veriyi değiştirerek R8'i ve aralıkları atlatabilir. Hafifletme (§5.3): yönetmeliğin tam hâli her Karar Saati sonunda hash'iyle deftere yazılır ve `/verify` çalışan kodun yönetmeliğini defterdeki son kayıtla karşılaştırır. Operatörün sessiz değişikliği engellenmez ama bir sonraki oturum kapanışına kadar yapılan bir doğrulamada görünür olur. Kalan açıklar:
    - Oturum kapanışı sessiz değişikliği aklar. Kapanış kaydı yönetmeliğin o anki hâlini yazar; sessiz değişiklik de içindedir. Ondan sonra `/verify` "tutarlı" der. İz defterde kalır: ardışık iki `YONETMELIK_DURUMU` kaydı arasındaki fark, o oturumun `YONETMELIK_DEGISTI` kayıtlarıyla açıklanamaz. Ama bu karşılaştırmayı sistem yapmaz; bir okuyucunun elle yapması gerekir.
    - Hash verinin (değerler, bayraklar, aralıklar) hash'idir, davranışın değil. R8'in denetim kodunu değiştiren ya da yönetmeliği okuyan kodun bir değeri yok saymasını sağlayan operatör, aynı hash'i üreten ama farklı davranan bir sistem çalıştırabilir.
    - Lider düğümü yöneten operatör deftere yeni bir `YONETMELIK_DURUMU` kaydı ekleyebilir. Kayıt defterde görünür ve bir oturum kapanışının hemen ardından gelmediği için dikkatli bir okuyucu fark eder, ama sistem bunu kendiliğinden işaretlemez.
    - Tespit ancak biri doğrulamayı çalıştırırsa olur; sürekli bir gözetim yoktur.
    Anayasalardaki karşılığı mahkemeler ve anayasa kültürüdür; Meşveret'te yoktur.
31. **Ölü el.** Bugünkü kurucular yarının topluluğunu bağlar. D1–D7 metinlerindeki ya da izinli aralıklardaki (§5.2) bir hata ya da eksik oylamayla düzeltilemez. Tek çıkış forumu baştan kurmaktır (yeni tohum, yeni defter). Temel Yasa'nın sonsuzluk maddesinin bedeli de budur.
32. **Aralıklar parametreleri tek tek sınırlar, birleşimlerini değil.** Artık her sayısal parametrenin aralığı var; `basit_cogunluk` en fazla 2/3 olabilir. Ama aralık içindeki değerlerin birleşimi hâlâ zarar verebilir: `basit_cogunluk` 2/3 ve `itiraz_esigi` %2 birlikte, küçük bir azınlığın her hızlı şerit önerisini 2/3 gerektiren bir oylamaya çekmesine izin verir. Sayısal olmayan parametrelerin (`karar_saati` günü ve saati) ve içerik kurallarının aralığı yoktur.

## 16. Hocanın gereksinimleri → karşılayan mekanizma

| # | Gereksinim | Karşılayan mekanizma |
|---|---|---|
| 1 | Herkes konu açabilir (öneri olarak) | KONU önerisi; seçmen kapsamında oy hakkı olan her Yurttaş açabilir (R5) |
| 2 | Silme ve düzenleme teklif edilebilir | SILME (yavaş şerit; içerik kuralı + alıntı, 2/3) ve DUZENLEME (hızlı şerit) önerileri; diff görünümü |
| 3 | Konu kabulü için çoğunluk | Sessiz onay (itiraz eşiği aşılmazsa kabul); itirazda Karar Saati'nde `basit_cogunluk` |
| 4 | Ad soyad, adres, doğum tarihi, şifre, takma ad; profilde takma ad; giriş ekranı | Kayıt formu (yapılandırılmış il/ilçe, argon2), JWT girişi, profil sayfası (özel alanlar yalnızca sahibine) |
| 5 | Konular oylamaya sunulur; kabul edilirse tartışma konusu olur | Öneri akışı → kabul edilen KONU → Konu + kalıcı tartışma alanı |
| 6 | Alt konular önerilebilir (açanla sınırlı değil), oylamaya girer | ALT_KONU önerisi (herkes açabilir), R1, hızlı şerit |
| 7 | Yönetmelik; herkesin bir rolü | YonetmelikMaddesi düğümleri (veri olarak), YONETMELIK önerisi (2/3, kendini koruma), değiştirilemez maddeler ve izinli aralıklar (§5.1–5.2, R8), defterdeki yönetmelik hash'i (§5.3); roller: Yurttaş, Müşavir, Hâtif (Mahzen'de Gölge) |
| 8 | Ontoloji: konu ve alt konu açılışında kural denetimi | Neo4j ontolojisi (alan ağacı, kapsam, kaynak sahipliği), R1–R7, Hâtif'in etiket denetimi |
| 9 | Her konuda tartışma alanı; tartışmalar silinmez | Kalıcı tartışma alanı; sürüm geçmişi; silme istisnadır: yalnızca üç dar içerik kuralına dayanarak ve 2/3 ile (§7.4); silinen içerik bile defterde kalır |
| 10 | Tartışmanın bir kısmı silinmek istenirse oylama | Mesaj bazında SILME önerisi, R7 gerekçesi (kural + alıntı), `silme_esigi`; kuralı anan sansür şeridi |
| 11 | Forumda her şey oylamayla | Tüm yapısal değişiklikler (konu, alt konu, düzenleme, silme, yönetmelik, kapanış) öneri akışından geçer; kendi mesajını silmek de. Tartışmaya yazmak oylamasızdır. **Bilinçli istisna:** değiştirilemez maddeler (D1–D7) ve parametrelerin izinli aralıkları oylamanın dışındadır (§5.1–5.2) |
| 12 | Konu kabulüne yalnızca ilgili kullanıcılar katılır | Seçmen kapsamı (NITELIK / ILGI), R2 (sahiplik), R5 (üyelik + bekleme) |
| 13 | Herkes eşit; bazıları "daha eşit" | Herkesin kendi oyu 1; havale alan kişinin ağırlığı artar; Müşavir etiketi görünürlüktür, rütbe değildir |
| 14 | Oy hakkı havale edilebilir | Genel ve alan bazlı HAVALE, miras, zincir, döngü yasağı (R4), pencere kilidi |
| 15 | Bilirkişiler; API ile bağlı yapay zekâ olabilir | Hâtif: kural tabanlı sembolik bilirkişi (gerçek API bilinçli olarak kapsam dışı) |
| 16 | Çoğunluğun azınlığı ezmesi engellenmeli (uzmanlar ve bölme) | Bölme, iki yönde: (1) kapsam + R2 otomatik daralma (parça bütün adına karar veremez); (2) eşzamanlı çoğunluk (§7.7): bütün bir parçanın payını orantısız azaltırsa parça ayrıca oylar ve öneri ancak iki oylamada da çoğunlukla geçer (Calhoun, ABD iki meclisli yapı, AB çifte çoğunluk). Uzmanlar: alan bazlı havale ve Müşavirler. Ayrıca nitelikli çoğunluk (yönetmelik ve silme 2/3), gerekçeli silme (R7) ve Şerh |
| 17 | Kalabalık (ölçek) sorunu | Havale (sıvı demokrasi), sessiz onay hızlı şeridi, Karar Saati'nde toplu oylama, seçmeni kapsamla daraltma |
| 18 | Sonunda uzlaşma; farklı görüşler oylanabilir | KAPANIS: rakip karar metinleri + onay oylaması + Şerh; süre sonra yeniden açma |
| 19 | Akran öğrenmesi temelli tartışma | Kalıcı tartışma alanı, açık sürüm geçmişi, Müşavir görünürlüğü, Mahzen diskuru; olgunlaşma süresi oylamadan önce tartışmaya en az 48 saat–7 gün ayırır |
| 20 | Web sitesi ve Android uygulaması | Expo (React Native + react-native-web) tek kod tabanı |
| 21 | Dağıtık defter | Üç düğümlü, hash zincirli, sadece eklenebilir defter; `/verify` ve istemcide doğrulama ekranı |
| 22 | Kullanıcılar bir grafta | Neo4j: `User`, `HAVALE`, `ETKILESIM`, `UYE` |
| 23 | Açıklar sorgulanmalı | §15 Bilinçli açıklar |

## 17. İstemci

- Expo SDK 57, expo-router (`client/src/app/` altındaki her dosya bir ekran), TypeScript. Web ve Android aynı kod tabanıdır.
- `src/components/paper.tsx` Meydan bileşenlerini (gazete başlığı, mühür, sansür şeridi, düğme, form alanları, geri sayım), `src/components/cellar.tsx` Mahzen bileşenlerini (CRT katmanı, çürüyen metin, ömür çubuğu, uyarı) içerir.
- `src/lib/clock.tsx` istemciyi sunucunun sahte saatine eşitler; tüm geri sayımlar bu saate göre işler.
- `src/components/reveal-tally.tsx` Karar Saati sonuç açıklamasını, `src/components/reveal-transition.tsx` ifşa geçişini oynatır.
- `src/components/proposal-title.tsx` daralan önerinin talep/etki başlığını, pay çubuğunu ve olgunlaşma satırını üretir; öneri sayfası, kartlar, konu sayfası ve Karar Saati ekranları bunu kullanır.
- API adresi `EXPO_PUBLIC_API_URL` ile verilir.

## 18. Testler (§12 gereksinimi → test dosyası)

| Gereksinim | Test |
|---|---|
| Havale çözümleme ve miras | `api/tests/domain/test_delegation.py` |
| Döngü kontrolü (miras üzerinden oluşanlar dahil) | `test_delegation.py`, `tests/integration/test_decision_hour.py::test_cycle_is_rejected_via_api` |
| Oy ağırlığı hesabı, çekimser zincirler | `api/tests/domain/test_tally.py`, `test_decision_hour.py` |
| R1–R8, otomatik daralma, üst küme reddi | `api/tests/domain/test_rules.py`, `tests/integration/test_proposals.py` |
| 2/3 ve kendini koruma | `test_tally.py`, `test_decision_hour.py::test_regulation_change_needs_two_thirds`, `::test_threshold_article_protects_itself` |
| Anlık görüntü ve kilit kuralları | `test_decision_hour.py::test_electorate_is_snapshotted_when_window_opens`, `::test_delegations_are_locked_while_window_is_open` |
| Sessiz onay eşiği, red bekleme | `test_proposals.py` |
| Mahzen seçmen anlık görüntüsü | `tests/integration/test_cellar.py::test_electorate_is_snapshot_of_posters_before_vote_opened` |
| Başlık kimliğinin başlıklar arasında eşleşmemesi | `api/tests/domain/test_shade.py`, `test_cellar.py` |
| Defter bütünlüğü ve bozulmuş zincirin tespiti | `ledger/tests/test_chain.py`, `ledger/tests/test_replication.py` |
| Baskın tespiti | `api/tests/domain/test_raid.py`, `test_decision_hour.py`, `test_cellar.py` |
| Neo4j graf deposu (bellek içiyle aynı sözleşme) | `api/tests/graph_contract.py` (`test_graph_memory.py`, `tests/integration/test_graph_neo4j.py`) |
| Olgunlaşma: sınıflar, sürenin başladığı an, sonraki oturuma kayma | `api/tests/domain/test_maturation.py`, `tests/integration/test_maturation.py`, `test_seed.py::test_scenario_9_late_general_proposal_waits_for_maturity` |
| Daralmanın sunumu: pay/toplam, etki başlığı, Hâtif satırı | `test_rules.py`, `test_oracle.py`, `test_proposals.py`, `test_seed.py::test_scenario_1_istanbul` |
| İçerik kuralı ekleme ve kaldırma: kod verme, kodun yeniden kullanılmaması, R6, kaldırılan kurala dayanan silme | `test_regulation.py`, `test_proposals.py::test_content_rule_can_be_added_by_regulation_vote`, `::test_content_rule_can_be_removed_and_its_code_is_never_reused`, `test_decision_hour.py::test_pending_deletion_citing_a_removed_rule_gets_oracle_no`, `graph_contract.py` |
| Silme: içerik kuralları, R7 gerekçesi, 2/3 eşiği, kendi mesajı istisnası, H4, şeritteki kural | `test_regulation.py`, `test_rules.py`, `test_oracle.py`, `test_proposals.py`, `test_decision_hour.py::test_deletion_needs_two_thirds_but_own_message_needs_simple_majority`, `test_seed.py::test_scenario_4_unjustified_deletion_is_rejected` |
| Pay etkisi ve orantısızlık; R2'nin ters yönü; eşzamanlı çoğunluk (ayrı oylama, üyeler arası havale, sonuç satırı, payların işlenmesi) | `api/tests/domain/test_shares.py`, `test_rules.py`, `test_proposals.py`, `test_decision_hour.py::test_proposal_needs_majority_in_every_disproportionate_scope`, `::test_disproportionately_affected_scope_votes_separately_with_member_only_delegation`, `test_seed.py` (senaryo 10) |
| Değiştirilemez maddeler ve izinli aralıklar (R8, aralık karşılaştırması, graf bayrağı, ikinci savunma hattı) | `test_regulation.py::test_ranges_from_the_task`, `::test_every_numeric_parameter_has_a_range_and_defaults_lie_inside` ve aşağıdakiler |
| Yönetmeliğin defterdeki izi (başlangıç kaydı, oturum sonu kaydı, sessiz değişikliğin ve metni aynı kalan sınır genişletmesinin tespiti, `tamper-regulation` aracı ve `/_dev` karşılığı) | `tests/integration/test_regulation_integrity.py`, `ledger/tests/test_replication.py::test_last_record_of_a_type_is_served_by_every_node` |
| Değiştirilemez maddeler (ayrıntı) | `test_regulation.py`, `test_rules.py`, `graph_contract.py`, `test_proposals.py::test_lowering_regulation_threshold_to_half_is_rejected_at_opening`, `::test_removing_the_right_of_dissent_is_rejected_at_opening`, `test_seed.py::test_scenario_11_floor_of_the_regulation` |
| On bir demo senaryosunun sonuçları | `tests/integration/test_seed.py` |

## 19. Sözlük (Türkçe terim ↔ kod)

Python tanımlayıcıları İngilizcedir. Belgede adı verilen ontoloji etiketleri, ilişki adları, enum değerleri (KONU, SILME, GENEL…) ve yönetmelik madde anahtarları belgedeki gibi kalır.

| Terim | Kod |
|---|---|
| Meydan / Mahzen | `square` / `cellar` |
| Yurttaş / Müşavir / Hâtif | `citizen` / `counselor` / `oracle` |
| Gölge (başlık kimliği) | `shade_id` |
| Alan / Kapsam / Kaynak | `Area` / `Scope` / `Resource` |
| Konu / Öneri / Karar / Şerh | `Topic` / `Proposal` / `Decision` / `Dissent` |
| Havale | `Delegation` |
| İtiraz / sessiz onay | `Objection` / `silent_approval` |
| Hızlı / yavaş şerit | `fast_lane` / `slow_lane` |
| Karar Saati | `DecisionHour` |
| Yönetmelik maddesi | `RegulationArticle` |
| Sansür şeridi | `CensorStrip` |
| İfşa | `reveal` |
| Defter | `ledger` |
| Diskur | `Discourse` (Neo4j etiketi `Diskur`) |
| Baskın | `raid` |
| Pay etkisi | `share_effect` (`domain/shares.py`) |
| Orantısız etkilenen kapsam | `disproportionate` |
| Eşzamanlı çoğunluk, alt kapsam oylaması | `concurrent`, `SessionItem.vote_scope_id` |
| İçerik kuralı (IK-1…) | `ContentRule` (madde türü `icerik_kurali`) |
| Değiştirilemez madde, temel ilke (D1–D7) | `Article.unchangeable`, düğüm alanı `degistirilemez`, madde türü `temel_ilke` |
| İzinli aralık | `Article.allowed`, `Interval`, `range_violations` |
| Yönetmelik durumu kaydı | `YONETMELIK_DURUMU`, `regulation.state` / `verify_state` |
| Silme gerekçesi, alıntı | R7, `content_rules` / `excerpt` |
| Olgunlaşma (dar / geniş / genel) | `maturation` (`MaturityClass`) |
| Talep / etki başlığı | `title` / `effective_title` |
