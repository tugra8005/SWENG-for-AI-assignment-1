"""Tohum: Meydan konularındaki ve Mahzen başlıklarındaki gündelik tartışma.

Senaryolardan bağımsızdır; forumun dolu ve çok sesli görünmesi içindir. Sağdan ve soldan, ılımlı
ve uç görüşler, felsefe ve mizah. Hiçbiri içerik kuralı ihlali değildir: sert görüş var, hakaret,
tehdit, kişisel bilgi ve reklam yok.

Kimin ne dediği tutarlıdır: nevzat muhafazakâr, fatih piyasacı, vedat milliyetçi-ulusalcı, burak
asayişçi; ipek sosyal demokrat, cansu ekolojist, umut sendikacı, gulsen devrimci sosyalist, harun
anarşist; yasemin ortada, ece rakamcı, dogan usulcü; melis, rana ve kaan şakacı.

Zamanlar tohum anından kaç gün önce olduğudur. Mesajlar konunun kabulünden sonra, yanıtlar
yanıtladıkları mesajdan sonra gelir. Parklar'daki mesajlar baskından (4 saat önce) en az bir gün
öncedir: ortak başlık etkileşimi (30 dakika) baskıncılara yeni kenar eklemez.
"""

from __future__ import annotations

# konu anahtarı → (anahtar, takma ad, kaç gün önce, metin, yanıtladığı anahtar)
MEYDAN_POSTS: dict[str, list[tuple[str, str, float, str, str | None]]] = {
    "bisiklet": [
        ("s_bis1", "fatih", 10.8,
         ("Her caddeye bisiklet yolu çizmek kolay; bedelini caddedeki esnaf öder. Otoparkı "
          "kalkan dükkânın müşterisi azalır. Önce talep ölçülsün: kaç kişi gerçekten bisikletle "
          "işe gidiyor?"),
         None),
        ("s_bis2", "cansu", 10.7,
         ("Talep, yol yapılınca oluşur. Otoyol yapılmadan önce de kimse 'kaç kişi otoyolda "
          "gidiyor' diye sormadı. Kentin havası da esnafın sorunu, yalnızca faturası geç "
          "geliyor."),
         "s_bis1"),
        ("s_bis3", "vedat", 10.5,
         ("Kopenhag, Amsterdam... Her şeyi Avrupa'dan taşıyoruz. Bizim şehirlerimiz yokuş, bizim "
          "insanımız işe takım elbiseyle gidiyor. Bu, yerli bir ulaşım planı değil, özenti bir "
          "proje."),
         None),
        ("s_bis4", "ipek", 10.4,
         ("Yokuş doğru bir itiraz, 'Avrupa' değil. Elektrikli bisiklet yokuşu çözüyor; İzmir'de "
          "BİSİM yıllardır çalışıyor. Mesele araç değil, yolun kime ayrıldığı."),
         "s_bis3"),
        ("s_bis5", "gulsen", 10.1,
         ("Caddenin neredeyse tamamı özel otomobile ayrılmışken buna 'tarafsız' diyoruz. "
          "Otomobil bir sınıf meselesi: arabası olanın şehri ile olmayanın şehri aynı değil. "
          "Bisiklet yolu küçük bir adım; asıl talep ücretsiz toplu taşıma olmalı."),
         None),
        ("s_bis6", "nevzat", 9.9,
         ("Her şeyi sınıfa bağlamayın. Rahmetli babam arabasını kırk ay taksitle almıştı, zengin "
          "değildi. İnsanın emekle aldığı arabayı düşman ilan etmek kimseyi bisiklete bindirmez."),
         "s_bis5"),
        ("s_bis7", "melis", 9.7,
         ("Ben bisiklete binmeyi bilmiyorum ama yolu destekliyorum. Belki yol yapılınca "
          "utanmadan öğrenirim."),
         None),
        ("s_bis8", "kaan", 9.65,
         ("Kordonda yetişkinlere öğreten gönüllüler var, gel. Düşersen oylamaya gerek yok, kendi "
          "kendine kalkarsın."),
         "s_bis7"),
        ("s_bis9", "harun", 9.2,
         ("Belediyeye dilekçe yazıp beklemek yerine bir cumartesi o caddede hep birlikte "
          "bisikletle dolaşalım. Yol kullananındır; izin kâğıdını beklemek zorunda değiliz."),
         None),
        ("s_bis10", "dogan", 9.1,
         ("Toplu sürüş güzel, ama karar burada oylandı ve muhatap belli. Kendi kafamıza göre yol "
          "'açmak' oylamanın kendisini anlamsızlaştırır."),
         "s_bis9"),
        ("s_bis11", "yasemin", 8.7,
         ("İki taraf da abartıyor. Ana caddeye korunaklı yol, ara sokaklara 30 km/sa sınırı. "
          "Arabaya düşmanlık da gerekmez, bisiklete düşmanlık da."),
         None),
        ("s_bis12", "ece", 7.9,
         ("Kısa yolculukların payını bilmeden konuşuyoruz. Belediyelerin ulaşım anketlerinde bu "
          "veri var; 5 km'nin altındaki yolculukları dilekçeye ek olarak isteyelim mi?"),
         None),
        ("s_bis13", "kerem", 7.5,
         ("Ceren'in okul çevresi önerisi bence en iyisi. Torunumu sabah bisikletle okula "
          "göndermek isterim, ama bu trafikte asla."),
         None),
        ("s_bis14", "aylin", 6.8,
         ("Ankara'da kış ve yokuşlar gerçekten sorun. Dilekçede şehir şehir farklı çözüm "
          "isteyelim; dört belediyeye tek kalıp olmasın."),
         None),
        ("s_bis15", "vedat", 6.6,
         ("İşte bu. Her şehrin kendi derdi var; Ankara'yı Amsterdam yapmaya çalışmayın."),
         "s_bis14"),
        ("s_bis16", "gulsen", 6.5,
         ("Amsterdam'ı da kimse 'Amsterdam yapmadı'. Yetmişlerde trafikte ölen çocuklar için "
          "sokağa çıkan aileler yaptı."),
         "s_bis15"),
        ("s_bis17", "rana", 5.2,
         ("Sayım yaptım: şimdiye kadar bu konuda 3 Amsterdam, 2 sınıf, 1 takım elbise, 1 yokuş. "
          "Kazanan yokuş."),
         None),
    ],
    "parklar": [
        ("s_park1", "nevzat", 9.3,
         ("Parklar ailelerindir. Gece yarısı kalabalığı başlayınca çocuklu aileler gelmez olur. "
          "22:00 makul."),
         None),
        ("s_park2", "harun", 9.2,
         ("Parklar herkesindir: aileler de, gece vardiyasından çıkan işçi de, evi dar olan genç "
          "de. Kapıya kilit vurmak güvenlik değil, kamusal alanı daraltmak."),
         "s_park1"),
        ("s_park3", "burak", 9.0,
         ("Güvenlik soyut bir şey değil. Bizim mahallede gece parkta kırılan banklar, sabah "
          "çocukların bulduğu cam şişeler var. Saat sınırı en azından denetlenebilir bir kural."),
         "s_park2"),
        ("s_park4", "ipek", 8.9,
         ("Kapanış saati yerine aydınlatma, tuvalet ve çeşme konuşalım. Kapalı park güvenli "
          "değildir, sadece boştur."),
         None),
        ("s_park5", "fatih", 8.6,
         ("Bütçe sorusu: gece bekçisi, aydınlatma, temizlik. Gece de açık kalacaksa bunu kim "
          "ödeyecek? 'Herkes' bir cevap değil."),
         None),
        ("s_park6", "gulsen", 8.5,
         ("'Kim ödeyecek' sorusu hep park için soruluyor. Yeni alışveriş merkezinin yolu için "
          "hiç sorulmuyor."),
         "s_park5"),
        ("s_park7", "vedat", 8.2,
         ("Mahalle bekçiliği bu milletin geleneğidir. Parkın kapısı değil bekçisi olsun; asayiş "
          "devletin işi, kilit vatandaşın değil."),
         None),
        ("s_park8", "cansu", 7.6,
         ("Bir de parkın asıl gece sakinleri var: kirpi, baykuş, yarasa. 'Sabaha kadar açık ve "
          "ışıl ışıl' onlar için kötü. Işığı azaltan, yürüyüş yolunu açık bırakan bir düzen "
          "olabilir."),
         None),
        ("s_park9", "yasemin", 7.5,
         ("Arada bir yol: oyun alanı 22:00'de kapansın, yürüyüş yolu açık kalsın, ışıklar yere "
          "baksın."),
         "s_park8"),
        ("s_park10", "melis", 6.1,
         ("Gece yarısı salıncakta sallanan bir yetişkin olarak itiraz ediyorum. 22:00'den sonra "
          "salıncağa vergi mi koyacaksınız?"),
         None),
        ("s_park11", "zeynep", 6.0,
         ("Rakip metin süresi dolmasa 'salıncaklar 24:00'e kadar' diye dördüncü metin eklerdim."),
         "s_park10"),
        ("s_park12", "kerem", 5.4,
         ("Yazın yatsıdan sonra cemaat parkta sohbet ediyor; 22:00 o mevsim için erken. Yaz–kış "
          "ayrımı bence ilker'in önerisinin en iyi tarafı."),
         None),
        ("s_park13", "umut", 4.8,
         ("Vardiyalı çalışan için akşam 22:00 günün tek boş saati. Parkın saatini 18:00'de işten "
          "çıkanlar belirlemesin."),
         None),
        ("s_park14", "ilker", 4.6,
         ("Yaz için gece yarısı önerim tam bu yüzden. Kışın zaten kimse gece parka çıkmıyor."),
         "s_park13"),
        ("s_park15", "nevzat", 4.4,
         ("Haklı bir nokta. Ailelerin huzuru ile çalışanın hakkı çatışmak zorunda değil; "
          "mahalleye göre karar verilsin, her yere tek saat değil."),
         "s_park13"),
        ("s_park16", "dogan", 3.9,
         ("Hatırlatma: kapanış oylaması onay oylaması. Birden fazla metni onaylayabilirsiniz; "
          "hiçbirini beğenmeyen hiçbirini onaylamayabilir."),
         None),
        ("s_park17", "rana", 1.2,
         ("Bu konudaki tek uzlaşma: kimse '20:00'de kapansın' metnini sevmiyor. Zeynep, kusura "
          "bakma."),
         None),
        ("s_park18", "zeynep", 1.1,
         ("Ben de pek sevmiyorum; kışın erken karardığı için yazmıştım."),
         "s_park17"),
    ],
    "pazar": [
        ("s_pazar1", "gulsen", 15.8,
         ("Zincir marketler her mahallede üç şube açarken pazar tezgâhının kirası artıyor. "
          "Pazar, dar gelirlinin son kalesi. Tezgâh kirası dondurulsun, üretici kooperatiflerine "
          "ücretsiz yer ayrılsın."),
         None),
        ("s_pazar2", "vedat", 15.6,
         ("Kooperatif kısmına katılıyorum, şaşırtıcı ama. Pazarda yerli üreticinin domatesi "
          "satılsın, ithal ürünün tezgâhı ayrı işaretlensin. Köylümüz kendi malını satamıyorsa "
          "bu bir beka meselesidir."),
         "s_pazar1"),
        ("s_pazar3", "cansu", 15.5,
         ("Etiket fikri iyi, ama 'yerli' değil 'yakın' diyelim. Antalya'dan gelen domatesle "
          "Silivri'den gelen aynı yolu gelmiyor."),
         "s_pazar2"),
        ("s_pazar4", "hakan", 14.9,
         ("Beşiktaş'taki akşam pazarı denemesine gittim. İlk hafta kalabalık, ikinci hafta "
          "yağmur, üçüncü hafta yalnızca ben ve bir simitçi."),
         None),
        ("s_pazar5", "melis", 14.8,
         ("Simitçi her yerde var. Belki asıl istikrar simitçidir."),
         "s_pazar4"),
        ("s_pazar6", "deniz", 13.5,
         ("Fiyat etiketi zorunluluğu pazarda da uygulansın; kilo fiyatını sormaya çekinen çok "
          "insan var."),
         None),
        ("s_pazar7", "mert", 13.4,
         ("Pazarlık da pazarın parçası ama. Etiket olsun, pazarlık da kalsın."),
         "s_pazar6"),
        ("s_pazar8", "rana", 12.0,
         ("Pazarcı nidaları somut olmayan kültürel miras sayılsın. 'Gel abla gel, bal gibi "
          "kavun' oylamaya sunulsa hemen EVET derim."),
         None),
        ("s_pazar9", "emre", 8.5,
         ("İBB yanıt verdi: Kasım'da Meclis gündemine alınması planlanıyormuş. Muhtarlığına "
          "görüş vermek isteyen mahallesini yazsın, toplu gönderelim."),
         None),
        ("s_pazar10", "ayse", 8.4,
         ("Kadıköy için ben yazarım; akşam pazarı önerisini de ekleyelim."),
         "s_pazar9"),
        ("s_pazar11", "vedat", 7.0,
         ("Yanıt güzel, ama resmî dilde 'planlanmaktadır' çoğu zaman 'unutulacaktır' demek. "
          "Kasım'da takipte olalım."),
         "s_pazar9"),
        ("s_pazar12", "gulsen", 6.9,
         ("Bu konuda vedat'la ikinci kez anlaştım. Endişelenmeye başladım."),
         "s_pazar11"),
    ],
    "felsefe": [
        ("s_fel1", "nevzat", 21.5,
         ("Listeye Burke'ün 'Fransız Devrimi Üzerine Düşünceler'ini önerebilir miyim? Burada "
          "sürekli 'her şeyi oylayalım' diyoruz; Burke geleneğin, yazılı olmayan aklın da bir "
          "oyu olduğunu söyler."),
         None),
        ("s_fel2", "gulsen", 21.3,
         ("Burke okunsun, yanında Paine'in 'İnsan Hakları' da. İkisi aynı devrime bakıp karşıt "
          "şeyler gördü; tartışma kendiliğinden çıkar."),
         "s_fel1"),
        ("s_fel3", "selin", 21.0,
         ("Çok iyi bir ikili. Menon'dan sonra Burke ile Paine'i aynı buluşmada okuyalım."),
         "s_fel2"),
        ("s_fel4", "fatih", 20.2,
         ("Rawls mu, Nozick mi? Benim cevabım belli: başkasının emeğinin ürünü üzerinde, ne "
          "kadar iyi niyetli olursa olsun, oylamayla hak iddia edilemez."),
         None),
        ("s_fel5", "ipek", 20.0,
         ("Rawls'un cehalet peçesini burada deneyelim: hangi şehirde, hangi gelirle doğacağını "
          "bilmeden etkinlik bütçesini nasıl bölerdin?"),
         "s_fel4"),
        ("s_fel6", "fatih", 19.8,
         ("Peçenin arkasında riskten kaçınacağımı varsayıyorsun. Ben kumar oynamayı seven biri "
          "olabilirim."),
         "s_fel5"),
        ("s_fel7", "harun", 18.5,
         ("Oylama da bir tahakküm biçimi değil mi? Çoğunluk kralın yerini aldı, o kadar. "
          "Proudhon'un dediği gibi: yönetilmek, gözetlenmek, denetlenmek, sayılmaktır."),
         None),
        ("s_fel8", "dogan", 18.3,
         ("Değiştirilemez maddeler bunun için var: çoğunluk kral olamasın diye. Bütünüyle "
          "kuralsız bir topluluk da en güçlünün kuralına düşer."),
         "s_fel7"),
        ("s_fel9", "tolga", 18.1,
         ("Hobbes'u Meşveret'e uyarlamışsın: yönetmelik olmasaydı hayat 'yalnız, yoksul, iğrenç, "
          "vahşi ve kısa' olurdu."),
         "s_fel8"),
        ("s_fel10", "vedat", 16.0,
         ("Hep Batı felsefesi okuyoruz. Fârâbî'nin 'Erdemli Şehir'i, Ziya Gökalp okunmayacak mı? "
          "Kendi düşünce geleneğimizi bilmeden Platon'a koşuyoruz."),
         None),
        ("s_fel11", "elif", 15.8,
         ("Fârâbî'ye tamamen katılıyorum; 'Erdemli Şehir' zaten Platon'la konuşan bir metin. "
          "Gökalp'i de okuyalım ama tartışarak: millet tanımı bugün de tartışmalı."),
         "s_fel10"),
        ("s_fel12", "vedat", 15.6,
         ("Tartışarak okuyalım tabii. Tartışmaktan korkan ben değilim."),
         "s_fel11"),
        ("s_fel13", "deniz", 13.0,
         ("Elif'in Euthyphron sorusuna ek: bir öneri kabul edildiği için mi bağlayıcı, doğru "
          "olduğu için mi kabul edildi? Hâtif'in EVET'i hangisine giriyor?"),
         None),
        ("s_fel14", "kaan", 12.8,
         ("Hâtif'inki üçüncü seçenek: kurallara uyduğu için. Kant'a sorsan ödev ahlakı der, bana "
          "sorsan bürokrasi."),
         "s_fel13"),
        ("s_fel15", "melis", 10.0,
         ("Menon'u okumadan buluşmaya gelen, bildiğini mi hatırlıyor, bilmediğini mi?"),
         None),
        ("s_fel16", "selin", 9.9,
         ("Sokrates'e göre hatırlıyor. Bana göre okumamış. Yine de gelsin."),
         "s_fel15"),
        ("s_fel17", "gulsen", 7.0,
         ("Bir buluşma da Marx'a ayrılsın: filozoflar dünyayı yalnızca yorumladı, oysa sorun onu "
          "değiştirmek. Bu forum belki ilk kez yorumu karara bağlıyor."),
         None),
        ("s_fel18", "nevzat", 6.9,
         ("Değiştirmeden önce neyi koruyacağımızı bilmek lazım. Ama Marx okunursa ben de "
          "gelirim; karşı taraf olarak."),
         "s_fel17"),
        ("s_fel19", "tolga", 2.5,
         ("Menon için hazırlık sorusu: erdem öğretilebilir mi? Öğretilebiliyorsa erdemli "
          "babaların çocukları neden erdemli olmuyor? (Menon 93–94)"),
         None),
    ],
    "film": [
        ("s_film1", "hakan", 20.5,
         ("Belgesel ayından sonra bir Yeşilçam ayı yapalım. Hababam Sınıfı'nı salonda topluca "
          "izlemek başka olur."),
         None),
        ("s_film2", "nevzat", 20.3,
         ("Yeşilçam ayına varım. Selvi Boylum Al Yazmalım da olsun: emek, sadakat, aile, hepsi "
          "orada."),
         "s_film1"),
        ("s_film3", "gulsen", 19.0,
         ("Yol ya da Sürü. Sinema yalnızca eğlence değil, tanıklık da."),
         None),
        ("s_film4", "vedat", 18.8,
         ("Tanıklık herkes içinse bir de Kurtuluş Savaşı'nı anlatan bir film olsun. O da "
          "tanıklık."),
         "s_film3"),
        ("s_film5", "leyla", 18.6,
         ("İki öneri de yerinde. Program tek bir taraftan olmasın; her ay filmi başka biri "
          "seçsin."),
         "s_film4"),
        ("s_film6", "irem", 16.5,
         ("Altyazı konusunda hakan'a katılıyorum. Bir de film başlamadan sessiz mod hatırlatması; geçen "
          "sefer arka sırada biri maç izliyordu."),
         None),
        ("s_film7", "melis", 16.4, "O bendim. Penaltıydı, affedin.", "s_film6"),
        ("s_film8", "gizem", 14.0, "Animasyon da sinemadır. Ghibli gecesi isteyen var mı?", None),
        ("s_film9", "mert", 13.8,
         ("Ruhların Kaçışı'yla başlarız, sonra bir saat 'çocuk filmi mi yetişkin filmi mi' diye "
          "tartışırız."),
         "s_film8"),
        ("s_film10", "fatih", 12.0,
         ("Filmleri oylamak yerine bilet satsak? Talep gören film gösterilir. En iyi programcı "
          "talepten anlayandır."),
         None),
        ("s_film11", "ipek", 11.8,
         ("O zaman herkes en popüler filmi izler, kimse Dekalog'u keşfetmez. Ortak programın "
          "amacı biraz da beklenmeyeni göstermek."),
         "s_film10"),
        ("s_film12", "fatih", 11.6,
         ("Dekalog'u ben de severim; zorla izletilmezse daha çok severim."),
         "s_film11"),
    ],
    "siir": [
        ("s_siir1", "kerem", 20.0,
         ("Necip Fazıl'dan 'Kaldırımlar'ı okumak istiyorum. Şiiri şairin siyasetinden "
          "ayırabilirsek bu akşamlar başarılı olur."),
         None),
        ("s_siir2", "gulsen", 19.8,
         ("Ayırırım, aynı akşam biri de Nâzım'ın 'Memleketimden İnsan Manzaraları'ndan okursa."),
         "s_siir1"),
        ("s_siir3", "okan", 19.6,
         ("Anlaştık: aynı akşam 'Kaldırımlar' ve 'Memleketimden İnsan Manzaraları'. Sırayı kura "
          "belirlesin."),
         "s_siir2"),
        ("s_siir4", "vedat", 18.0,
         ("Mehmet Âkif'in 'Çanakkale Şehitlerine'si de listede olsun. Okunurken ayağa kalkmak "
          "serbest."),
         None),
        ("s_siir5", "harun", 17.8, "Oturarak dinlemek de serbest olsun o zaman.", "s_siir4"),
        ("s_siir6", "vedat", 17.6, "Serbest. Kalkan da kalkmayan da dinlesin, yeter.", "s_siir5"),
        ("s_siir7", "pinar", 15.0,
         ("Bir akşam da yalnızca kadın şairlere ayrılsın: Gülten Akın, Didem Madak, Lale Müldür."),
         None),
        ("s_siir8", "melis", 12.5,
         ("Ben kendi şiirimi okuyacağım. Uyak: yok. Ölçü: yok. Cesaret: var."),
         None),
        ("s_siir9", "rana", 12.4, "Szymborska da böyle başlamıştır. (Başlamamıştır.)", "s_siir8"),
        ("s_siir10", "tolga", 10.0,
         ("Şiir oylanmaz ama hangi şiirin okunacağı oylanabilir. Bu bir kategori hatası değil, "
          "programcılık."),
         None),
        ("s_siir11", "okan", 0.0015,
         ("Ekim şiir akşamının önerisini açtım: Cemal Süreya, ortak salonda. İtiraz eden olmazsa "
          "yarın takvimde."),
         None),
    ],
    "belgesel-ayi": [
        ("s_belg1", "cansu", 16.0,
         ("Bir hafta iklime ayrılsın; ama korkutan değil, çözüm gösteren türden."),
         None),
        ("s_belg2", "fatih", 15.8,
         ("Çözüm gösteren iklim belgeseli, nadir duyduğum bir öneri; destekliyorum. Teknolojinin "
          "çözdüğü sorunları görmek isterim."),
         "s_belg1"),
        ("s_belg3", "gulsen", 15.0,
         ("Bir hafta da emek belgeseli: maden, tekstil atölyesi, kurye. Şehir belgeseli "
          "dediğimiz şeyin içinde çalışanlar da var."),
         None),
        ("s_belg4", "vedat", 14.0,
         ("Anadolu'nun unutulan zanaatları üzerine bir belgesel olsun: bakırcılar, keçeciler. "
          "Bunlar kaybolunca bir daha gelmez."),
         None),
        ("s_belg5", "nevzat", 13.8,
         ("Çok iyi olur. Çocuklarımıza bir şey bırakmak lazım."),
         "s_belg4"),
        ("s_belg6", "mert", 12.5,
         ("Her gösterimin sorusunu önceden yazalım demiştim; ilki şu olsun: kamerayı nereye "
          "çevirdiğin bile bir seçimken belgesel tarafsız olabilir mi?"),
         None),
        ("s_belg7", "yasemin", 12.3,
         ("Tarafsız olamaz, ama dürüst olabilir: neyi göstermediğini söyleyen belgesel."),
         "s_belg6"),
    ],
    "dekalog": [
        ("s_dek1", "irem", 5.9,
         ("Gösterim cuma 20:00. 19:45'te kapıda olursak altyazıyı denemeye vakit kalır."),
         None),
        ("s_dek2", "hakan", 5.8, "Altyazılı kopyayı ben getiriyorum, yedeği de var.", "s_dek1"),
        ("s_dek3", "gizem", 4.5,
         ("Film bir saat ama sonrasına iki saat ayıralım; Dekalog kısa bir film değil, uzun bir "
          "soru."),
         None),
        ("s_dek4", "nevzat", 3.4,
         ("İlk kez katıldım. Hesap yapan baba, buz tutan göl... Bilgiye bu kadar güvenmek kibir "
          "mi, sevgi mi, hâlâ düşünüyorum."),
         None),
        ("s_dek5", "harun", 3.3,
         ("İkisi birden belki. Babanın yanılması bilimin değil, kesinliğin trajedisi."),
         "s_dek4"),
        ("s_dek6", "leyla", 3.1,
         ("Dekalog II için öneri açacağım: aynı salon, iki hafta sonra cuma. Gelecek olanlar "
          "şimdiden yazarsa salonu ona göre isteriz."),
         None),
        ("s_dek7", "melis", 2.8,
         ("Kapıda katılan sekiz kişiden biri bendim. 'Geliyorum' demeyi unuttum; rapordaki "
          "'gerisi kapıda katıldı' cümlesinin kahramanıyım."),
         None),
    ],
    "menon": [
        ("s_men1", "kaan", 5.5,
         ("Bağlantı paylaşılınca İzmir'den katılacağım. Hangi çeviriyi okuyoruz?"),
         None),
        ("s_men2", "selin", 5.4,
         ("Elimizdeki iki çeviriyi karşılaştırarak okuyalım; ayrıştıkları yerleri buluşmada "
          "konuşuruz."),
         "s_men1"),
        ("s_men3", "elif", 3.0,
         ("Köle çocuğun metinde adı bile yok. Sokrates'in 'herkes bilir' kanıtı adı olmayan "
          "birine dayanıyor. Bunu da konuşalım."),
         None),
        ("s_men4", "fatih", 2.8,
         ("Bence Platon'un amacı tam bu: bilgi soyla, mülkle gelmiyor. Bu açıdan oldukça "
          "eşitlikçi bir sahne."),
         "s_men3"),
        ("s_men5", "gulsen", 2.7,
         ("Eşitlikçi bir sahnede çocuğun hâlâ köle olması da ayrı bir ders."),
         "s_men4"),
        ("s_men6", "deniz", 1.0,
         ("Okuma notu: 80d'deki Menon paradoksuyla başlayalım; köle çocuk sahnesi 82b'de."),
         None),
    ],
}

# Mahzen dolgu başlığı (soru) → yanıtlar. Biçim seed.MAHZEN_DISCUSSIONS ile aynı: "op" başlığı
# açandır, "{n}" n. mesaja (0 = açılış) >>N referansı olur. En çok 7 yanıt: yanıtlar bir sonraki
# dolgu başlık açılmadan (90 dakika) biter.
MAHZEN_MORE: dict[str, list[tuple[str, str]]] = {
    "Bir ağaç ormanda devrilirse ve kimse duymazsa ses çıkar mı?": [
        ("ferhat", "Hava titreşir; ses dediğimiz şey bir kulak ister. Titreşim var, ses yok."),
        ("kaan", "{1} O zaman bu başlığı kimse okumazsa ben de yazmamış mı oluyorum?"),
        ("op", "{2} Mahzen'de zaten öyle: yazıyorsun, çürüyor, kimse duymamış oluyor."),
        ("cansu", ("Ağaç devrildiyse önce kimin kestiğine bakalım. Ormanda kendiliğinden devrilen "
                   "ağaç sanıldığından az.")),
        ("melis", "{4} Felsefe başlığına çevre denetimi geldi. Bu forumun en güzel tarafı."),
    ],
    "Mutluluk bir amaç mı, bir yan ürün mü?": [
        ("melis", ("Yan ürün. Amaç yapınca ilk iş onu ölçmeye başlıyorsun, ölçtüğün an da "
                   "kaçıyor.")),
        ("ece", "{1} Goodhart yasası mutluluğa da işliyor demek."),
        ("nevzat", ("Annemlerin kuşağı mutluluğu sormazdı; çalışır, çocuk büyütürdü. Mutlu "
                    "muydular? Galiba evet.")),
        ("op", "{3} Sormamak belki mutluluğun şartı."),
    ],
    "Adalet eşitlik midir, hakkaniyet mi?": [
        ("ipek", ("Eşitlik başlangıç çizgisi, hakkaniyet yarışın kendisi. Herkese aynı numara "
                  "ayakkabı vermek, ayağı farklı olana adalet değil.")),
        ("fatih", ("{1} Kimin ayağının kaç numara olduğuna kim karar veriyor? Hakkaniyet dediğin, "
                   "ölçüyü tutanın keyfi.")),
        ("gulsen", "{2} Şu an ölçüyü piyasa tutuyor. Onun keyfi daha mı adil?"),
        ("fatih", ("{3} Piyasanın keyfi yok, milyonlarca insanın tercihi var. Hangi kurul "
                   "kararından olsa iyidir.")),
        ("op", ("Bu forum bir cevap vermiş aslında: eşit kesinti adil sayılıyor, orantısız "
                "kesinti ikinci oylamaya gidiyor. Eşitlik varsayılan, hakkaniyet istisna.")),
        ("harun", "{5} Adaleti bir eşik değerine çevirdik: 10 yüzde puanı. Bürokrasinin şiiri."),
    ],
    "İnsan doğası diye bir şey var mı?": [
        ("burak", ("Var ve iyimser değil. Kuralsız bir yerde ilk gün herkes iyi niyetli, ikinci "
                   "gün biri kapıyı kilitler. Hobbes haklıydı.")),
        ("cansu", ("{1} Rousseau da aynı kapıya bakıp 'ilk kez bir toprağı çitle çevirip burası "
                   "benim diyen' insanla her şeyin bozulduğunu söyler.")),
        ("burak", "{2} Çit olmasa ne olurdu? Herkes herkesin tarlasına girerdi."),
        ("gulsen", ("{3} Ya da tarlayı herkes birlikte sürerdi. İmece yüzyıllardır bunun mümkün "
                    "olduğunu gösteriyor.")),
        ("tolga", ("'İnsan doğası' lafı çoğu zaman bir tartışmayı bitirmek için kullanılıyor. "
                   "Tartışmayı bitirmek de mi insan doğası?")),
        ("op", "{5} Belki insan doğası tam da bu: kendi doğası hakkında anlaşamamak."),
    ],
    "Gelenek geçmişin oyu mudur?": [
        ("nevzat", ("Evet. Chesterton buna ölülerin demokrasisi der: atalarımızı sırf öldükleri "
                    "için oy hakkından mahrum etmeyelim.")),
        ("harun", "{1} Ölüler oy veriyorsa mezar taşlarına itiraz hakkı istiyorum."),
        ("cansu", ("Gelenek oy değil, bir deneyin sonucu: işe yarayan kalmış. Ama koşullar "
                   "değişince deney yeniden yapılır.")),
        ("nevzat", ("{3} Yapın, ama çiti sökmeden önce neden dikildiğini öğrenin. Neden "
                    "dikildiğini bilmeyen sökmesin.")),
        ("op", ("Değiştirilemez maddeler tam olarak bu: kurucuların oyu, yaşayanların oyundan "
                "güçlü. Geleneği yönetmeliğe yazmışız.")),
        ("yasemin", ("{5} Tek çıkışı da forumu baştan kurmak. Gelenekçilerin bile bu kadarını "
                     "istediğinden emin değilim.")),
    ],
    "Mülkiyet doğal bir hak mıdır?": [
        ("gulsen", ("Doğal değil. Doğada tapu yok. Tapuyu devlet verir, devleti de güçlü olan "
                    "kurar.")),
        ("fatih", ("{1} Doğada hastane de yok; doğal olmayan her şey kötü değil. Kendi emeğimle "
                   "yaptığım masa benimdir, bunu söylemek için devlete ihtiyacım yok.")),
        ("harun", "{2} Masa senin. Masayı yaptığın ağacın ormanı kimin?"),
        ("fatih", "{3} İlk kez emeğini katanın. Locke'u okuyun."),
        ("gulsen", ("{4} Locke'un bir şartı da var: başkalarına yeterince ve aynı iyilikte "
                    "bırakmak. Kira artışlarına bakınca o şart çoktan çiğnenmiş.")),
        ("op", ("İkiniz de Meşveret'in bütçesini ortak sayıyorsunuz ama. Etkinlik bütçesinin "
                "sahibi kim? Ontolojide yazıyor: Genel.")),
        ("melis", ("Benim tek mülküm bu başlıktaki gölge kimliğim, o da bir sonraki başlıkta "
                   "değişiyor.")),
    ],
    "Sınırlar haritada mı çizilir, akılda mı?": [
        ("vedat", ("Haritada çizilir, akılda korunur. Sınırını unutan millet önce haritasını, "
                   "sonra adını kaybeder.")),
        ("harun", ("{1} Sınırlar savaştan sonra masa başında cetvelle çizilmiş çizgiler. Ben bir "
                   "çizgiyi değil, insanları severim.")),
        ("vedat", ("{2} O masaya oturabilmek için önce cephede olmak gerekiyordu. Cetveli de "
                   "oradakilerin bedeli tuttu.")),
        ("ipek", ("İkiniz de haklısınız ve bu korkutucu: sınır hem gerçek bir bedel hem keyfî "
                  "bir çizgi.")),
        ("op", ("Burada da sınır var: İstanbul kapsamı Ankara'nın payına karar veremez. Kimse "
                "buna ulusalcılık demiyor.")),
        ("kaan", "{5} Çünkü İstanbul'un ordusu yok. Trafiği var."),
    ],
    "Mükemmel bir dünya sıkıcı olur muydu?": [
        ("melis", "Olurdu. Şikâyet edecek bir şey kalmazsa bu foruma kim yazacak?"),
        ("gulsen", "Sömürünün olmadığı bir dünya sıkıcıysa o sıkıntıya razıyım."),
        ("nevzat", ("{2} Herkesin eşit olacağı ütopyalar genelde en eşitsiz yerler çıktı. "
                    "Mükemmel dünya vaat eden önce mükemmel olmayan bir köprü yapsın.")),
        ("gulsen", ("{3} O köprüyü yapan işçinin sendikası olsun, gerisini konuşuruz.")),
        ("op", ("Mükemmel bir dünyada Karar Saati olmazdı; karar verilecek bir şey kalmazdı. Ben "
                "Pazar akşamlarımı kaybetmek istemem.")),
        ("rana", ("{5} Pazar akşamı oylamaya, Pazartesi sabahı işe gidiyoruz. Mükemmel dünya "
                  "bunun tam tersi olurdu.")),
    ],
    "Gülmek bir itiraz biçimi midir?": [
        ("rana", ("Nasreddin Hoca bütün bir hukuku kazan fıkrasıyla eleştirdi: kazanın doğurduğuna "
                  "inandıysan öldüğüne de inanacaksın.")),
        ("kerem", ("Gülmek itiraz olabilir ama önce saygı lazım. Her şeye gülen aslında hiçbir "
                   "şeye itiraz etmiyordur.")),
        ("op", ("{2} Ya da her şeye itiraz ediyordur ve başka aracı yoktur. Gücü olmayanın "
                "silahı mizahtır.")),
        ("melis", ("İtiraz eşiği üç. Üç kişi gülerse öneri yavaş şeride geçsin; bunu yönetmelik "
                   "önerisi olarak açacağım.")),
        ("dogan", ("{4} Mahzen'den öneri açılamaz. İfşa oylaması geçerse başlık bir konu "
                   "önerisi taslağına döner; o zaman da adın görünür.")),
        ("melis", "{5} Gördünüz mü? Usul mizahın düşmanıdır."),
    ],
    "Toplu taşımada telefonla konuşmak kaba mıdır?": [
        ("umut", "Kaba değil. Hoparlörü açmak ise oylama gerektirir."),
        ("melis", ("{1} Dün metrobüste biri bütün vagona düğün planını anlattı. Sonunda kendimi "
                   "davetli gibi hissettim.")),
        ("nevzat", ("Eskiden vapurda herkes gazetesini okurdu, kimse kimseyi rahatsız etmezdi. "
                    "Şimdi herkes bir yayın kanalı.")),
        ("harun", "{3} Eskiden de vapurda bağıran simitçiler vardı. Nostalji seçici bir kulaktır."),
        ("op", ("Kural istemem; bakışmak yeter. Bir vagon dolusu insanın sessiz bakışı en güçlü "
                "itirazdır.")),
        ("rana", "{5} Bakışmanın eşiği ne? Aktif yolcuların %5'i mi?"),
    ],
    "Kendi seçmediğimiz bir mirastan sorumlu muyuz?": [
        ("ipek", ("Borcu miras alan mirası reddedebilir, tarih reddedilemiyor. Sorumlu değiliz "
                  "belki ama hesabını vermek zorundayız.")),
        ("vedat", ("{1} Hesap hep hatalar için mi soruluyor? Atalarımızın zaferlerini de miras "
                   "aldık. Ayıbı devralıp onuru reddetmek tutarsızlık.")),
        ("elif", ("{2} Onuru almak kolay, ayıbı almak zor; sorumluluğun ölçüsü bu yüzden ayıp "
                  "tarafında.")),
        ("vedat", ("{3} O ölçüyü kim koyuyor? Tarihi yalnızca suçlu aramak için okuyan ondan bir "
                   "şey öğrenmez.")),
        ("op", ("Sorumluluk değil, dikkat bence: bize geçeni görmek ve devam ettirip "
                "ettirmeyeceğimize karar vermek.")),
        ("tolga", ("{5} Miras da bir öneri yani: kabul edersen senin olur, itiraz edersen yavaş "
                   "şeride geçer.")),
    ],
    "Bir makine anlamı anlayabilir mi?": [
        ("ece", ("Hâtif hiçbir şey anlamıyor ve her öneriye yorum yazıyor. Bazı insanlardan daha "
                 "dürüst bir durum.")),
        ("tolga", ("{1} Searle'ün Çince odası: kuralları uygulayan anlamış sayılmaz. Hâtif tam bir "
                   "Çince odası.")),
        ("op", ("{2} Peki biz? Biz de kuralları uygulayıp 'anladım' diyoruz. Fark odanın içinde "
                "birinin olduğunu hissetmemiz mi?")),
        ("harun", ("Makinenin anlayıp anlamaması umurumda değil; makinenin oyunu kimin yazdığı "
                   "umurumda.")),
        ("ece", "{4} Yazıyor zaten: Hâtif'in kurallarını onu işleten yazar. Bilinçli açık."),
        ("melis", "Hâtif'e havale veren varsa itiraf etsin. Mahzen'deyiz, kimse bilmeyecek."),
        ("op", "{6} Havale sayısı Hâtif'in profilinde yazıyor. Mahzen'e bile gerek yok."),
    ],
    "Hız bizi özgürleştirir mi, köleleştirir mi?": [
        ("umut", ("Kuryelere sorun. On dakikada teslimat sözü verilen yerde hız birinin sırtına "
                  "biniyor.")),
        ("fatih", ("{1} Kimse kuryeyi zorla çalıştırmıyor; o işi seçen var. Hız tüketiciye "
                   "özgürlük, çalışana iş.")),
        ("gulsen", ("{2} Seçenekler açlıkla kuryelikse buna seçim denmez. Hız, sermayenin zamanı "
                    "sıkıştırma biçimi.")),
        ("yasemin", ("İkisi de doğru. Hızlı tren beni özgürleştiriyor, on dakikalık teslimat "
                     "başkasını yoruyor. Soru hız değil, bedeli kimin ödediği.")),
        ("op", ("Meşveret yavaş tasarlanmış: olgunlaşma süresi, haftada bir Karar Saati. Burada "
                "yavaşlık bir güvence.")),
        ("kaan", "{5} Buna bir hafta sonra cevap vereceğim. Olgunlaşma süresi."),
    ],
    "Kura adil bir seçim yöntemi midir?": [
        ("deniz", ("Atina'da görevlilerin çoğu kurayla belirlenirdi. Aristoteles'e göre seçim "
                   "aristokratik, kura demokratikti.")),
        ("burak", "{1} Kurayla seçilen birine şehrin bütçesini emanet eder misin? Ben etmem."),
        ("deniz", "{2} Oyla seçilene ediyor musun? En azından kura satın alınamaz."),
        ("ipek", ("Yurttaş meclisleri bunu deniyor: rastgele seçilen yüz kişi bir konuyu aylarca "
                  "çalışıyor. Sonuçlar şaşırtıcı derecede ölçülü.")),
        ("op", "Mahzen başlıkları da bir tür kura: hangisinin yukarıda kalacağı neredeyse rastgele."),
    ],
    "Başkası adına karar vermek ne zaman meşrudur?": [
        ("selin", ("Bana beş havale verildi. Her Pazar beş kişinin yerine oy verirken bunu "
                   "düşünüyorum: onların hakkını değil, güvenini taşıyorum.")),
        ("harun", "{1} Temsil, susturmanın kibar adı. Beş kişi beş kez konuşabilirdi."),
        ("selin", ("{2} Konuşabilirler; havaleyi geri almak bir tık. Kimse susturulmadı, sadece "
                   "yoruldu.")),
        ("nevzat", ("Babam bizim adımıza çok karar verdi, çoğu doğruydu. Meşruiyet sonuçla mı "
                    "ölçülür, rızayla mı?")),
        ("ece", ("{4} İkisiyle de: rıza başta, sonuç sonra. Havalenin 180 günde düşmesi bu yüzden; "
                 "rıza tazelensin.")),
    ],
    "Herkesin bildiği yalan hâlâ yalan mıdır?": [
        ("rana", ("'Bir sonraki otobüs boş gelir' diyen şoför herkesin bildiği yalanı söylüyor ve "
                  "hepimiz bunu sevgiyle kabul ediyoruz.")),
        ("tolga", "Yalan değil, ritüel. İki taraf da doğru olmadığını biliyor; kimse aldatılmıyor."),
        ("gulsen", ("{2} Siyaset de ritüele döndüyse sorun büyük. Herkes vaadin tutulmayacağını "
                    "biliyor ve yine alkışlıyor.")),
        ("fatih", "{3} Bu konuda anlaştık. Bedeli bütçede yazmayan vaat yalandır."),
        ("op", ("Burada vaat yok; önerinin metni ve deftere geçen hash var. Belki bu yüzden "
                "sıkıcı, belki bu yüzden güvenilir.")),
    ],
    "Kimliğimizi seçer miyiz, yoksa bize mi verilir?": [
        ("vedat", ("Verilir. Dilini, toprağını, bayrağını sen seçmedin; onlar seni seçti. Bunu "
                   "inkâr eden köksüz kalır.")),
        ("ipek", "{1} Verilir, sonra seçilir. Hangi parçasını büyüteceğine sen karar verirsin."),
        ("harun", ("Burada kimliğim iki alan: şehir ve doğum tarihi. Sistem beni bunlarla "
                   "kapsamlara ayırıyor ve ben itiraz edemiyorum.")),
        ("op", ("{3} İlgi kapsamları seçiliyor ama. Şehir veriliyor, ilgi seçiliyor; kimlik "
                "tartışması iki tabloya bölünmüş.")),
        ("kerem", ("İkisini birden taşıyorum: Bursalıyım ve sinema seviyorum. Biri doğumdan, biri "
                   "tercihten; ikisi de ben.")),
    ],
}
