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
| `meşveret-dev advance-time --hours 25` | Sahte saati ilerletir; aradaki işleri (sessiz onay bitişi, rakip metin süresi, haftalık Karar Saati) kendi vade anlarında sırayla işler. `--days`, `--minutes`, `--to 2026-10-04T20:00:00+03:00` da kullanılabilir |
| `meşveret-dev run-karar-saati` | Hemen bir Karar Saati oturumu açar (anlık görüntü, havale kilidi, baskın tespiti, Hâtif'in oyu) ve tohumdaki oy planına göre tohum kullanıcılarının oylarını verir. `--no-scripted-votes` ile yalnızca oturumu açar |
| `meşveret-dev run-karar-saati --close` | Saati pencere sonuna ilerletir, oyları açar, sayar ve sonuçları uygular |
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

## Demo senaryoları

Önce `meşveret-dev seed --reset` çalıştırın. Aşağıdaki numaralar tohumun ürettiği numaralardır; seed çıktısında da yazar.

| Öneri | Senaryo |
|---|---|
| №19 | 1 · İstanbul vakası |
| №9 | 2 · Havale zinciri (Gece metro seferleri) |
| №13, №14 | 3 · Yönetmelik değişikliği |
| №10, №11, №12 | 4 · Silme |
| №8 | 5 · Kapanış |
| Mahzen No.91 | 6 · Mahzen |
| №15 | 7 · Baskın |
| №16 | 8 · Hâtif |
| №20 | 9 · Olgunlaşma |
| №17, №18 | 10 · Eşzamanlı çoğunluk |
| — | 11 · Yönetmeliğin tabanı (açılışta reddedilen öneriler, izinli aralıklar, yönetmelik hash'i) |
| — | 12 · Operatörün sessiz değişikliği |

Senaryo 1, 6, 11 ve 12 anında oynatılır. Senaryo 2, 3, 4, 5, 7, 8 ve 10 aynı Karar Saati oturumunda oynatılır; senaryo 9 aynı oturumun açılışında görünür. Önce 1 ve 6'yı, ardından "Karar Saati" bölümünü izleyin.

### 1. İstanbul vakası: otomatik daralma ve red

1. **ayse** olarak giriş yapın (İstanbul'da oturuyor).
2. Ana sayfada **№19 "Etkinlik bütçesinin tamamı İstanbul'a"** önerisini açın. Bu öneriyi İstanbul kapsamındaki emre açtı; etkilenen kaynak Genel kapsama ait ve şehir bazında bölünebilir. Başlık iki satırdır: üstte küçük ve üstü çizili *"Talep: Etkinlik bütçesinin tamamı İstanbul'a"*, altta büyük **"Etki: Etkinlik bütçesinin İstanbul payı"**. Ana sayfadaki kart da aynı düzendedir.
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
5. Başlık artık Meydan görünümünde, herkesin takma adıyla ve defter mührüyle durur. **Öneri taslağı №21 →** ile taslağı açın (senaryo 1'in isteğe bağlı 4. adımını yaptıysanız numara №22 olur); alanı ve seçmen kapsamını seçip **Taslağı öneri olarak gönder** deyin. Öneri normal akışa (sessiz onay) girer.

### 11. Yönetmeliğin tabanı: değiştirilemez maddeler ve izinli aralıklar

1. **Yönetmelik** sayfasının başında çift çerçeveli **Değiştirilemez Maddeler** bölümü durur: D1–D7 ilkeleri, her biri kilit işaretiyle, altında **İzinli aralıklar** paragrafı. Her sayısal parametrenin değerinin altında kilitli bir **izinli: …** satırı görünür: `yonetmelik_esigi` için "≥ 2/3 – ≥ 3/4", `sessiz_onay_suresi` için "12 saat – 72 saat", `mahzen_kapasite` için "30 – 300 başlık". Aralıklar tasarımcının seçimidir; gerekçeleri DESIGN.md §5.2'dedir.
2. **kerem** olarak giriş yapın. Yönetmelik sayfasında `yonetmelik_esigi` → **Değişiklik öner** → yeni oran `1/2` → **Öneriyi aç**. Öneri açılmaz: *"R8 — yonetmelik_esigi değiştirilemez izinli aralığın dışında: ≥ 2/3 – ≥ 3/4. İzinli aralıklar oylamayla genişletilemez (D7)."* `4/5` de aynı gerekçeyle reddedilir (3/4'ün üstü fiilen kilitler); `3/4` denerseniz öneri açılır.
3. Şerh hakkını kaldırmayı deneyin: `/oneri/yeni?type=YONETMELIK&action=kaldir&article=D3` adresini açın. Form maddenin değiştirilemez olduğunu kilitle gösterir; **Öneriyi aç** deyin: *"R8 — Bu madde değiştirilemez: D3 (Kaybeden taraf Şerh ekleyebilir; Şerh silinemez.) …"* Öneri kuyruğa girmez; değişiklik teklif bile edilemez.
4. **Defter → Doğrula**: düğümlerin altındaki **Yönetmelik bütünlüğü** kutusu TUTARLI der. Çalışan kodun yönetmeliğinin hash'i, defterdeki son `YONETMELIK_DURUMU` kaydıyla (kurulumda yazılan başlangıç kaydı) aynıdır. Karar Saati kapandıktan sonra aynı kutu o oturumun sonunda yazılan kaydı gösterir. Oylamasız bir değişiklikte (veritabanına ya da grafa elle yazılan bir değer, kodda genişletilen bir aralık) kutu FARKLI der ve değişen maddeleri listeler; bunu `api/tests/integration/test_regulation_integrity.py` gösterir. Değişiklik engellenmez, yalnızca görünür olur.

### 12. Operatörün sessiz değişikliği

Değiştirilemezlik bir yazılım kuralıdır; sunucuyu işleten onu atlatabilir. Meşveret bunu engellemez, tespit edilebilir kılar (DESIGN.md §5.3).

1. **Defter → Doğrula**: **Yönetmelik bütünlüğü** kutusu TUTARLI der.
2. Operatör olarak sessiz onay süresini oylamasız, izinli aralığın (12 – 72 saat) dışına çekin:

   ```bash
   docker compose exec api meşveret-dev tamper-regulation sessiz_onay_suresi '{"saat": 2}'
   ```

   Komut eski ve yeni değeri yazar, değerin izinli aralığın dışında olduğunu ve R8'in atlandığını bildirir, son satırda doğrulamanın sonucunu verir: **Yönetmelik bütünlüğü: FARKLI**. Öneri açılmaz, deftere kayıt düşmez.
3. **Yönetmelik** sayfasında `sessiz_onay_suresi` artık **2 saat** gösterir ve altında hâlâ "izinli: 12 saat – 72 saat" yazar. Oylamayla değişen maddelerin altında tarih ve öneri numarasıyla bir geçmiş satırı görünür; burada yoktur.
4. **Defter → Doğrula**: **Yönetmelik bütünlüğü** kutusu bordo **FARKLI** der; çalışan kodun hash'i defterdeki son kaydın hash'inden farklıdır ve altta **farklı maddeler: sessiz_onay_suresi** yazar. Üç defter düğümü ise tutarlıdır: defterin kendisine dokunulmamıştır.
5. Değeri geri alın; kutu yeniden TUTARLI der, çünkü yönetmelik defterdeki son kayıtla yine aynıdır:

   ```bash
   docker compose exec api meşveret-dev tamper-regulation sessiz_onay_suresi '{"saat": 24}'
   ```

**Sınır:** tespit yalnızca bir sonraki Karar Saati kapanışına kadar sürer. Oturum sonunda yazılan kayıt yönetmeliğin o anki hâlini, sessiz değişiklik dahil, olduğu gibi kaydeder; ondan sonra kutu yeniden TUTARLI der (DESIGN.md §15, 30. madde). Bu yüzden 5. adımı atlamayın: 2 saatlik sessiz onay, sonra oynatılan senaryoları da değiştirir.

Docker'sız geliştirme modunda aynı işlem `POST /_dev/tamper-regulation` ile yapılır: gövde `{"key": "sessiz_onay_suresi", "value": {"saat": 2}}`.

### Karar Saati: senaryo 2, 3, 4, 5, 7, 8, 9 ve 10

**Oturum açılmadan önce:**

- **Senaryo 4, gerekçesiz silme:** **emre** olarak **Bisiklet yolları** konusunda hale'nin *"Eleştiri olur, hakaret olmaz."* mesajında **Silme öner**'e basın. Kural seçmeden gerekçeye "Bu mesajı beğenmedim." yazıp **Öneriyi aç** deyin. Öneri açılmaz: *"R7 — Silme önerisi en az bir içerik kuralına dayanmalı (IK-1 Spam ve reklam; IK-2 Hakaret ve tehdit; IK-3 …)"* ve alıntı uyarısı. Kurallar **Yönetmelik → İçerik kuralları** bölümündedir.
- **Senaryo 4, gerekçeli silmeler:** **№10**'da hale, kaba_kul'un hakaret içeren mesajını IK-2'ye dayanarak silmeyi öneriyor; alıntı «Bu konuyu açanların hepsi cahil». **Silme gerekçesi** bölümünde kural, alıntı ve eşik (`silme_esigi ≥ 2/3`) görünür; Hâtif yorumu: *"İçerik kuralı IK-2 (Hakaret ve tehdit): belirtilen kısımda karşılığı var ('cahil')."* **№11** kaba_kul'un reklam mesajı için IK-1'e dayanır. **№12**'de ceren, yanlışlıkla telefon numarasını paylaştığı kendi mesajını silmek istiyor: gerekçe yok, eşik `basit_cogunluk`.

- **Senaryo 8:** **№16 "Belgesel film gösterimleri"** önerisini açın. Öneren onu *Edebiyat* alanına etiketledi. Sayfanın altındaki **Bilirkişi görüşü · Hâtif** bölümü alanın *Belgesel* olması gerektiğini söyler ve "Oylamada verilecek oy: HAYIR" der.
- **Senaryo 9:** **№20 "Yönetmelik: musavir_esigi"** önerisini açın. kerem onu tohum anından 10 dakika önce açtı (müşavir eşiği 5 → 3). Genel kapsamlı ve yönetmelik önerileri Karar Saati'nden önce en az 7 gün yayında kalır. Sayfada ve ana sayfadaki kartta **"Olgunlaşıyor — 11 Ekim Pazar 20:00 oturumunda oylanacak"** yazar. Süre 6 Ekim'de dolar; o haftanın Pazar oturumu (4 Ekim) daha önce olduğu için öneri 11 Ekim'e kayar. Karar Saati sayfasının **Kuyruk** bölümü de aynı satırı gösterir.
- **Senaryo 2, döngü denemesi:** zincir şöyle kuruludur: aylin → baris (genel havale), baris → ceren (*Ulaşım* alanında). **ceren** olarak giriş yapın → **Havale** → takma ad `aylin`, alan *Ulaşım* → **Havale et**. Havale reddedilir: *"R4: Bu havale döngü oluşturur — Ulaşım alanında zincir size geri dönüyor (ceren → aylin → baris → ceren)."*

- **Senaryo 10, pay etkisi:** **№17 "İstanbul payının yarısı Ankara'ya"** önerisini açın. **Pay etkisi** tablosu İstanbul 4.000 → 2.000 (%-50, *orantısız*), Ankara 6.000 → 8.000 (%33,3), İzmir ve Bursa %0 gösterir; ortalama %-4,2. Hâtif'in yorumu: *"Orantısız etkilenen kapsam: İstanbul … fark 45,8 yüzde puanı (eşik 10). Karar Saati'nde İstanbul seçmenleri ayrıca oylar."* Orantısız etkisi olduğu için öneri sessiz onaya girmedi, doğrudan kuyruğa geçti. **№18 "Tüm şehirlerin payında %10 kesinti"** her şehirde %-10 gösterir: *"orantısız etkilenen kapsam yok; tek oylama"*.
- **Senaryo 10, pay etkisi zorunlu:** (isteğe bağlı) **Konu öner** → Seçmen kapsamı *Genel*, etkilenen kaynak *Etkinlik bütçesi*. Formda kapsam başına yeni pay tablosu çıkar; bir şehrin payını düşürdükçe satır *"orantısız → ayrı oylama"* olarak işaretlenir. Aynı öneriyi API'den pay etkisi olmadan açmaya çalışmak R2 ile reddedilir: *"… öneri etkisini kapsam başına yeni paylarla bildirmeli; metin tek başına yetmez."*

**Oturumu açın:**

```bash
docker compose exec api meşveret-dev run-karar-saati
```

Komut oturumu açar ve tohumdaki oy planını uygular. Beş baskın hesabının oyları reddedilir; çıktıda "baskın şüphesiyle işaretlendiniz" satırları görünür. №20 oturuma alınmaz; çıktının sonunda `~ #20 Yönetmelik: musavir_esigi — olgunlaşıyor (genel, 168 saat); 2026-10-11 20:00:00 (Pazar) İstanbul oturumunda oylanacak` satırı görünür ve oy pusulasında yer almaz.

- **Senaryo 2, kilit:** **aylin** olarak **Havale** sayfasında genel havaleyi **Geri al**'a basın: *"Karar Saati penceresi açık: havale grafı bu oturum için kilitli."* **Karar Saati** sayfasında aylin'in pusulasında "Oyunuz havale zinciriyle ceren adlı yurttaşa gidiyor" yazar.
- **Senaryo 10, ayrı oylama:** İstanbul'da oturan **ayse** olarak **Karar Saati** pusulasında №17 iki kez görünür: Genel oylaması ve altında *"İstanbul oylaması · orantısız etkilenen kapsam"*. İstanbul oylamasında havale yalnızca İstanbul seçmenleri arasında çözülür. Beklenen sonuç için ayse'nin №17'de oy vermemesi gerekir (verirse İstanbul yüzdesi değişir).
- **Senaryo 2, ağırlık:** **ceren** olarak **Karar Saati** → oy pusulası. №9 "Gece metro seferleri" için **Oy ağırlığınız: 3** yazar. **Evet** deyin; oy mühürlenir ve ekranda commit görünür. Diğer önerilere oy vermeyin; yüzdeler oy planına göre ayarlandı.

**Oturumu kapatın:**

```bash
docker compose exec api meşveret-dev run-karar-saati --close
```

**Karar Saati → Geçmiş oturumlar → #1** sayfasında oylar tek tek düşer. Beklenen sonuçlar:

| Öneri | Sonuç |
|---|---|
| №9 Gece metro seferleri | 8 EVET, 5 HAYIR → **KABUL**. ceren'in oyu olmasaydı 5–5 eşitlikti ve basit çoğunluk sağlanmazdı; ceren'in fişinde "×3 · havale: aylin, baris" yazar |
| №13 red_bekleme 30 → 45 gün | 18/30 = %60 → **RET** (yönetmelik eşiği ≥ 2/3) |
| №14 sessiz_onay_suresi 24 → 36 saat | 20/30 = 2/3 → **KABUL**. Yönetmelik sayfasında maddenin geçmişi görünür |
| №10 Silme: hakaret (IK-2) | 18/30 = %60 → **RET**: başkasının içeriğini silmek 2/3 ister; mesaj görünür kalır (senaryo 4) |
| №11 Silme: reklam (IK-1) | 20/30 = 2/3 → **KABUL** (senaryo 4) |
| №12 Silme: ceren'in kendi mesajı | 7/12 = %58 → **KABUL**: kendi mesajı basit çoğunlukla; 2/3 gerekseydi geçemezdi (senaryo 4) |
| №8 Kapanış | 22:00 metni en çok onayı alır → **KARAR** (senaryo 5) |
| №15 Parklar sabaha kadar açık kalsın | 5 hesap baskın şüphesiyle dışlandı; 2 EVET, 4 HAYIR → **RET** (senaryo 7) |
| №17 İstanbul payının yarısı Ankara'ya | İki sayım: **Genel: %64 EVET ✓ · İstanbul: %22 EVET ✗ → Reddedildi** (senaryo 10) |
| №18 Tüm şehirlerin payında %10 kesinti | Orantısız değil, tek oylama: 13/21 → **KABUL**; bütçe payları 3.600 / 5.400 / 4.500 / 4.500 olur (senaryo 10) |
| №16 Belgesel film gösterimleri | Hâtif ×3 HAYIR (iki yurttaş Kültür alanında Hâtif'e havale etti); 4 EVET, 6 HAYIR → **RET** (senaryo 8) |

### 4. Silme: gerekçe, 2/3 ve kendi mesajı

Silme istisnadır ("tartışmalar silinmez"). Başkasının içeriğini silmek için en az bir içerik kuralına dayanmak, kuralı ihlal eden kısmı metinden alıntılamak ve kullanılan oyların 2/3'ünü almak gerekir. Kendi mesajı için gerekçe gerekmez, basit çoğunluk yeter. Oturum öncesi adımlar ve sonuçlar yukarıdaki Karar Saati bölümündedir.

1. Oturum kapandıktan sonra ana sayfa → **Bisiklet yolları** konusu. Hakaret içeren mesaj görünür kaldı (%60 yetmedi). Reklamın yerinde tam genişlikte siyah bir şerit durur: **"#11 · IK-1 gereğince silindi"**; ceren'in mesajının yerinde **"#12 · yazarının isteğiyle silindi"**.
2. Şeritteki **defterde: ⌗ …** bağlantısına tıklayın. **Defter** sayfası o kaydı açar; mesajın tam metni defterde durur. Silme gizlemedir, kayıttan kaldırmaz.
3. **Defter → Doğrula**: üç düğüm "tutarlı" görünür. Bozma aracını çalıştırıp (yukarıda) yeniden doğrulayın: ledger-2 "BÜTÜNLÜK BOZUK" ve bozulan kaydın numarası.

### 5. Kapanış ve Şerh

1. **Parkların kapanış saati** konusunda en üstteki çift çerçeveli **Karar** bölümünde kazanan metin görünür: *"Parklar her gün 22:00'de kapansın."* Konu artık salt okunurdur.
2. **ilker** olarak giriş yapın. Kaybeden metin "yazın 24:00, kışın 22:00" onundu. **Şerh ekle** → metni yazın → **Şerhi mühürle**. Şerh karara eklenir, düzenlenemez ve silinemez, deftere yazılır.
3. Kazanan metnin sahibi **burak** olarak girerseniz **Şerh ekle** düğmesi görünmez; şerh hakkı yalnızca kaybeden metinlerin sahiplerine ve destekçilerine aittir (sunucu da reddeder).

### 7. Baskın

№15 sonucunun altında "Baskın şüphesiyle işaretlenip dışlanan 5 hesap" bölümü bu hesapları listeler: mavi_kus, sari_kedi, yesil_at, mor_balik, turuncu_ari. Hesaplar seed anından yaklaşık 5 saat önce, 32 dakika içinde açıldı ve Parklar konusunda birbirlerine yanıt verdi. İçerikleri silinmedi; yalnızca bu oylamadan dışlandılar. Dışlanmasalardı öneri 7 EVET'e 4 HAYIR'la geçerdi.

### 10. Eşzamanlı çoğunluk

Oturum kapandıktan sonra **Karar Saati → Geçmiş oturumlar → #1** sayfasında №17'nin altında iki sayım görünür: önce Genel oylaması (damga **ÇOĞUNLUK VAR**), sonra bordo çizgiyle ayrılan İstanbul oylaması (11 seçmen; damga **ÇOĞUNLUK YOK**). En altta önerinin kaderi: **"Genel: %64 EVET ✓ · İstanbul: %22 EVET ✗ → Reddedildi"**. Veto yalnızca İstanbul'un kendi payı üzerindedir ve geçersiz kılınamaz. №18 ise tek oylamayla kabul edilir ve bütçe payları %10 azalır; bundan sonra açılan İstanbul kapsamlı bir bütçe önerisinin daralma kutusu 3.600 / 18.000 puan gösterir.

### Zamanı ilerletmek

```bash
docker compose exec api meşveret-dev advance-time --hours 25
```

Senaryo 9'un devamı: oturumu kapattıktan sonra saati 11 Ekim oturumuna ilerletin. 4 Ekim oturumu №20'yi almaz (olgunlaşmamış), 11 Ekim oturumu alır.

```bash
docker compose exec api meşveret-dev advance-time --to 2026-10-11T20:30:00+03:00
```

№19 gibi sessiz onaydaki öneriler, itiraz eşiğine ulaşmadıysa süre dolunca kabul edilir ve konuya dönüşür. İtiraz etmek için öneri sayfasındaki **İtiraz et** düğmesi kullanılır; eşik max(3, aktif üyelerin %5'i) kadar itirazdır.

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
