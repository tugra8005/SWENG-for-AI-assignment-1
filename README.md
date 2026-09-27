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
| №15 | 1 · İstanbul vakası |
| №9 | 2 · Havale zinciri (Gece metro seferleri) |
| №11, №12 | 3 · Yönetmelik değişikliği |
| №10 | 4 · Silme |
| №8 | 5 · Kapanış |
| Mahzen No.91 | 6 · Mahzen |
| №13 | 7 · Baskın |
| №14 | 8 · Hâtif |

Senaryo 1 ve 6 anında oynatılır. Senaryo 2, 3, 4, 5, 7 ve 8 aynı Karar Saati oturumunda oynatılır; önce 1 ve 6'yı, ardından "Karar Saati" bölümünü izleyin.

### 1. İstanbul vakası: otomatik daralma ve red

1. **ayse** olarak giriş yapın (İstanbul'da oturuyor).
2. Ana sayfada **№15 "Etkinlik bütçesinin tamamı İstanbul'a"** önerisini açın. Bu öneriyi İstanbul kapsamındaki emre açtı; etkilenen kaynak Genel kapsama ait ve şehir bazında bölünebilir. Sayfanın üstündeki bordo bant R2'nin sonucunu gösterir: **"Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."**
3. Aynı denemeyi bölünemez bir kaynakla yapın: **Konu öner** → başlık ve metin girin → Alan: *Kent* → Seçmen kapsamı: *İstanbul* → Etkilenen kaynak: *Ortak toplantı salonu* → **Öneriyi aç**. Öneri açılmaz: *"R2 — Bu kapsam bu kaynak hakkında karar veremez: 'Ortak toplantı salonu' bölünemez ve sahibi Genel kapsam."*
4. (İsteğe bağlı) Seçmen kapsamını *Genel* yapıp aynı kaynakla deneyin: öneri açılır.

### 6. Mahzen: ifşa oylaması ve geçiş

1. **ayse** olarak Meydan'ın en altındaki sade **mahzen** bağlantısına tıklayın. Ekran kararır ve ilk giriş uyarısı çıkar; **anladım, devam** deyin.
2. Liste kapasiteye yakındır (91/100). Alt sıralardaki başlıklar soluklaşır, karakterleri bozulur; ömür çubukları kısalır. Sağ üstteki **crt** anahtarı tarama çizgilerini kapatır.
3. En üstteki **"Çoğunluk haklı olabilir mi?"** başlığını açın. Beş yazarı var; ayse'nin açtığı ifşa oylamasında iki EVET bir HAYIR oy var ve geçmek için 3 EVET gerekiyor. Ara sayım gösterilmez.
4. **[ evet ]** deyin. EVET sayısı seçmen listesinin yarısını aştığı an ifşa gerçekleşir. Yaklaşık 1,5 saniyelik geçişte siyah zemin kâğıda, amber yazı mürekkebe döner, mono yazı serife geçer ve Gölge kimliklerinin üzerine takma adlar yazılır.
5. Başlık artık Meydan görünümünde, herkesin takma adıyla ve defter mührüyle durur. **Öneri taslağı №16 →** ile taslağı açın; alanı ve seçmen kapsamını seçip **Taslağı öneri olarak gönder** deyin. Öneri normal akışa (sessiz onay) girer.

### Karar Saati: senaryo 2, 3, 4, 5, 7 ve 8

**Oturum açılmadan önce:**

- **Senaryo 8:** **№14 "Belgesel film gösterimleri"** önerisini açın. Öneren onu *Edebiyat* alanına etiketledi. Sayfanın altındaki **Bilirkişi görüşü · Hâtif** bölümü alanın *Belgesel* olması gerektiğini söyler ve "Oylamada verilecek oy: HAYIR" der.
- **Senaryo 2, döngü denemesi:** zincir şöyle kuruludur: aylin → baris (genel havale), baris → ceren (*Ulaşım* alanında). **ceren** olarak giriş yapın → **Havale** → takma ad `aylin`, alan *Ulaşım* → **Havale et**. Havale reddedilir: *"R4: Bu havale döngü oluşturur — Ulaşım alanında zincir size geri dönüyor (ceren → aylin → baris → ceren)."*

**Oturumu açın:**

```bash
docker compose exec api meşveret-dev run-karar-saati
```

Komut oturumu açar ve tohumdaki oy planını uygular. Beş baskın hesabının oyları reddedilir; çıktıda "baskın şüphesiyle işaretlendiniz" satırları görünür.

- **Senaryo 2, kilit:** **aylin** olarak **Havale** sayfasında genel havaleyi **Geri al**'a basın: *"Karar Saati penceresi açık: havale grafı bu oturum için kilitli."* **Karar Saati** sayfasında aylin'in pusulasında "Oyunuz havale zinciriyle ceren adlı yurttaşa gidiyor" yazar.
- **Senaryo 2, ağırlık:** **ceren** olarak **Karar Saati** → oy pusulası. №9 "Gece metro seferleri" için **Oy ağırlığınız: 3** yazar. **Evet** deyin; oy mühürlenir ve ekranda commit görünür. Diğer önerilere oy vermeyin; yüzdeler oy planına göre ayarlandı.

**Oturumu kapatın:**

```bash
docker compose exec api meşveret-dev run-karar-saati --close
```

**Karar Saati → Geçmiş oturumlar → #1** sayfasında oylar tek tek düşer. Beklenen sonuçlar:

| Öneri | Sonuç |
|---|---|
| №9 Gece metro seferleri | 8 EVET, 5 HAYIR → **KABUL**. ceren'in oyu olmasaydı 5–5 eşitlikti ve basit çoğunluk sağlanmazdı; ceren'in fişinde "×3 · havale: aylin, baris" yazar |
| №11 red_bekleme 30 → 45 gün | 18/30 = %60 → **RET** (yönetmelik eşiği ≥ 2/3) |
| №12 sessiz_onay_suresi 24 → 36 saat | 20/30 = 2/3 → **KABUL**. Yönetmelik sayfasında maddenin geçmişi görünür |
| №10 Silme | **KABUL** (senaryo 4) |
| №8 Kapanış | 22:00 metni en çok onayı alır → **KARAR** (senaryo 5) |
| №13 Tek şehir bütçesi | 5 hesap baskın şüphesiyle dışlandı; 2 EVET, 4 HAYIR → **RET** (senaryo 7) |
| №14 Belgesel film gösterimleri | Hâtif ×3 HAYIR (iki yurttaş Kültür alanında Hâtif'e havale etti); 4 EVET, 6 HAYIR → **RET** (senaryo 8) |

### 4. Silme

1. Ana sayfa → **Bisiklet yolları** konusu. kaba_kul'un hakaret içeren mesajının yerinde tam genişlikte siyah bir şerit durur: **"#10 NUMARALI OYLAMAYLA SİLİNDİ"**.
2. Şeritteki **defterde: ⌗ …** bağlantısına tıklayın. **Defter** sayfası o kaydı açar; mesajın tam metni defterde durur. Silme gizlemedir, kayıttan kaldırmaz.
3. **Defter → Doğrula**: üç düğüm "tutarlı" görünür. Bozma aracını çalıştırıp (yukarıda) yeniden doğrulayın: ledger-2 "BÜTÜNLÜK BOZUK" ve bozulan kaydın numarası.

### 5. Kapanış ve Şerh

1. **Parkların kapanış saati** konusunda en üstteki çift çerçeveli **Karar** bölümünde kazanan metin görünür: *"Parklar her gün 22:00'de kapansın."* Konu artık salt okunurdur.
2. **ilker** olarak giriş yapın. Kaybeden metin "yazın 24:00, kışın 22:00" onundu. **Şerh ekle** → metni yazın → **Şerhi mühürle**. Şerh karara eklenir, düzenlenemez ve silinemez, deftere yazılır.
3. Kazanan metnin sahibi **burak** olarak denerseniz şerh reddedilir.

### 7. Baskın

№13 sonucunun altında "Baskın şüphesiyle işaretlenip dışlanan 5 hesap" bölümü bu hesapları listeler: mavi_kus, sari_kedi, yesil_at, mor_balik, turuncu_ari. Hesaplar seed anından yaklaşık 5 saat önce, 32 dakika içinde açıldı ve Parklar konusunda birbirlerine yanıt verdi. İçerikleri silinmedi; yalnızca bu oylamadan dışlandılar. Dışlanmasalardı öneri 7 EVET'e 4 HAYIR'la geçerdi.

### Zamanı ilerletmek

```bash
docker compose exec api meşveret-dev advance-time --hours 25
```

№15 gibi sessiz onaydaki öneriler, itiraz eşiğine ulaşmadıysa süre dolunca kabul edilir ve konuya dönüşür. İtiraz etmek için öneri sayfasındaki **İtiraz et** düğmesi kullanılır; eşik max(3, aktif üyelerin %5'i) kadar itirazdır.

## Testler

```bash
scripts/test.sh
```

- `api` birim testleri: saf alan mantığı, bellek içi graf, defter karşılaştırması.
- `ledger` testleri: zincir bütünlüğü, bozulmuş zincirin tespiti, üç düğümlü çoğaltma.
- Entegrasyon testleri: `docker-compose.test.yml` ile geçici PostgreSQL ve Neo4j (tmpfs, 55432 ve 57687 portları) başlatılır. API servisleri, sekiz senaryonun tohum provası ve Neo4j graf deposunun sözleşme testleri çalışır.

Docker yoksa yalnızca Docker gerektirmeyen testler çalışır:

```bash
scripts/test.sh --unit
```

## Docker'sız geliştirme modu (isteğe bağlı)

Neo4j yerine bellek içi graf kullanır; PostgreSQL erişilebilir olmalıdır. Açılışta tohumu baştan kurar. CLI ayrı süreçte bellek içi grafa erişemediği için zaman ve Karar Saati araçları bu modda `POST /_dev/advance-time` ve `POST /_dev/run-karar-saati` uç noktalarından sunulur. Asıl kurulum docker compose'dur.

```bash
DATABASE_URL=postgresql+psycopg://kullanici:sifre@127.0.0.1:5432/mesveret_dev scripts/dev_local.sh
```
