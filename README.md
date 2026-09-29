# Meşveret — oylamayla yönetilen forum

"Yazılım Mühendisliğine Giriş" ödevi. Herkesin konu önerebildiği; konuların ve yapısal değişikliklerin oylamayla kabul edildiği iki modlu bir forum:

- **Meydan** — açık, kimlikli, kalıcı.
- **Mahzen** — anonim, geçici, isteğe bağlı felsefe tartışma alanı.

Tasarım kararları, ontoloji, kuralların gerekçeleri ve **bilinçli açıklar** [DESIGN.md](DESIGN.md) belgesinde.

```
api/       FastAPI (Python 3.12): kimlik, öneri motoru, havale, Karar Saati, Mahzen, Hâtif, geliştirme CLI'ı
ledger/    Defter düğümü: sadece eklenebilir, hash zincirli, çoğaltılmış log
client/    Expo (React Native + react-native-web): web ve Android, tek kod tabanı
scripts/   test.sh (tüm testler), dev_local.sh (Docker'sız geliştirme modu)
```

## Kurulum

Gerekenler: Docker ve Docker Compose; istemci için Node.js 20+ ve npm.

```bash
cp .env.example .env
```

```bash
docker compose up -d --build
```

Bu komut altı servisi başlatır: `postgres`, `neo4j`, `api`, `ledger-1` (lider), `ledger-2`, `ledger-3`. API `http://localhost:8000` adresinde çalışır; üç defter düğümü `8101`–`8103` portlarında. Sağlık durumunu görmek için:

```bash
curl -s http://localhost:8000/health
```

Tohum veriyi ve demo senaryolarını kurun:

```bash
docker compose exec api meşveret-dev seed --reset
```

`meşveret-dev` komutunun ASCII takma adı `mesveret-dev`'dir; klavyede ş yoksa onu kullanın.

İstemciyi web'de başlatın:

```bash
cd client && npm install && EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web
```

Tarayıcıda `http://localhost:8081` açılır.

**Android:** aynı kod tabanı Expo Go ile çalışır. Emülatörde API adresi `http://10.0.2.2:8000`, gerçek cihazda bilgisayarın yerel ağ adresidir (ör. `http://192.168.1.20:8000`). `EXPO_PUBLIC_API_URL` bu adresle verilip `npx expo start` çalıştırılır ve QR kod Expo Go ile okutulur.

### Kayıt ve doğrulama kodu

E-posta gönderilmez; doğrulama kodu API konsoluna basılır:

```bash
docker compose logs -f api | grep "SAHTE E-POSTA"
```

Tohum hesaplarının hepsi doğrulanmıştır ve şifreleri **`mesveret-demo`**.

## Geliştirme CLI'ı

Yalnızca `ENV=dev` iken çalışır. Tüm zamanlanmış işler sahte bir saate göre işler; demo bu komutlarla yapılır.

| Komut | Ne yapar |
|---|---|
| `meşveret-dev seed --reset` | Her şeyi (PostgreSQL, Neo4j, üç defter düğümü) sıfırlar, tohum veriyi ve senaryoları kurar. Sahte saat: Salı 29 Eylül 2026, 10:00 İstanbul |
| `meşveret-dev now` | Sahte saati ve bir sonraki Karar Saati'ni gösterir |
| `meşveret-dev advance-time --hours 25` | Sahte saati ilerletir; aradaki işleri (havale dolumu ve kabul süresi, sessiz onay bitişi, rakip metin süresi, haftalık Karar Saati) kendi vade anlarında sırayla işler ve her birini bir satırla yazar. Komut sürerken API'nin arka plan zamanlayıcısı bekler; işlerin tümü bu komutun çıktısında görünür. `--days`, `--minutes`, `--to 2026-10-04T20:00:00+03:00` da kullanılabilir |
| `meşveret-dev run-karar-saati` | Hemen bir Karar Saati oturumu açar (anlık görüntü, havale kilidi, baskın tespiti, Hâtif'in oyu) ve tohumdaki oy planına göre tohum kullanıcılarının oylarını verir. `--no-scripted-votes` ile yalnızca oturumu açar |
| `meşveret-dev run-karar-saati --close` | Saati pencere sonuna ilerletir, oyları açar, sayar ve sonuçları uygular |
| `meşveret-dev demo goto N` / `demo next` / `demo prev` / `demo durum` / `demo bitir` | Sınıf gösterimi (DEMO.md): her adım yığını deterministik bir duruma getirir ve hangi kullanıcıyla hangi sayfanın açılacağını yazar. `goto` baştan kurar (~20 sn, kurtarma için), `next` yalnızca geçişi uygular (~1,5 sn). Demo boyunca saat durur; `bitir` yeniden akıtır |
| `meşveret-dev tamper-regulation MADDE 'JSON'` | Yönetmelikteki bir değeri oylamasız, doğrudan veritabanında değiştirir: öneri, R8 denetimi, değişiklik geçmişi ve defter kaydı yoktur. Operatörün sessiz değişikliğini taklit eder (senaryo 12) |

Komutlar API konteynerinde çalışır:

```bash
docker compose exec api meşveret-dev now
```

Defter bozma aracı (yalnızca geliştirme; "Defteri doğrula" ekranının bozulmayı yakaladığını göstermek için):

```bash
docker compose exec ledger-2 python -m ledger.tamper --seq 5
```

`--mode rechain` verilirse bozulan kayıttan sonraki hash'ler de yeniden hesaplanır. Düğüm kendi içinde tutarlı görünür ama liderden ayrışır; doğrulama bunu "tutarsız" olarak gösterir.

## Sınıf gösterimi

Yaklaşık iki dakikalık canlı gösterim ve yedek videosu için [DEMO.md](DEMO.md). Geliştirme ortamında istemcinin sağ alt köşesinde küçük bir menü durur: demo adımının sayfalarını o kullanıcıyla açar ve hesap değiştirir. Üretim derlemesinde menü yoktur, üretim API'sinde `/_dev` uç noktaları yoktur.

## Demo senaryoları

Önce `meşveret-dev seed --reset` çalıştırın. Aşağıdaki numaralar tohumun ürettiği numaralardır; seed çıktısında da yazar.

| Öneri | Senaryo |
|---|---|
| №20 | 1 · İstanbul vakası |
| №9 | 2 · Havale zinciri (Gece metro seferleri) |
| №13, №14 | 3 · Yönetmelik değişikliği |
| №10, №11, №12 | 4 · Silme |
| №8 | 5 · Kapanış |
| Mahzen No.91 | 6 · Mahzen |
| №15 | 7 · Baskın |
| №16 | 8 · Hâtif |
| №21 | 9 · Olgunlaşma |
| №17, №18 | 10 · Eşzamanlı çoğunluk |
| №18, №19 | 14 · Pay çakışması |
| — | 11 · Yönetmeliğin tabanı (açılışta reddedilen öneriler, izinli aralıklar, yönetmelik hash'i) |
| — | 12 · Operatörün sessiz değişikliği (Karar Saati oturumunun açılışından önce ve oturum açıkken) |
| — | 15 · Havale kabulü (bekleyen, reddedilen, iade, "havale kabul etmiyorum") |
| — | 13 · Havale süresi (zamanı 181 gün ilerletir; en son oynatın) |

Senaryo 1, 6, 11 ve 15 anında oynatılır (15'te kabul Karar Saati sonuçlarını değiştirebilir, aşağıya bakın); senaryo 12'nin A parçası Karar Saati oturumu açılmadan önce, B parçası oturum açıkken oynatılır. Senaryo 2, 3, 4, 5, 7, 8, 10 ve 14 aynı Karar Saati oturumunda oynatılır; senaryo 9 aynı oturumun açılışında görünür. Önce 1 ve 6'yı, ardından "Karar Saati" bölümünü izleyin. Senaryo 13 saati 181 gün ilerlettiği için en son oynatılır.

### 1. İstanbul vakası: otomatik daralma ve red

1. **ayse** olarak giriş yapın (İstanbul'da oturuyor).
2. Ana sayfada **№20 "Etkinlik bütçesinin tamamı İstanbul'a"** önerisini açın. Bu öneriyi İstanbul kapsamındaki emre açtı; etkilenen kaynak Genel kapsama ait ve şehir bazında bölünebilir. Başlık iki satırdır: üstte küçük ve üstü çizili *"Talep: Etkinlik bütçesinin tamamı İstanbul'a"*, altta büyük **"Etki: Etkinlik bütçesinin İstanbul payı"**. Ana sayfadaki kart da aynı düzendedir.
   - Başlığın altındaki bordo çerçeveli kutu R2'nin sonucunu gösterir: **"Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."** Altında oran (**4.000 / 20.000 puan (%20)**) ve bir çubuk durur: bütçenin tamamı gri, İstanbul payı bordo.
   - **Etkilenen kaynaklar** listesinde *"Etkinlik bütçesi — yalnızca İstanbul payı (4.000 / 20.000)"* yazar.
   - Sayfanın altındaki Hâtif görüşü: *"Talep kaynağın tamamını hedefliyordu; seçmen kapsamı yalnızca İstanbul payına karar verebilir, daraltma uygulandı."*
3. Aynı denemeyi bölünemez bir kaynakla yapın: **Konu öner** → başlık ve metin girin → Alan: *Kent* → Seçmen kapsamı: *İstanbul* → Etkilenen kaynak: *Ortak toplantı salonu* → **Öneriyi aç**. Öneri açılmaz: *"R2 — Bu kapsam bu kaynak hakkında karar veremez: 'Ortak toplantı salonu' bölünemez ve sahibi Genel kapsam."*
4. (İsteğe bağlı) Seçmen kapsamını *Genel* yapıp aynı kaynakla deneyin: öneri açılır.

### 6. Mahzen: ifşa oylaması ve geçiş

1. **ayse** olarak Meydan'ın en altındaki sade **mahzen** bağlantısına tıklayın. Ekran kararır ve ilk giriş uyarısı çıkar; **anladım, devam** deyin.
2. Liste kapasiteye yakındır (91/100). Alt sıralardaki başlıklar soluklaşır, karakterleri bozulur; ömür çubukları kısalır. Sağ üstteki **crt** anahtarı tarama çizgilerini kapatır.
3. En üstteki **"Çoğunluk haklı olabilir mi?"** başlığını açın. Beş yazarı var; ayse'nin açtığı ifşa oylamasında iki EVET bir HAYIR oy var ve geçmek için 3 EVET gerekiyor. Ara sayım gösterilmez.
4. **[ evet ]** deyin. EVET sayısı seçmen listesinin yarısını aştığı an ifşa gerçekleşir. Yaklaşık 1,5 saniyelik geçişte siyah zemin kâğıda, amber yazı mürekkebe döner, mono yazı serife geçer ve Gölge kimliklerinin üzerine takma adlar yazılır.
5. Başlık artık Meydan görünümünde, herkesin takma adıyla ve defter mührüyle durur. **Öneri taslağı №22 →** ile taslağı açın (senaryo 1'in isteğe bağlı 4. adımını yaptıysanız numara №23 olur); alanı ve seçmen kapsamını seçip **Taslağı öneri olarak gönder** deyin. Öneri normal akışa (sessiz onay) girer.

### 15. Havale kabulü

Havale alan kişi kabul edene kadar yürürlüğe girmez ve oy verende kalır (DESIGN.md §8.7). Temsilcinin oyu açık olduğu için kimse onayı olmadan temsilci yapılamaz; pencereden hemen önce verilen bir havale birinin gizli oyunu açığa çıkaramaz. Tohumdaki havaleler kabul edilmiş olarak başlar; bir havale bekliyor, biri reddedildi.

1. **aylin** olarak giriş yapın. Ana sayfanın başında bordo çerçeveli şerit durur: **"Size verilen havale · kabulünüzü bekliyor"**, altında *"elif size Kent için havale verdi. Kabul ederseniz oyu size akar ve bu alandaki oyunuz açık olur. Son kabul: 5 Ekim 2026; kabul edilmezse düşer."* ve **Kabul et** / **Reddet**. Aynı şerit profilde ve Havale sayfasında da görünür.
2. Aynı sayfada **Havale** → *Verdiğiniz havaleler*: *Genel* aylin → baris yürürlükte; altında **Ulaşım · mert · reddedildi · 27 Eylül 2026**. aylin'in Ulaşım havalesini mert reddetti; havale grafa hiç girmedi, aylin'in Ulaşım'daki oyu genel havalesiyle baris'e gider.
3. **Reddet**'e basın: şerit kaybolur, deftere `HAVALE_RED` (`neden: reddedildi`) yazılır; **elif** olarak Havale sayfasında **Kent · aylin · reddedildi** görünür. **Kabul et** derseniz havale grafa girer ve 180 günlük süresi o anda başlar; deftere `HAVALE_KABUL` yazılır. Kabul, elif'in Kent ve alt alanlarındaki oyunu aylin'in zincirine ekler: tohumdaki oy planı elif için bu alanlarda oy veremez ve sonuç tablosundaki sayılar değişebilir. Tablodaki sonuçları görmek istiyorsanız kabulü Karar Saati kapandıktan sonra deneyin ya da Reddet'i seçin.
4. **ceren** olarak **Havale** → *Size gelen havaleler*: baris'in Ulaşım havalesinin yanında **İade et** vardır. İade ederseniz oy baris'e döner, deftere `HAVALE_IADE` yazılır ve baris'in Havale sayfasında **iade edildi** görünür (bu da senaryo 2'nin sonucunu değiştirir; en son deneyin).
5. **mert** olarak **Profil** → *Yalnızca size görünür* bölümünde **Havale kabul etmiyorum**'u açın. Başka biri olarak mert'in profilinde **Bu yurttaşa havale et** düğmesi pasiftir: *"Bu yurttaş havale kabul etmiyor."* Havale sayfasından takma adla denenirse: *"mert havale kabul etmiyor."*
6. Kabul edilmeyen havale `havale_kabul_suresi` (7 gün, izinli 1 – 30 gün) sonunda düşer:

   ```bash
   docker compose exec api meşveret-dev advance-time --days 7
   ```

   Komut dolumu vade anında işler; çıktıda `• 2026-10-05T07:00:00+00:00 havale kabul süresi doldu: elif → aylin (kent)` satırı görünür (arada 4 Ekim Karar Saati'nin açılış ve kapanış satırları da vardır). Deftere `HAVALE_RED` (`neden: kabul_suresi_doldu`) yazılır; elif'in Havale sayfasında **Kent · aylin · kabul süresi doldu**. Karar Saati penceresi açıkken kabul ve iade kilitlidir; ret grafa dokunmadığı için yapılabilir.

### 11. Yönetmeliğin tabanı: değiştirilemez maddeler ve izinli aralıklar

1. **Yönetmelik** sayfasının başında çift çerçeveli **Değiştirilemez Maddeler** bölümü durur: D1–D7 ilkeleri, her biri kilit işaretiyle, altında **İzinli aralıklar** paragrafı. Her sayısal parametrenin değerinin altında kilitli bir **izinli: …** satırı görünür: `yonetmelik_esigi` için "≥ 2/3 – ≥ 3/4", `sessiz_onay_suresi` için "12 saat – 72 saat", `mahzen_kapasite` için "30 – 300 başlık". Aralıklar tasarımcının seçimidir; gerekçeleri DESIGN.md §5.2'dedir.
2. **kerem** olarak giriş yapın. Yönetmelik sayfasında `yonetmelik_esigi` → **Değişiklik öner** → yeni oran `1/2` → **Öneriyi aç**. Öneri açılmaz: *"R8 — yonetmelik_esigi değiştirilemez izinli aralığın dışında: ≥ 2/3 – ≥ 3/4. İzinli aralıklar oylamayla genişletilemez (D7)."* `4/5` de aynı gerekçeyle reddedilir (3/4'ün üstü fiilen kilitler); `3/4` denerseniz öneri açılır.
3. Şerh hakkını kaldırmayı deneyin: `/oneri/yeni?type=YONETMELIK&action=kaldir&article=D3` adresini açın. Form maddenin değiştirilemez olduğunu kilitle gösterir; **Öneriyi aç** deyin: *"R8 — Bu madde değiştirilemez: D3 (Kaybeden taraf Şerh ekleyebilir; Şerh silinemez.) …"* Öneri kuyruğa girmez; değişiklik teklif bile edilemez.
4. **Defter → Doğrula**: düğümlerin altındaki **Yönetmelik bütünlüğü** kutusu TUTARLI der. Çalışan kodun yönetmeliğinin hash'i, defterdeki son `YONETMELIK_DURUMU` kaydıyla (kurulumda yazılan başlangıç kaydı) aynıdır. Karar Saati kapandıktan sonra aynı kutu o oturumun sonunda yazılan kaydı gösterir. Oylamasız bir değişiklikte (veritabanına ya da grafa elle yazılan bir değer, kodda genişletilen bir aralık) kutu FARKLI der ve değişen maddeleri listeler; bir sonraki Karar Saati açılışında ya da kapanışında değişiklik deftere yazılır ve geri alınır (senaryo 12).

### 12. Operatörün sessiz değişikliği

Değiştirilemezlik bir yazılım kuralıdır; sunucuyu işleten onu atlatabilir. Meşveret oylamasız değişikliği engellemez; tespit eder, deftere yazar ve bir sonraki Karar Saati açılışında ya da kapanışında geri alır (DESIGN.md §5.3). Hiçbir oturum oylamasız bir değerle açılmaz ya da sayılmaz. Senaryo 12, aşağıdaki Karar Saati oturumunun çevresinde iki parça olarak oynatılır: **A** oturum açılmadan önce, **B** oturum açıkken.

**A. Açılışta tespit** (`run-karar-saati`'den önce):

1. **Defter → Doğrula**: **Yönetmelik bütünlüğü** kutusu TUTARLI der; altındaki **Geçmişte tespit edilen oylamasız değişiklikler** listesi boştur ("Henüz yok").
2. Operatör olarak yönetmelik değişikliği eşiğini oylamasız 1/2'ye, izinli aralığın (≥ 2/3 – ≥ 3/4) dışına çekin:

   ```bash
   docker compose exec api meşveret-dev tamper-regulation yonetmelik_esigi '{"oran": "1/2", "karsilastirma": ">"}'
   ```

   Komut eski ve yeni değeri yazar, değerin izinli aralığın dışında olduğunu ve R8'in atlandığını bildirir, son satırda doğrulamanın sonucunu verir: **Yönetmelik bütünlüğü: FARKLI**. Öneri açılmaz, deftere kayıt düşmez. **Yönetmelik** sayfasında `yonetmelik_esigi` artık **> 1/2** gösterir; altında hâlâ "izinli: ≥ 2/3 – ≥ 3/4" yazar ve öneri numaralı bir geçmiş satırı yoktur. Bu eşikle senaryo 3'teki %60'lık №13 geçerdi.
3. Karar Saati bölümündeki gibi oturumu açın (`run-karar-saati`). Açılış, pencere uzunluğunu, yönetmelik değerlerini, seçmenleri ve havaleleri anlık görüntüye almadan önce yönetmeliği son `YONETMELIK_DURUMU` kaydıyla karşılaştırır. Fark deftere `OYLAMASIZ_DEGISIKLIK` olarak yazılır, madde son oylanmış değerine döndürülür ve geri alma `OYLAMASIZ_DEGISIKLIK_GERI_ALINDI` olarak yazılır. Komut çıktısında `! oylamasız değişiklik açılışta tespit edildi ve geri alındı: yonetmelik_esigi` satırı görünür.
4. **Defter → Doğrula**: kutu yeniden **TUTARLI** der. Geçmiş listesinde: **yonetmelik_esigi · #1 numaralı oturumun açılışında · … · kayıtta ≥ 2/3 → bulunan > 1/2 · GERİ ALINDI**. Oturum 2/3 ile açıldı; kapanışta №13 yine reddedilir (senaryo 3).

**B. Kapanışta tespit** (oturum açıkken, `run-karar-saati --close`'dan önce):

5. Adres değişikliğinden sonraki bekleme süresini oylamasız, izinli aralığın (0 – 180 gün) dışına çekin:

   ```bash
   docker compose exec api meşveret-dev tamper-regulation adres_bekleme '{"gun": 1000}'
   ```

   **Yönetmelik** sayfasında `adres_bekleme` **1000 gün** gösterir. **Defter → Doğrula**: kutu bordo **FARKLI** der ve **farklı maddeler: adres_bekleme** yazar. Üç defter düğümü tutarlıdır: defterin kendisine dokunulmamıştır. Oturumun seçmen listesi açılışta alındığı için bu değişiklik oylamayı etkilemez.
6. Oturumu kapatın (`run-karar-saati --close`). Kapanışta, oylar sayılmadan önce aynı karşılaştırma yapılır: fark yazılır ve geri alınır, ardından oturumun sonuçları uygulanır.
7. **Defter → Doğrula**: kutu **TUTARLI** der. Geçmiş listesinde iki satır durur, en yenisi üstte: **adres_bekleme · #1 numaralı oturumun kapanışında · kayıtta 90 gün → bulunan 1000 gün · GERİ ALINDI** ve açılıştaki `yonetmelik_esigi` satırı. **defterde: ⌗ …** bağlantısı tespit kaydını açar. Liste defterden kurulur ve hiç boşalmaz. **Yönetmelik** sayfasında `adres_bekleme` yeniden **90 gün**, `yonetmelik_esigi` **≥ 2/3**'tür.

Docker'sız geliştirme modunda aynı değişiklik `POST /_dev/tamper-regulation` ile yapılır: gövde `{"key": "adres_bekleme", "value": {"gun": 1000}}`.

### Karar Saati: senaryo 2, 3, 4, 5, 7, 8, 9 ve 10

**Oturum açılmadan önce:**

- **Senaryo 4, gerekçesiz silme:** **emre** olarak **Bisiklet yolları** konusunda hale'nin *"Eleştiri olur, hakaret olmaz."* mesajının satır sonundaki **⋯** düğmesine, ardından **silme öner**'e basın (düzenleme ve silme önerileri ikincil eylemdir, "⋯" arkasında durur). Kural seçmeden gerekçeye "Bu mesajı beğenmedim." yazıp **Öneriyi aç** deyin. Öneri açılmaz: *"R7 — Silme önerisi en az bir içerik kuralına dayanmalı (IK-1 Spam ve reklam; IK-2 Hakaret ve tehdit; IK-3 …)"* ve alıntı uyarısı. Kurallar **Yönetmelik → İçerik kuralları** bölümündedir.
- **Senaryo 4, gerekçeli silmeler:** **№10**'da hale, kaba_kul'un hakaret içeren mesajını IK-2'ye dayanarak silmeyi öneriyor; alıntı «Bu konuyu açanların hepsi cahil». **Silme gerekçesi** bölümünde kural, alıntı ve eşik (`silme_esigi ≥ 2/3`) görünür; Hâtif yorumu: *"İçerik kuralı IK-2 (Hakaret ve tehdit): belirtilen kısımda karşılığı var ('cahil')."* **№11** kaba_kul'un reklam mesajı için IK-1'e dayanır. **№12**'de ceren, yanlışlıkla telefon numarasını paylaştığı kendi mesajını silmek istiyor: gerekçe yok, eşik `basit_cogunluk`. Konu sayfasında üç mesajın üstünde küçük bir işaret durur: *"№10 silme oylamasında · 4 Ekim"*; işaret öneriye bağlanır.

- **Senaryo 8:** **№16 "Belgesel film gösterimleri"** önerisini açın. Öneren onu *Edebiyat* alanına etiketledi. Sayfanın altındaki **Bilirkişi görüşü · Hâtif** bölümü alanın *Belgesel* olması gerektiğini söyler ve "Oylamada verilecek oy: HAYIR" der.
- **Senaryo 9:** **№21 "Yönetmelik: Müşavir eşiği"** önerisini açın. kerem onu tohum anından 10 dakika önce açtı (müşavir eşiği 5 → 3). Genel kapsamlı ve yönetmelik önerileri Karar Saati'nden önce en az 7 gün yayında kalır. Sayfada ve ana sayfadaki kartta **"Olgunlaşıyor — 11 Ekim Pazar 20:00 oturumunda oylanacak"** yazar. Süre 6 Ekim'de dolar; o haftanın Pazar oturumu (4 Ekim) daha önce olduğu için öneri 11 Ekim'e kayar. Karar Saati sayfasının **Kuyruk** bölümü de aynı satırı gösterir.
- **Senaryo 2, döngü denemesi:** zincir şöyle kuruludur: aylin → baris (genel havale), baris → ceren (*Ulaşım* alanında). **ceren** olarak giriş yapın → **Havale** → takma ad `aylin`, alan *Ulaşım* → **Havale et**. Havale reddedilir: *"R4: Bu havale döngü oluşturur — Ulaşım alanında zincir size geri dönüyor (ceren → aylin → baris → ceren)."*

- **Senaryo 10, pay etkisi:** **№17 "İstanbul payının yarısı Ankara'ya"** önerisini açın. **Pay etkisi** tablosu İstanbul 4.000 → 2.000 (-%50,0, *orantısız*), Ankara 6.000 → 8.000 (%33,3), İzmir ve Bursa %0,0 gösterir; ortalama -%4,2. Hâtif'in yorumu: *"Orantısız etkilenen kapsam: İstanbul … fark 45,8 yüzde puanı (eşik 10). Karar Saati'nde İstanbul seçmenleri ayrıca oylar."* Orantısız etkisi olduğu için öneri sessiz onaya girmedi, doğrudan kuyruğa geçti. **№18 "Tüm şehirlerin payında %10 kesinti"** her şehirde -%10,0 gösterir: *"orantısız etkilenen kapsam yok; tek oylama"*.
- **Senaryo 10, pay etkisi zorunlu:** (isteğe bağlı) **Konu öner** → Seçmen kapsamı *Genel*, etkilenen kaynak *Etkinlik bütçesi*. Formda kapsam başına yeni pay tablosu çıkar; bir şehrin payını düşürdükçe satır *"orantısız → ayrı oylama"* olarak işaretlenir. Aynı öneriyi API'den pay etkisi olmadan açmaya çalışmak R2 ile reddedilir: *"… öneri etkisini kapsam başına yeni paylarla bildirmeli; metin tek başına yetmez."*

**Oturumu açın:**

```bash
docker compose exec api meşveret-dev run-karar-saati
```

Senaryo 12'yi oynatacaksanız A parçasını bu komuttan önce, B parçasını oturumu kapatmadan önce oynatın. Komut oturumu açar ve tohumdaki oy planını uygular. Beş baskın hesabının oyları reddedilir; çıktıda "baskın şüphesiyle işaretlendiniz" satırları görünür. №21 oturuma alınmaz; çıktının sonunda `~ #21 Yönetmelik: Müşavir eşiği — olgunlaşıyor (genel, 168 saat); 2026-10-11 20:00:00 (Pazar) İstanbul oturumunda oylanacak` satırı görünür ve oy pusulasında yer almaz.

- **Senaryo 2, kilit:** **aylin** olarak **Havale** sayfasında genel havaleyi **Geri al**'a basın: *"Karar Saati penceresi açık: havale grafı bu oturum için kilitli."* **Karar Saati** sayfasında aylin'in pusulasında "Oyunuz havale zinciriyle ceren adlı yurttaşa gidiyor" yazar.
- **Senaryo 14, aynı kaynak:** pusulada №18 ve №19 aynı bütçeye dokunur ve kartlarının altında uyarı çıkar. №18'de *"№19 ile aynı kaynağı etkiliyor; önce bu öneri uygulanır, kabul edilirse №19 uygulanamaz."*, №19'da *"№18 ile aynı kaynağı etkiliyor; önce №18 uygulanır."* yazar. Kapanışta öneriler numara sırasıyla uygulanır.
- **Senaryo 10, ayrı oylama:** İstanbul'da oturan **ayse** olarak **Karar Saati** pusulasında №17 iki kez görünür: Genel oylaması ve altında *"İstanbul oylaması · orantısız etkilenen kapsam"*. İstanbul oylamasında havale yalnızca İstanbul seçmenleri arasında çözülür. Beklenen sonuç için ayse'nin №17'de oy vermemesi gerekir (verirse İstanbul yüzdesi değişir).
- **Senaryo 2, ağırlık ve açık oy:** **ceren** olarak **Karar Saati** → oy pusulası. №9 "Gece metro seferleri" için **Oy ağırlığınız: 3** ve altında *"Oyunuz açık olacak: 2 yurttaşın oyunu taşıyorsunuz."* yazar: başkalarının oyunu taşıyan temsilcinin oyu sonuçta adıyla görünür. Oy vermediğiniz diğer önerilerde *"Oyunuz gizli"* yazar. **EVET** ve **HAYIR** aynı görünür; **EVET**'e basın, seçenek dolar ve altında *"Seçiminiz: EVET · mühürlendi"* yazar. Diğer önerilere oy vermeyin; yüzdeler oy planına göre ayarlandı.

**Oturumu kapatın:**

```bash
docker compose exec api meşveret-dev run-karar-saati --close
```

**Karar Saati → Geçmiş oturumlar → #1** sayfasında her öneri için toplamlar, eşik çizgisi, mühür ve **Açık oylar (temsilciler)** listesi durur. Ağırlığı 1 olan seçmenlerin oyları gizlidir ve yalnızca toplamlara katılır. **Oyların açılışını izle** oyları tek tek düşürür: açık oylar takma adla, gizli oylar *"gizli · 3f9a0c21"* gibi oturuma özel takma kimlikle. Beklenen sonuçlar:

| Öneri | Sonuç |
|---|---|
| №9 Gece metro seferleri | 8 EVET, 5 HAYIR → **KABUL**. ceren'in oyu olmasaydı 5–5 eşitlikti ve basit çoğunluk sağlanmazdı. Açık oylar listesinde yalnızca temsilciler ve Hâtif durur: *"ceren EVET ×3 · havale: aylin, baris"*; diğer 9 oy gizlidir (senaryo 2) |
| №13 Yönetmelik: Red bekleme süresi, 30 → 45 gün | 18/30 = %60 → **RET** (yönetmelik eşiği ≥ 2/3) |
| №14 Yönetmelik: Sessiz onay süresi, 24 → 36 saat | 20/30 = 2/3 → **KABUL**. Yönetmelik sayfasında maddenin geçmişi görünür |
| №10 Silme: hakaret (IK-2) | 18/30 = %60 → **RET**: başkasının içeriğini silmek 2/3 ister; mesaj görünür kalır (senaryo 4) |
| №11 Silme: reklam (IK-1) | 20/30 = 2/3 → **KABUL** (senaryo 4) |
| №12 Silme: ceren'in kendi mesajı | 7/12 = %58 → **KABUL**: kendi mesajı basit çoğunlukla; 2/3 gerekseydi geçemezdi (senaryo 4) |
| №8 Kapanış | 22:00 metni en çok onayı alır → **KARAR** (senaryo 5) |
| №15 Parklar sabaha kadar açık kalsın | 5 hesap baskın şüphesiyle dışlandı; 2 EVET, 4 HAYIR → **RET** (senaryo 7) |
| №17 İstanbul payının yarısı Ankara'ya | İki sayım: **Genel'de geçti (%64) · İstanbul'da geçemedi (%22) → Reddedildi** (senaryo 10) |
| №18 Tüm şehirlerin payında %10 kesinti | Orantısız değil, tek oylama: 13/21 → **KABUL**; bütçe payları 3.600 / 5.400 / 4.500 / 4.500 olur (senaryo 10) |
| №19 Tüm şehirlerin payında %5 artış | 13/21 kabul oyu, ama mühür **UYGULANAMADI**: №18 aynı bütçenin paylarını önce değiştirdi (senaryo 14) |
| №16 Belgesel film gösterimleri | Hâtif ×3 HAYIR (iki yurttaş Kültür alanında Hâtif'e havale etti); 4 EVET, 6 HAYIR → **RET** (senaryo 8) |

### 4. Silme: gerekçe, 2/3 ve kendi mesajı

Silme istisnadır ("tartışmalar silinmez"). Başkasının içeriğini silmek için en az bir içerik kuralına dayanmak, kuralı ihlal eden kısmı metinden alıntılamak ve kullanılan oyların 2/3'ünü almak gerekir. Kendi mesajı için gerekçe gerekmez, basit çoğunluk yeter. Oturum öncesi adımlar ve sonuçlar yukarıdaki Karar Saati bölümündedir.

1. Oturum kapandıktan sonra ana sayfa → **Bisiklet yolları** konusu. Hakaret içeren mesaj görünür kaldı (%60 yetmedi). Reklamın yerinde tam genişlikte siyah bir şerit durur: **"#11 · IK-1 gereğince silindi"**; ceren'in mesajının yerinde **"#12 · yazarının isteğiyle silindi"**.
2. Şeritteki **defterde: ⌗ …** bağlantısına tıklayın. **Defter** sayfası o kaydı açar; mesajın tam metni defterde durur. Silme gizlemedir, kayıttan kaldırmaz.
3. **Defter → Doğrula**: üç düğüm "tutarlı" görünür. Bozma aracını çalıştırıp (yukarıda) yeniden doğrulayın: ledger-2 "BÜTÜNLÜK BOZUK" ve bozulan kaydın numarası.

### 5. Kapanış ve Şerh

1. **Parkların kapanış saati** konusunda en üstteki çift çerçeveli **Karar** kutusunda kazanan metin görünür: *"Parklar her gün 22:00'de kapansın."* Konu artık salt okunurdur. **Yeniden açma öner** düğmesi gridir; altında *"Karar 28.12.2026'dan sonra yeniden açılabilir."* yazar (`yeniden_acma` 90 gün).
2. Karar kutusunun altında **Şerhler** bölümü durur; henüz şerh yoktur.
3. **ilker** olarak giriş yapın. Kaybeden 3. metin ("yazın 24:00, kışın 22:00") onundu. **Şerh ekle**'ye basın; formda şerhin dayandığı metin görünür: *"Dayandığı metin: #3 «Parklar yazın 24:00'te, kışın 22:00'de kapansın.» · ilker"*. Metni yazıp **Şerhi mühürle** deyin. Şerh, yazarı ve dayandığı metinle listelenir; düzenlenemez, silinemez, deftere yazılır.
4. Kaybeden metinlere onay veren yurttaşlar da şerh düşebilir: **irem**, **kaan** ve **leyla** 1. metni (20:00) onaylamıştı. Birden fazla kaybeden metni onaylayan kişi şerhin hangisine dayandığını seçer.
5. Kazanan metnin sahibi **burak** olarak girerseniz **Şerh ekle** düğmesi görünmez; şerh hakkı yalnızca kaybeden metinlerin sahiplerine ve destekçilerine aittir (sunucu da reddeder).

### 7. Baskın

№15 sonucunun altında *"5 hesabın oyu baskın şüphesiyle sayılmadı"* ve kümenin gerekçesi yazar. Hesaplar adlarıyla listelenmez, defterdeki açılış kaydı da yalnızca sayıyı taşır: yanlış pozitifler herkese teşhir edilmez. Hesaplar seed anından yaklaşık 5 saat önce, 32 dakika içinde açıldı ve Parklar konusunda birbirlerine yanıt verdi. İçerikleri silinmedi; yalnızca bu oylamadan dışlandılar. Dışlanmasalardı öneri 7 EVET'e 4 HAYIR'la geçerdi. Dışlanan kişi bunu kendisi görür: **mavi_kus** olarak giriş yapıp oturum sayfasında **Oyumu doğrula**'ya basın; *"Bu oylamada baskın şüphesiyle dışlandınız: …"* yazar.

**Oyumu doğrula.** Oturum sayfasında ya da profilin *Oylarım* bölümünde **Oyumu doğrula** yalnızca giriş yapmış kişiye kendi oylarını gösterir. **deniz** olarak açın: her oylama için oyu, *"gizli oy · bu oturumdaki takma kimliğiniz …"*, mühür ve açılış kayıtlarının defter bağlantıları ve *"commit yeniden hesaplandı, eşleşiyor"*. **ceren** için №9 *"açık oy (takma adınızla)"* olarak görünür. Takma kimlik aynı kişi için başka oturumda farklıdır.

### 10. Eşzamanlı çoğunluk

Oturum kapandıktan sonra **Karar Saati → Geçmiş oturumlar → #1** sayfasında №17'nin altında iki sayım görünür: önce Genel oylaması (damga **ÇOĞUNLUK VAR**), sonra bordo çizgiyle ayrılan İstanbul oylaması (11 seçmen; damga **ÇOĞUNLUK YOK**). En altta önerinin kaderi: **"Genel: %64 EVET ✓ · İstanbul: %22 EVET ✗ → Reddedildi"**. Veto yalnızca İstanbul'un kendi payı üzerindedir ve geçersiz kılınamaz. №18 ise tek oylamayla kabul edilir ve bütçe payları %10 azalır; bundan sonra açılan İstanbul kapsamlı bir bütçe önerisinin daralma kutusu 3.600 / 18.000 puan gösterir.

### Zamanı ilerletmek

```bash
docker compose exec api meşveret-dev advance-time --hours 25
```

Senaryo 9'un devamı: oturumu kapattıktan sonra saati 11 Ekim oturumuna ilerletin. 4 Ekim oturumu №21'i almaz (olgunlaşmamış), 11 Ekim oturumu alır.

```bash
docker compose exec api meşveret-dev advance-time --to 2026-10-11T20:30:00+03:00
```

№20 gibi sessiz onaydaki öneriler, itiraz eşiğine ulaşmadıysa süre dolunca kabul edilir ve konuya dönüşür. İtiraz etmek için öneri sayfasındaki **İtiraz et** düğmesi kullanılır; eşik max(3, aktif üyelerin %5'i) kadar itirazdır.

### 14. Pay çakışması

Aynı bölünebilir kaynağın paylarına dokunan öneriler kapanışta numara sırasıyla uygulanır. Bir önerinin pay hedefleri, önce uygulanan bir öneri aynı kaynağın paylarını değiştirdiyse geçersiz olur (DESIGN.md §7.8).

1. Oturum kapandıktan sonra **Karar Saati → Geçmiş oturumlar → #1**: №18 (kesinti) 13/21 ile kabul edilir ve bütçe payları %10 azalır. №19 **"Tüm şehirlerin payında %5 artış"** da 13/21 kabul oyu alır ama mührü **UYGULANAMADI**'dır. Altında: *"Kabul oyu aldı ama çakışma nedeniyle uygulanamadı: №18 Etkinlik bütçesi paylarını daha önce değiştirdi. Öneri reddedilmiş sayılmaz; güncel paylarla aynı içerikle yeniden açılabilir."*
2. №19'un sayfasında durum **Çakışma nedeniyle uygulanamadı**'dır. **Pay etkisi** tablosu güncel paylarla hesaplanır (İstanbul 3.600 → 4.200). Hâtif'in görüşünde önce güncel paylara göre yorum (*"pay tablosu №18 ile değişti"*), altında küçük harfle öneri anındaki yorum durur.
3. Reddedilmediği için red_bekleme uygulanmaz: aynı başlık ve içerikle hemen yeni bir öneri açılabilir. Yeni öneri güncel paylara dayanır.

### 13. Havale süresi

Her havale kabul edildiği ya da yenilendiği andan `havale_suresi` (180 gün) sonra kendiliğinden sona erer ve oy sahibine döner. Unutulmuş havalelerden birikmiş güç böylece düzenli olarak sıfırlanır; bilinçli olarak yenilenen güven korunur (DESIGN.md §8.5). Tohumdaki havaleler tohum anından 30 gün önce verildi: kalan süre 150 gün.

1. **Yönetmelik** sayfasında `havale_suresi` **180 gün** gösterir, altında kilitli **izinli: 30 – 365 gün**; `havale_uyari_suresi` **14 gün**, **izinli: 3 – 30 gün**.
2. **aylin** olarak **Havale** sayfası: *Genel* aylin → baris, altında **bitiş 26 Şubat 2027 · 150 gün kaldı** ve **Yenile** / **Geri al**. **ceren** olarak: *Size gelen havaleler* Ulaşım: 1, **baris · Ulaşım · bitiş 26 Şubat 2027 · 150 gün kaldı**. Zincir aylin → baris → ceren'dir: Ulaşım önerilerinde ceren'in ağırlığı 3'tür.
3. Saati 140 gün ilerletin; havalelerin dolmasına 10 gün kalır:

   ```bash
   docker compose exec api meşveret-dev advance-time --days 140
   ```

   Çıktı aradaki işleri sırayla listeler: her hafta Karar Saati'nin açılış ve kapanışı, sessiz onay bitişleri ve, senaryo 15'teki bekleyen havaleye dokunmadıysanız, `havale kabul süresi doldu: elif → aylin (kent)`.

4. **aylin** olarak giriş yapın. Süresi `havale_uyari_suresi` (14 gün) içinde dolacağı için ana sayfanın başında bordo çerçeveli uyarı şeridi durur: **"Genel havaleniz (baris) 26 Şubat 2027 tarihinde doluyor, 10 gün kaldı. Dolunca oyunuz size döner."** ve **Yenile** düğmesi. Aynı şerit profilde ve Havale sayfasında da görünür; profilde verilen ve alınan havaleler kalan süreleriyle listelenir. **ceren** olarak şerit alınan havaleyi gösterir: *"Size verilen 1 havalenin süresi doluyor: baris (Ulaşım, 10 gün kaldı). Yenilemek havaleyi verenin elindedir."* Bildirim gönderilmez.
5. (İsteğe bağlı) **deniz** olarak şeritteki **Yenile**'ye basın. Felsefe havalesinin (deniz → selin) süresi baştan başlar: Havale sayfasında **bitiş 15 Ağustos 2027 · 180 gün kaldı**. Deftere `HAVALE_YENILENDI` yazılır.
6. Saati 41 gün daha ilerletin (toplam 181 gün):

   ```bash
   docker compose exec api meşveret-dev advance-time --days 41
   ```

   Çıktıda her dolum, vade anıyla birlikte bir satırdır: `• 2027-02-26T07:00:00+00:00 havale süresi doldu: aylin → baris`, `… havale süresi doldu: baris → ceren (ulasim)` ve diğerleri. Komut sürerken API'nin arka plan zamanlayıcısı bekler; dolumların tümü bu komutun çıktısında görünür, API günlüğüne bakmak gerekmez. Her dolum deftere bir kez `HAVALE_SURESI_DOLDU` olarak yazılır.
7. **aylin** ve **baris** olarak Havale sayfası: *"Yürürlükte havaleniz yok; oyunuzu kendiniz kullanıyorsunuz."* İkisi de oylarını geri aldı. **ceren**: *"Size doğrudan havale veren yok."* Ulaşım önerilerinde ağırlığı 3'ten 1'e düştü.
8. **selin**'in profilinde Müşavir damgası kalkmıştır: felsefedeki beş havaleden süresi dolanlar düştü. 5. adımı yaptıysanız deniz'in yenilediği havale kalır (*Aldığı havaleler: Felsefe: 1*); eşik 5 olduğu için etiket yine yoktur.

Pencere açıkken süresi dolan havale o oturum için geçerli kalır: oturum seçmen listesini ve ağırlıkları açılışta alır. Bunu `api/tests/integration/test_delegation_expiry.py` gösterir.

## Testler

```bash
scripts/test.sh
```

- `api` birim testleri: saf alan mantığı, bellek içi graf, defter karşılaştırması.
- `ledger` testleri: zincir bütünlüğü, bozulmuş zincirin tespiti, üç düğümlü çoğaltma.
- Entegrasyon testleri: `docker-compose.test.yml` ile geçici PostgreSQL ve Neo4j (tmpfs, 55432 ve 57687 portları) başlatılır. API servisleri, senaryoların tohum provası ve Neo4j graf deposunun sözleşme testleri çalışır.

Docker yoksa yalnızca Docker gerektirmeyen testler çalışır:

```bash
scripts/test.sh --unit
```

## Docker'sız geliştirme modu (isteğe bağlı)

Neo4j yerine bellek içi graf kullanır; PostgreSQL erişilebilir olmalıdır. Açılışta tohumu baştan kurar. CLI ayrı süreçte bellek içi grafa erişemediği için zaman, Karar Saati ve sessiz değişiklik araçları bu modda `POST /_dev/advance-time`, `POST /_dev/run-karar-saati` ve `POST /_dev/tamper-regulation` uç noktalarından sunulur. Asıl kurulum docker compose'dur.

```bash
DATABASE_URL=postgresql+psycopg://kullanici:sifre@127.0.0.1:5432/mesveret_dev scripts/dev_local.sh
```
