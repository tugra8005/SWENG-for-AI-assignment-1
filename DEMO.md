# Meşveret — sınıf gösterimi

Ölçülen süre 2 dakika 11 saniyedir: 10 adım (10. adım iki parçalı). Hedef yaklaşık 2 dakikaydı, 4 dakikaya kadar uzayabilirdi. Süre bu sınırın altında kaldığı için 1. ve 2. adım birleştirilmedi, 9. ve 10. adım kısaltılmadı. Süreler, `scripts/demo-kaydi.mjs` ile yapılan iki ölçüm çalıştırmasından gelir (aşağıda **Ölçüm**). Canlı demo çökerse yedek video oynatılır: [`docs/demo.mp4`](docs/demo.mp4). Video canlı anlatımın hızındadır; her adım konuşma notunu okuyacak kadar ekranda kalır, üstünden konuşulabilir.

## Hazırlık (derse girmeden)

Uygulama menüsünde **Meşveret** yazın (başlatıcılar bir kez `sunum/kur.sh` ile eklenir):

- **Meşveret · sunum (web)**: Docker yığınını ve Expo'yu başlatır, web paketini önceden derler, demo kurulu değilse 1. adımı kurar (~20 sn), uygulamayı sekmesiz ayrı bir Brave penceresinde açar.
- **Meşveret · sunum (Android)**: aynı hazırlık, üstüne emülatörü pencereli açar (bu makinede hazırlıkla birlikte ~25 sn), portları yönlendirir, Android paketini önceden derler ve uygulamayı Expo Go'da başlatır.
- **Meşveret · sunumu durdur**: emülatörü, Expo'yu ve sunum penceresini kapatır.

Başlatıcılar her adımı yalnızca gerekiyorsa yapar: yığın ayaktaysa, Expo çalışıyorsa, demo kuruluysa geçer. İkisini birlikte açmak sorun değil. Aynı betikler terminalden de çalışır:

```bash
sunum/web.sh
```

```bash
sunum/android.sh
```

`--sifirla` demo kuruluysa bile 1. adımı baştan kurar; `sunum/durdur.sh --demo-bitir --docker` saati yeniden akıtır ve yığını da durdurur.

**Kumanda.** Hazırlık bitince aynı terminal penceresi kumandaya döner; uzun komut yazmak gerekmez:

| Tuş | İş |
|---|---|
| Enter | sonraki adım (`demo next`, ~1,5 sn) |
| `p` | önceki adım |
| `g N` | N. adımı baştan kur (`1`–`9`, `10a`, `10b`) |
| `d` | şu anki adımı yeniden yaz |
| `s` | 1. adımdan baştan başla |
| `q` | kumandadan çık (yığın ve pencereler açık kalır) |

Her adımda kumanda adımın başlığını, sorusunu ve hangi kullanıcıyla hangi sayfanın açılacağını yazar. Tarayıcıda ya da emülatörde sağ alt köşedeki küçük menü aynı sayfaları listeler; bir satıra tıklamak o kullanıcıyla giriş yapıp sayfayı açar. Menü yalnızca geliştirme ortamında görünür: üretim derlemesinde bileşen yoktur, üretim API'sinde `/_dev` uç noktaları yoktur.

**Saat donmuştur.** Demo boyunca geri sayımlar akmaz, zamanlayıcı kendiliğinden bir şey işlemez. Zamanı yalnızca adım geçişleri ilerletir; iki çalıştırma ekranda aynı sayıları gösterir. Demodan çıkmak için `meşveret-dev demo bitir`.

**Kurtarma.** Bir adım bozulursa kumandada `g N` (ya da `meşveret-dev demo goto N`) o adımı baştan kurar (~20 sn). Başlatıcılar olmadan elle: `docker compose up -d`, `cd client && npx expo start --web`, `docker compose exec api meşveret-dev demo goto 1`, ardından her adımda `docker compose exec api meşveret-dev demo next`.

## Adımlar

<!-- süreler: scripts/demo-kaydi.mjs --md ile ölçümden güncellenir -->

### Adım 1 · Kayıt ve profil
**Süre:** 11 sn · **Soru:** kimlik: herkese görünen ne, gizli ne?

1. Menü → **1) aylin → /profil/aylin**: *Yalnızca size görünür* bölümü (ad, e-posta, adres, doğum tarihi) ve *Kapsam üyelikleri* (Ankara, 35–49 yaş).
2. Menü → **2) ceren → /profil/aylin**: aynı belge, gizli bölüm yok.

> **Konuşma:** Herkes takma adla görünür; ad, adres ve doğum tarihini yalnızca sahibi görür. Oy hakkını belirleyen kapsamlar seçilmez, türetilir: şehir adresten, yaş grubu doğum tarihinden.

### Adım 2 · Öneri ve sessiz onay
**Süre:** 13 sn · **Soru:** ölçek: her şey oylanırsa kimse oy vermez

1. Menü → **1) aylin → /oneri/20**: *Sessiz onay* bölümü, geri sayım ve **İtiraz et**.

> **Konuşma:** Her şeyi oylamaya koyarsak kimse oy vermez. Konu önerisi yirmi dört saat itiraza açık kalır; aktif üyelerin yirmide biri itiraz etmezse sessizce kabul edilir.

### Adım 3 · İstanbul vakası: R2 daraltma
**Süre:** 12 sn · **Soru:** bölme: parça bütün adına karar veremez

Geçiş: saat bir gün ilerler, №20 itirazsız kabul edilir.

1. Menü → **1) aylin → /konu/…**: öneri konu oldu; üstte *R2 · otomatik daralma* kutusu.
2. Menü → **2) aylin → /oneri/20**: başlıkta talep üstü çizili, altında etki; pay çubuğu 4.000 / 20.000.

> **Konuşma:** Bir gün geçti ve öneri itirazsız konu oldu. Ama İstanbul bütçenin tamamı hakkında karar veremez: R2 talebi daralttı, etki yalnızca İstanbul'un payı.

### Adım 4 · Eşzamanlı çoğunluk
**Süre:** 10 sn · **Soru:** çoğunluk tiranlığı: bütün, parçayı ezemez

1. Menü → **1) ayse → /oneri/17**: *Pay etkisi* tablosunda İstanbul -%50,0 orantısız; sonuç satırı.

> **Konuşma:** Genel çoğunluk İstanbul'un payını yarıya indirmek istedi. Orantısız etkilenen İstanbul ayrıca oyladı: Genel'de geçti, İstanbul'da kaldı, öneri reddedildi.

### Adım 5 · Havale ve Karar Saati
**Süre:** 16 sn · **Soru:** uzmanlar: oyunu güvendiğine ver, o da hesap versin

1. Menü → **1) aylin → /havale**: zincir aylin → baris → ceren; üstteki şeritte elif'in bekleyen havalesi.
2. Menü → **2) ceren → /karar-saati/1?izle=9**: mühürlü oylar tek tek açılır.

> **Konuşma:** Oy havale edilebilir ama ancak alan kabul edince sayılır; elif'in havalesi bekliyor. Oylar mühürlüydü, şimdi açılıyor: ceren başkalarının oyunu taşıdığı için oyu açık, diğerleri gizli, yalnızca toplamda.

### Adım 6 · Kapanış ve Şerh
**Süre:** 12 sn · **Soru:** uzlaşma: kaybeden taraf kayda geçer

1. Menü → **1) zeynep → /konu/7**: KARAR kutusu. *Şerhler* → **Şerh ekle** → kısa bir metin → **Şerhi mühürle**.

> **Konuşma:** Üç rakip karar metni onay oylamasına girdi; en çok onay alan KARAR oldu. Kaybeden susturulmaz: zeynep şerhini ekliyor, şerh silinemez ve deftere mühürlenir.

### Adım 7 · Silme
**Süre:** 12 sn · **Soru:** çoğunluk tiranlığı: silmek istisnadır

1. Menü → **1) hale → /konu/6**: sansür şeritleri; hakaret içeren mesaj duruyor.
2. Menü → **2) emre → /oneri/yeni?type=SILME…**: kural seçmeden *Gerekçe*'ye bir cümle → **Öneriyi aç** → R7.

> **Konuşma:** Silme istisnadır: bir içerik kuralına dayanmayan öneri açılmaz bile. Hakaret yüzde altmış aldı, iki bölü üç gerekiyordu, duruyor; reklam silindi, yerinde şerit kaldı.

### Adım 8 · Değiştirilemez maddeler
**Süre:** 11 sn · **Soru:** çoğunluk tiranlığı: kuralı değiştirerek kazanmak

1. Menü → **1) aylin → yonetmelik_esigi**: *Yeni oran* 1/2, **> (fazlası)** → **Öneriyi aç** → R8.
2. Menü → **2) aylin → D3 kaldır** → **Öneriyi aç** → reddedilir.

> **Konuşma:** Çoğunluk eşiği kendi lehine düşürerek kazanamaz; yarıya indiren öneri açılışta reddedilir. Şerh hakkını kaldırmak da öyle: yedi madde oylamanın dışında.

### Adım 9 · Mahzen
**Süre:** 13 sn · **Soru:** açıklar: anonimlik ile hesap verebilirlik

1. Menü → **1) ayse → /mahzen**: kararma ve uyarı → **anladım, devam**; alt sıralar çürüyor.
2. Menü → **2) ayse → /mahzen/91**: **[ evet ]** → ışık yanar.

> **Konuşma:** Mahzen anonim ve geçicidir; alta düşen başlık çürür ve silinir. Katılımcılar isterse başlığı ifşa eder: eşik aşılınca ışık yanar, gölgelerin yerine takma adlar yazılır.

### Adım 10a · Operatörün sessiz değişikliği
**Süre:** 10 sn · **Soru:** açıklar: kurala güveni kim korur?

Geçiş: `yonetmelik_esigi` oylamasız 1/2'ye indirilir (sunucuyu işletenin yapabileceği).

1. Menü → **1) aylin → /defter** → **Doğrula**: *Yönetmelik: FARKLI*, başlık bordo.

> **Konuşma:** Son sürpriz: sunucuyu işleten kişi eşiği oylamasız indirdi. Defter, yönetmeliğin son oylanmış hâlinin hash'ini tutar ve farkı yakalar.

### Adım 10b · Karar Saati açılışında geri alınır
**Süre:** 12 sn · **Soru:** açıklar: tespit ve kalıcı iz

Geçiş: Karar Saati #2 açılır.

1. Menü → **1) aylin → /defter** → **Doğrula**: *Yönetmelik: tutarlı*; geçmişte *GERİ ALINDI*.

> **Konuşma:** Karar Saati açılırken fark tespit edildi, geri alındı ve deftere yazıldı. Sistem operatöre güvenmek zorunda, ama bu iz hiçbir zaman silinmez.

**Yeniden ölçmek ve videoyu yeniden almak** (yığın ve istemci çalışırken; Playwright ve Chromium yolu gerekir):

```bash
node scripts/demo-kaydi.mjs run A --video docs/demo.mp4
```

```bash
node scripts/demo-kaydi.mjs run B
```

```bash
node scripts/demo-kaydi.mjs md
```

Son komut iki çalıştırmayı karşılaştırır, her adımın süresini ve **Ölçüm** tablosunu günceller. Ölçümler `docs/demo-olcum/` altındadır.

## Olası sorular

DESIGN.md §15'teki bilinçli açıklardan en olası beşi:

1. **Bir kişi çok hesap açarsa?** (3. madde) E-posta doğrulaması bunu yalnızca yavaşlatır; gerçek çözüm e-Devlet gibi kimlik doğrulaması ve kapsam dışı. Baskın tespiti yeni ve birbirine yoğun bağlı hesap kümelerini sayımdan çıkarır; yanlış pozitifler de olabilir.
2. **Sunucu oyları görebilir mi?** (4. ve 33. madde) Evet: tuzları pencere boyunca sunucu tutar, takma kimliği kişiyle eşleştirebilir. Defter oyların sonradan değiştirilmediğini kanıtlar, sunucunun dürüst olduğunu kanıtlamaz.
3. **Oylar birkaç kişide toplanırsa?** (6. madde) Havale alma sınırı yok; Müşavir etiketi yoğunlaşmayı görünür yapar. Havale 180 günde kendiliğinden düşer: unutulmuş güç sıfırlanır, bilinçli olarak yenilenen güven kalır.
4. **Hâtif kime çalışıyor?** (7. ve 15. madde) Kuralları sistemi işleten yazar; Hâtif'e havale eden oyunu kural yazarına emanet eder. Hiç kimsenin oy vermediği bir oylamada Hâtif'in tek oyu sonucu belirler.
5. **Değiştirilemez maddeler gerçekten değiştirilemez mi?** (30. madde) Oylamayla değiştirilemezler; sunucuyu işleten kişi kodu ya da veriyi değiştirebilir. Son adımdaki gibi defter bunu yakalar ve Karar Saati geri alır, ama kod düzeyindeki değişikliği geri alamaz.

## Ölçüm

<!-- ölçüm: scripts/demo-kaydi.mjs --md ile güncellenir -->
İki çalıştırma (A: 2026-09-29 17:48 UTC, B: 2026-09-29 17:50 UTC), 1440 × 900 Chromium, Docker yığını. *Süre* adımın ekranda kaldığı toplam süredir: `demo next` komutu, sayfaların menüden açılması, tıklamalar, canlandırmalar ve konuşma notunun okunma süresine (dakikada 132 kelime) tamamlayan bekleme. *İşlem* bunlardan yalnızca komut, sayfa ve tıklama kısmıdır; canlıda konuşma bununla üst üste biner.

| Adım | A (sn) | B (sn) | İşlem A / B (sn) | Konuşma (sn) | Ekrandaki sayılar | A = B |
|---|---|---|---|---|---|---|
| 1 · Kayıt ve profil | 10,9 | 10,9 | 5,3 / 5,3 | 10,9 | 31 | ✓ |
| 2 · Öneri ve sessiz onay | 12,7 | 12,5 | 3,0 / 2,8 | 10,9 | 18 | ✓ |
| 3 · İstanbul vakası: R2 daraltma | 12,0 | 12,0 | 4,4 / 4,5 | 10,0 | 32 | ✓ |
| 4 · Eşzamanlı çoğunluk | 10,0 | 9,8 | 5,5 / 5,4 | 8,2 | 34 | ✓ |
| 5 · Havale ve Karar Saati | 15,6 | 15,6 | 12,0 / 12,0 | 12,3 | 297 | ✓ |
| 6 · Kapanış ve Şerh | 12,2 | 12,3 | 7,5 / 7,5 | 10,5 | 57 | ✓ |
| 7 · Silme | 12,3 | 12,3 | 5,6 / 5,6 | 10,5 | 44 | ✓ |
| 8 · Değiştirilemez maddeler | 10,9 | 10,8 | 4,8 / 4,7 | 9,1 | 33 | ✓ |
| 9 · Mahzen | 12,9 | 12,9 | 8,5 / 8,6 | 10,9 | 573 | ✓ |
| 10a · Operatörün sessiz değişikliği | 10,0 | 10,0 | 3,4 / 3,5 | 8,2 | 16 | ✓ |
| 10b · Karar Saati açılışında geri alınır | 11,6 | 11,6 | 5,8 / 5,8 | 9,5 | 22 | ✓ |
| **Toplam** | **131,0** | **130,7** | | | | ✓ |

Defter: A 626 kayıt, B 626 kayıt; hash zinciri birebir aynı.
