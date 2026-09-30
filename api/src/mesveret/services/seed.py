"""Tohum veri ve demo senaryoları.

Sahte saat ``SEED_NOW`` anına (Salı 29 Eylül 2026, 10:00 İstanbul) kurulur. Geçmiş tarihli
içerik bir zaman çizelgesine yazılır ve zaman sırasıyla oluşturulur; böylece defter
kayıtlarının zaman damgaları içeriğin gerçek zamanıyla aynı olur. Tüm tohum hesaplarının
şifresi ``DEMO_PASSWORD``.

Senaryolar (README'de adım adım):
1. İstanbul vakası — R2 daraltma; bölünemeyen kaynakla red.
2. Havale zinciri — aylin → baris (genel), baris → ceren (Ulaşım); ceren'in ağırlığı 3.
3. Yönetmelik değişikliği — %60 geçemez, 2/3 geçer.
4. Silme — gerekçesiz silme reddedilir; gerekçeli silme %60 ile geçemez, %67 ile geçer (sansür
   şeridi kuralı anar, içerik defterde durur); kendi mesajını silme basit çoğunlukla geçer.
5. Kapanış — üç rakip metin, onay oylaması, kaybeden Şerh ekler.
6. Mahzen — ifşa oylaması, geçiş animasyonu, öneri taslağı; denetimsiz bir şiir başlığı ve dolgu
   başlıklarda tartışmalar.
7. Baskın — art arda açılmış bağlantılı hesaplar işaretlenip dışlanır.
8. Hâtif — etiket önerisi ve deterministik oy.
9. Olgunlaşma — Karar Saati'nden 10 dakika önce açılan genel kapsamlı öneri 7 gün bekler.
10. Eşzamanlı çoğunluk — "İstanbul payının yarısı Ankara'ya" Genel'de geçer, İstanbul'un ayrı
    oylamasında reddedilir; "Tüm şehirlerin payında %10 kesinti" orantısız değildir, tek oylamayla
    geçer.
14. Pay çakışması — "Tüm şehirlerin payında %5 artış" aynı bütçeye dokunur ve kabul oyu alır, ama
    №18 (kesinti) önce uygulandığı için hedefleri geçersizdir: çakışma nedeniyle uygulanamaz.

Oylanacak senaryo önerileri, son planlı oturumdan (Pazar 27 Eylül) sonra olgunlaşacak
biçimde 21–22 Eylül'de açılır; böylece o oturumu kaçırıp kuyrukta bekliyor olmaları tutarlıdır.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import CellarPost, DevVotePlan, Proposal, SchedulerState, Topic, User
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.scopes import ScopeSubtype
from mesveret.services import (
    auth,
    cellar,
    delegation,
    ontology,
    oracle,
    proposals,
    scheduler,
    topics,
)
from mesveret.services.proposals import ProposalInput

SEED_NOW = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)  # Salı 10:00 İstanbul
DEMO_PASSWORD = "mesveret-demo"

AREAS = [
    ("kultur", "Kültür", None, ("kültür", "sanat", "festival")),
    ("sinema", "Sinema", "kultur", ("sinema", "film", "yönetmen", "gösterim")),
    ("belgesel", "Belgesel", "sinema", ("belgesel",)),
    ("kisa-film", "Kısa film", "sinema", ("kısametraj",)),
    ("edebiyat", "Edebiyat", "kultur", ("edebiyat", "roman", "kitap", "yazar")),
    ("siir", "Şiir", "edebiyat", ("şiir", "şair", "dize")),
    ("kent", "Kent", None, ("kent", "şehir", "mahalle", "belediye")),
    ("ulasim", "Ulaşım", "kent", ("ulaşım", "otobüs", "metro", "tramvay", "sefer")),
    ("bisiklet", "Bisiklet", "ulasim", ("bisiklet", "pedal")),
    ("parklar", "Parklar ve yeşil alan", "kent", ("park", "yeşil", "bahçe")),
    ("bilim", "Bilim ve düşünce", None, ("bilim", "araştırma")),
    ("felsefe", "Felsefe", "bilim", ("felsefe", "filozof", "düşünce")),
    ("etik", "Etik", "felsefe", ("etik", "ahlak", "erdem")),
    ("teknoloji", "Teknoloji", "bilim", ("teknoloji", "yazılım", "internet")),
]

CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa"]

RESOURCES = [
    ResourceInfo(
        "butce", ResourceKind.ORTAK, "Etkinlik bütçesi", "genel",
        divisible=True, division_type=ScopeSubtype.SEHIR,
        shares={"sehir:istanbul": 4000, "sehir:ankara": 6000, "sehir:izmir": 5000,
                "sehir:bursa": 5000},
        aliases=("bütçe", "etkinlik bütçe"),
    ),
    ResourceInfo("salon", ResourceKind.ORTAK, "Ortak toplantı salonu", "genel",
                 aliases=("salon", "toplantı salon")),
]

# (takma ad, ad soyad, il, doğum tarihi, ilgi alanları)
NAMED = [
    ("ayse", "Ayşe Yıldız", "İstanbul", date(1995, 3, 14), ("sinema", "felsefe")),
    ("aylin", "Aylin Kaya", "Ankara", date(1988, 7, 2), ("ulasim",)),
    ("baris", "Barış Demir", "İzmir", date(1979, 11, 23), ("ulasim",)),
    ("ceren", "Ceren Aksoy", "İstanbul", date(1991, 1, 9), ("ulasim", "bisiklet")),
    ("ilker", "İlker Şahin", "Bursa", date(1969, 5, 30), ("parklar",)),
    ("hale", "Hale Koç", "Ankara", date(1984, 9, 17), ("bisiklet",)),
    ("emre", "Emre Arslan", "İstanbul", date(2002, 2, 28), ("kent",)),
    ("kaba_kul", "Kadir Bal", "İzmir", date(1999, 12, 1), ()),
]

POOL_NAMES = [
    "deniz", "elif", "ferhat", "gizem", "hakan", "irem", "kaan", "leyla", "mert", "nazli",
    "okan", "pinar", "rana", "selin", "tolga", "umut", "vedat", "yasemin", "zeynep", "burak",
    "cansu", "dogan", "ece", "fatih", "gulsen", "harun", "ipek", "kerem", "melis", "nevzat",
]
POOL_SURNAMES = [
    "Aydın", "Çelik", "Öztürk", "Yılmaz", "Kılıç", "Doğan", "Aslan", "Çetin", "Kara", "Koç",
    "Kurt", "Özdemir", "Şimşek", "Polat", "Erdoğan", "Güneş", "Yıldırım", "Tekin", "Bulut", "Avcı",
]
# Öneri açan tohum hesaplarının seçmen kapsamına üyeliği (R5) rastgeleliğe bırakılmaz.
POOL_EXTRA_INTERESTS = {"leyla": ("sinema",), "nazli": ("sinema",), "selin": ("felsefe",)}
# Tohum kullanıcılarının kimliği takma addan türetilir: Gölge kimlikleri, oy takma kimlikleri ve
# defter kayıtları her tohumda aynı çıkar (demo iki çalıştırmada aynı sayıları gösterir).
SEED_NAMESPACE = uuid.UUID("6d6e7376-6572-6574-2d73-656564000001")
RAIDERS = ["mavi_kus", "sari_kedi", "yesil_at", "mor_balik", "turuncu_ari"]

# 90 dolgu başlığın her biri ayrı bir soru; aynı başlık listede iki kez görünmez.
MAHZEN_PROMPTS = [
    "Bir ağaç ormanda devrilirse ve kimse duymazsa ses çıkar mı?",
    "Theseus'un gemisi: parçaları tek tek değişen şey hâlâ aynı mıdır?",
    "Özgür irade bir yanılsama ise ceza adil olabilir mi?",
    "Bilmediğimizi bilmek bir tür bilgi midir?",
    "Dil düşünceyi mi belirler, düşünce dili mi?",
    "Sonsuz yaşam anlamı çoğaltır mı, yok eder mi?",
    "Başkasının acısını gerçekten bilebilir miyiz?",
    "Doğruyu söylemek her zaman erdem midir?",
    "Kalabalığın bilgeliği ile kalabalığın deliliği arasındaki fark nedir?",
    "Zaman akar mı, yoksa biz mi akarız?",
    "Bir makine anlamı anlayabilir mi?",
    "Mutluluk bir amaç mı, bir yan ürün mü?",
    "Güzellik bakanın gözünde midir?",
    "Adalet eşitlik midir, hakkaniyet mi?",
    "Hatırlamadığımız şeyler bizi hâlâ biz yapar mı?",
    "Söz veren kişi değiştiyse söz hâlâ bağlar mı?",
    "Yalnızlık seçilince özgürlük, dayatılınca ceza mıdır?",
    "Sanat eseri anlamını yapanın niyetinden mi, bakanın yorumundan mı alır?",
    "Bir şehir binalarından mı ibarettir, insanlarından mı?",
    "Hiç görmediğimiz bir rengi hayal edebilir miyiz?",
    "Sıkılmak zihnin bir uyarısı mıdır, bir hastalığı mı?",
    "Geleceğin insanlarına karşı borcumuz var mı?",
    "Bir hayvanın acısı bir insanınkinden daha mı az önemlidir?",
    "Hata yapma hakkı olmayan bir toplum özgür olabilir mi?",
    "Merak öğretilebilir mi?",
    "Rüyada verilen bir karar bizim kararımız mıdır?",
    "Affetmek unutmayı gerektirir mi?",
    "Çeviri bir metni korur mu, yeniden mi yazar?",
    "Kötülük bir eksiklik midir, kendi başına bir şey mi?",
    "Kuralları değişen oyun aynı oyun mu kalır?",
    "Anonimlik dürüstlüğü mü artırır, sorumsuzluğu mu?",
    "Bir toplum hiç kimsenin istemediği bir kararı nasıl alır?",
    "Gelenek geçmişin oyu mudur?",
    "Sessizlik bir cevap sayılır mı?",
    "Kendimize yalan söyleyebilir miyiz?",
    "Bir şeyi sevmek onu anlamayı gerektirir mi?",
    "Bilim bir yöntem midir, bir tavır mı?",
    "Sayılar keşfedilir mi, icat mı edilir?",
    "Kıskançlık adalet duygusunun bir kırıntısı mıdır?",
    "Unutulma hakkı ile hatırlama ödevi çatışırsa hangisi kazanır?",
    "Bir kitabı yarıda bırakmak ona haksızlık mıdır?",
    "Müzik bir dil midir?",
    "Cesaret korkunun yokluğu mudur, ona rağmen davranmak mı?",
    "Herkesin payını aynı oranda kesen karar adil midir?",
    "İnsan doğası diye bir şey var mı?",
    "Merhamet adaletin önüne geçebilir mi?",
    "Bir yapay zekâya kötü davranmak ahlaken yanlış olabilir mi?",
    "Tesadüf dediğimiz şey bilgisizliğimizin adı mıdır?",
    "Mülkiyet doğal bir hak mıdır?",
    "Bir fikri çürütmek onu savunanı da çürütür mü?",
    "Utanç ahlakın bekçisi midir?",
    "Çocukluğumuzdaki biz ile bugünkü biz aynı kişi miyiz?",
    "Oy vermemek de bir oy mudur?",
    "Şiir düzyazıya çevrilebilir mi?",
    "Evren bir anlam taşımak zorunda mı?",
    "Bir sırrı saklamak yalan söylemek midir?",
    "Yavaşlık bir erdem olabilir mi?",
    "Bir şehrin gecesi gündüzünden daha mı dürüsttür?",
    "Mükemmel bir dünya sıkıcı olur muydu?",
    "Tartışmayı kazanmak haklı olmak mıdır?",
    "Bir eşya ne zaman çöpe dönüşür?",
    "Nostalji geçmişe mi özlemdir, gençliğe mi?",
    "Bilgiye erişmek onu bilmek demek mi?",
    "Kuralı çiğnemek hangi durumda kurala sadakattir?",
    "Bir hikâyenin sonu başını değiştirir mi?",
    "Başkası adına karar vermek ne zaman meşrudur?",
    "Kura adil bir seçim yöntemi midir?",
    "Kimliğimizi seçer miyiz, yoksa bize mi verilir?",
    "Sınırsız seçenek özgürlük müdür, yük mü?",
    "Sınırlar haritada mı çizilir, akılda mı?",
    "İyi niyet kötü sonucu hafifletir mi?",
    "Bir melodinin sahibi olabilir mi?",
    "Gülmek bir itiraz biçimi midir?",
    "Eski bir mektubu okumak yazarının mahremiyetini çiğner mi?",
    "Toplu taşımada telefonla konuşmak kaba mıdır?",
    "Uyku ölümün provası mıdır?",
    "Herkesin bildiği yalan hâlâ yalan mıdır?",
    "Sabır bir tür teslimiyet midir?",
    "Kendi seçmediğimiz bir mirastan sorumlu muyuz?",
    "Sonsuz bir kütüphanede kaybolmak mümkün mü?",
    "Sokak kedileri kimindir?",
    "Bir tartışmada son sözü söyleyen mi kazanır?",
    "Tanımadığımız birine güvenmek akıl mıdır, umut mu?",
    "Bir fotoğraf anı korur mu, onun yerine mi geçer?",
    "Hiç değişmeyen bir fikir ölü müdür?",
    "Hız bizi özgürleştirir mi, köleleştirir mi?",
    "Geri alınabilen bir karar gerçekten karar mıdır?",
    "Boş bir sayfa korkutucu mudur, davetkâr mı?",
    "Hiç kimse okumazsa yazmanın anlamı var mı?",
    "Bir şehirde kaybolmak onu tanımanın ilk adımı mıdır?",
]
MAHZEN_OPENERS = [
    "Kısa bir cevap arıyorum ama sanırım yok.",
    "Dün gece aklıma takıldı, yazmadan duramadım.",
    "Kimse adımı bilmediği için rahatça sorabiliyorum.",
    "Meydan'da sorsam oylamaya döner; burada sadece konuşalım.",
    "İki tarafı da ikna edici buluyorum.",
    "Cevabınız ne olursa olsun gerekçesini merak ediyorum.",
    "Bir arkadaşla tartıştık, anlaşamadık.",
    "Belki saçma bir soru, ama saçma sorular da cevap ister.",
    "Bu başlık da birkaç güne kalmaz, biliyorum.",
]
MAHZEN_REPLIES = [
    "Soru yanlış sorulmuş olabilir.", "Tanımları netleştirmeden ilerleyemeyiz.",
    "Bence cevap bağlama bağlı.", "Kant burada itiraz ederdi.", "Hume'u hatırlayalım.",
    "Sezgim hayır diyor ama gerekçem yok.", "Bu bir kategori hatası.",
    "Karşı örnek: rüyalar.", "Pratikte fark etmez, teoride çok şey değişir.",
]
# Birkaç dolgu başlıkta genel yanıtların yerine gerçek bir tartışma: dolgu sırası → yanıtlar.
# "op" başlığı açan kişidir; metindeki "{n}" n. mesaja (0 = açılış) >>N referansı olur.
MAHZEN_DISCUSSIONS: dict[int, list[tuple[str, str]]] = {
    1: [
        ("ferhat", "Aynıdır. Gemi parçalarından değil, yaptığı yolculuktan ibaret."),
        ("umut", ("{1} O zaman sökülen eski parçalarla ikinci bir gemi yapılırsa hangisi "
                  "Theseus'un?")),
        ("op", ("{2} İkisi de değil bence. Soru, bir şeye ad vermenin bir uzlaşma olduğunu "
                "gösteriyor sadece.")),
        ("ferhat", ("Bu forum da öyle: kuralları tek tek oylanarak değişiyor. Bir yıl sonra "
                    "aynı forum mu olacak?")),
    ],
    30: [
        ("irem", ("İkisini birden. Burada yazdığımı Meydan'da yazmazdım, ama burada yazdığım "
                  "daha doğru.")),
        ("kaan", "{1} Daha doğru mu, daha rahat mı? Rahatlık doğruluk değil."),
        ("op", ("Gölge kimliği her başlıkta değişiyor; kimse itibar biriktiremiyor. Kaybedecek "
                "itibar yoksa kazanacak da yok.")),
        ("yasemin", ("{3} İfşa oylaması var ama. Her an adımın açılabileceğini bilmek beni "
                     "dikkatli yazdırıyor.")),
        ("irem", "{4} O zaman bu anonimlik değil, ertelenmiş imza."),
    ],
    52: [
        ("dogan", "Oy vermemek, karar verme işini oy verenlere bırakmaktır. Bu da bir tercih."),
        ("op", "{1} Tercih ama oy değil. Oy bir şey söyler; sessizlik yorumlanmayı bekler."),
        ("ece", "Havale bunun için var. Karar vermek istemeyen, güvendiği birine bırakır."),
        ("nevzat", ("{3} Havale sessizliğin kibar hâli bence. Oyunu devrediyorsun, "
                    "sorumluluğunu değil.")),
        ("op", ("{4} Onu da devrediyorsun. Havaleni geri almadığın her hafta onu yeniden "
                "onaylamış oluyorsun.")),
    ],
    80: [
        ("vedat", "Herkesin, yani kimsenin. Mama koyan çok, veterinere götüren az."),
        ("op", ("{1} Götüren var aslında; faturayı kimse paylaşmak istemiyor. Bizim sokakta "
                "bir teyze tek başına ödüyor.")),
        ("melis", "Mahalle ortak bir kasa açsa? Asıl zor olan kasayı kimin tutacağı."),
        ("gulsen", ("{3} Kasa açılırsa bu sefer hangi sokağın kedisi kimin payından beslenecek "
                    "diye tartışırız.")),
        ("op", "Yine de sahipsiz demeyi bırakalım. Sahibi mahalle."),
    ],
}

# Mahzen'in doğası: Meydan'da içerik kuralları ve silme oylaması var, Mahzen'de yok. Anonim,
# denetimsiz bir başlık yalnızca aşağı düşüp çürüyerek kaybolur. Şiir kullanıcının verdiği
# metindir; değiştirilmeden, olduğu gibi durur.
KOYLULER_BASLIK = "Köylüleri niçin öldürmeliyiz?"
KOYLULER_SIIR = """Köylüleri niçin öldürmeliyiz?

Çünkü onlar ağır kanlı adamlardır
Değişen bir dünyaya karşı
Kerpiç duvarlar gibi katı
Çakır dikenleri gibi susuz
Kayıtsızca direnerek yaşarlar.
Aptal, kaba ve kurnazdırlar.
İnanarak ve kolayca yalan söylerler.
Paraları olsa da
Yoksul görünmek gibi bir hünerleri vardır.
Her şeyi hafife alır ve herkese söverler.
Yağmuru, rüzgarı ve güneşi
Bir gün olsun ekinleri akıllarına gelmeden
Düşünemezler…
Ve birbirlerinin sınırlarını sürerek
Topraklarını büyütmeye çalışırlar.

Köylüleri niçin öldürmeliyiz?

Çünkü onlar karılarını döverler
Seslerinin tonu yumuşak değildir
Dışarda ezildikçe içerde zulüm kesilirler.
Gazete okumaz ve haksızlığa
Ancak kendileri uğrarlarsa karşı çıkarlar.
Adım başı pınar olsa da köylerinde
Temiz giyinmez ve her zaman
Bir karış sakalla gezerler.
Çocuklarını iyi yetiştiremezler
Evlerinde kitap, müzik ve resim yoktur.
Bir gün olsun dişlerini fırçalamaz
Ve şapkalarını ancak yatarken çıkarırlar.

Köylüleri niçin öldürmeliyiz?

Çünkü onlar köpekleri boğuşunca kavga ederler.
Birbirlerinin evlerine ancak
Ölümlerde ve düğünlerde giderler.
Şarkı söylemekten ve kederlenmekten utanırlar
Gülmek ayıp eğlenmek zayıflıktır
Ancak rakı içtiklerinde duygulanır ve ağlarlar.
Binlerce yılın kalın kabuğu altında
Yürekleri bir gaz lambası kadar kalmıştır.
Aldanmak korkusu içinde
Sürekli birbirlerini aldatırlar.
Bir yere birlikte gitmeleri gerekirse
Karılarından en az on adım önde yürürler
Ve bir erkeklik işareti olarak
Onları herkesin ortasında döverler.

Köylüleri niçin öldürmeliyiz?

Çünkü onlar yanlış partilere oy verirler
Kendilerinden olanlarla alay edip
Tuhaf bir şekilde başkalarına inanırlar.
Devlet, tapu dairesi, banka borcu ve hastanedir
Devletten korkar ve en çok ona hile yaparlar.
Yiğittirler askerde subay dövecek kadar
Ama bir memur karşısında -bu da tuhaftır-
Ezim ezim ezilirler.
Enflasyon denince buğday ve gübre fiyatlarını bilirler
Cami duvarı, kahve ya da bir ağaç gövdesine yaslanıp
On bir ay gökyüzünden bereket beklerler.
Dindardırlar ahret korkusu içinde
Ama bir kadının topuklarından
Memelerini görecek kadar bıçkındırlar
Harmanı kaldırdıktan sonra yılda bir kez
Şehre giderler!

Köylüleri niçin öldürmeliyiz?

Çünkü onlar otobüslerde ayaklarını çıkarırlar
Ayak ve ağız kokusu içinde kurulup koltuklara
Herkesi bunalta bunalta, yüksek perdeden
Kızlarının talihsizliğini
ve hayırsız oğullarını anlatırlar.
Yoksulluktan kıvrandıkları halde, şükür içinde
Bunun, Tanrının bir lutfu olduğuna inanırlar.
Ve önemsiz bir şeyden söz eder gibi, her fırsatta
Gizli bir övünçle, uzak şehirdeki
Zengin bir akrabalarından söz ederler.
Kibardırlar lokantada yemek yemeyi bilecek kadar
Ama sokağa çıkar çıkmaz sümküre sümküre
Yollara tükürürler…
Ve sonra şaşarak temizliğine ve düzenine
Şehirde yaşamanın iyiliğinden konuşurlar.

Köylüleri niçin öldürmeliyiz?

Çünkü onlar ilk akşamdan uyurlar.
Yarı gecelerde yıldızlara bakarak
Başka dünyaları düşünmek gibi bir tutkuları yoktur.
Gökyüzünü baharda yağmur yağarsa
Ve yaz güneşleri ekinlerini yetirirse severler.
Hayal güçleri kıttır ve hiçbir yeniliğe
-Bu verimi yüksek bir tohum bile olsa-
Sonuçlarını görmeden inanmazlar.
Dünyanın gelişimine bir katkıları yoktur.
Mülk düşkünüdürler amansız derecede
Bir ülkenin geleceği
Küçücük topraklarının ipoteği altındadır.
Ve birer kaya parçası gibi dururlar su geçirmeden
Zamanın derin ırmakları önünde…

KÖYLÜLERİ, SÖYLEYİN NASIL
NASIL KURTARALIM?"""
KOYLULER_YANITLAR = [
    ("harun", ("Başlığı görünce kapatacaktım. Sonuna kadar okuyun; son iki dizede soru "
               "değişiyor.")),
    ("ipek", ("{0} Meydan'da bu başlığa ilk gün silme önerisi gelirdi. Burada silme yok: "
              "ya yukarıda kalır ya aşağıda çürür.")),
    ("op", ("{2} Silinsin diye değil, okunsun diye koydum. Başlığına bakıp hüküm veren, "
            "şiirin kimi konuştuğunu kaçırıyor.")),
    ("kerem", "Kimi konuşuyor peki? Köylüyü mü, ona tepeden bakanı mı?"),
    ("nazli", ("{4} Bence ona tepeden bakanı. Liste boyunca öldürmeyi soruyor, sonunda "
               "kurtarmayı; asıl mesele bu dönüş.")),
    ("melis", ("Bunu Meydan'da kendi adımla paylaşır mıydım? Sanmıyorum. Burada "
               "paylaşılabilmesi iyi mi kötü mü, karar veremedim.")),
]


def _t(days: float = 0, hours: float = 0, minutes: float = 0) -> datetime:
    return SEED_NOW - timedelta(days=days, hours=hours, minutes=minutes)


@dataclass
class World:
    users: dict[str, User] = field(default_factory=dict)
    pool: list[str] = field(default_factory=list)
    ids: dict[str, int] = field(default_factory=dict)
    steps: list[tuple[datetime, int, Callable[[Ctx], None]]] = field(default_factory=list)

    def at(self, when: datetime, fn: Callable[[Ctx], None]) -> None:
        self.steps.append((when, len(self.steps), fn))

    def run(self, ctx: Ctx) -> None:
        for when, _, fn in sorted(self.steps, key=lambda s: (s[0], s[1])):
            fn(ctx.at(when))
        self.steps.clear()


# --- zaman çizelgesi yapı taşları ----------------------------------------------------------------


def _user(c: Ctx, w: World, nickname: str, full_name: str, city: str, birth: date,
          interests: tuple[str, ...] = (), last_login: datetime | None = None) -> None:
    user = auth.create_verified_user(
        c, user_id=str(uuid.uuid5(SEED_NAMESPACE, nickname)),
        nickname=nickname, full_name=full_name, email=f"{nickname}@mesveret.test",
        password=DEMO_PASSWORD, birth_date=birth, city=city, district="Merkez", address_line="",
    )
    for area in interests:
        ontology.join_interest(c, user, area)
    user.last_login_at = last_login or _t(days=1 + len(nickname) % 5)
    user.cellar_warned_at = c.now
    c.db.commit()
    w.users[nickname] = user


def _topic(w: World, key: str, author: str, title: str, body: str, area: str, scope: str,
           when: datetime, parent: str | None = None) -> None:
    def open_(c: Ctx) -> None:
        inp = ProposalInput(type="ALT_KONU" if parent else "KONU", title=title, body=body,
                            area_id=area, scope_id=scope,
                            parent_topic_id=w.ids[parent] if parent else None)
        w.ids[f"p:{key}"] = proposals.open_proposal(c, w.users[author], inp).id

    def accept(c: Ctx) -> None:
        p = c.db.get(Proposal, w.ids[f"p:{key}"])
        proposals.accept(c, p)
        c.commit()
        w.ids[key] = c.db.execute(
            select(Topic.id).where(Topic.accepted_proposal_id == p.id)
        ).scalar_one()

    w.at(when, open_)
    w.at(when + timedelta(hours=24), accept)


def _msg(w: World, key: str, who: str, topic_key: str, text: str, when: datetime,
         reply_to: str | None = None) -> None:
    def run(c: Ctx) -> None:
        msg = topics.post_message(c, w.users[who], w.ids[topic_key], text,
                                  w.ids[reply_to] if reply_to else None)
        w.ids[key] = msg.id

    w.at(when, run)


def _queued_by_objection(w: World, key: str, author: str, inp: ProposalInput, opened: datetime,
                         objectors: list[str]) -> None:
    def open_(c: Ctx) -> None:
        w.ids[key] = proposals.open_proposal(c, w.users[author], inp).id

    w.at(opened, open_)
    for i, nick in enumerate(objectors):
        w.at(opened + timedelta(hours=2 + i),
             lambda c, nick=nick: proposals.object_to(c, w.users[nick], w.ids[key]))

    def check(c: Ctx) -> None:
        status = c.db.get(Proposal, w.ids[key]).status
        if status != "QUEUED":
            raise RuntimeError(f"Tohum: '{key}' itirazla yavaş şeride geçmedi ({status}).")

    w.at(opened + timedelta(hours=2 + len(objectors)), check)


# --- bölümler -------------------------------------------------------------------------------------


def _people(w: World) -> None:
    for i, (nick, name, city, birth, interests) in enumerate(NAMED):
        w.at(_t(days=420 - i), lambda c, a=(nick, name, city, birth, interests):
             _user(c, w, *a))
    areas = [a[0] for a in AREAS]
    for i, nick in enumerate(POOL_NAMES):
        birth = date(1960 + (i * 7) % 45, 1 + i % 12, 1 + (i * 3) % 27)
        interests = tuple(sorted({areas[i % len(areas)], areas[(i * 5 + 3) % len(areas)],
                                  *POOL_EXTRA_INTERESTS.get(nick, ())}))
        name = f"{nick.title()} {POOL_SURNAMES[i % len(POOL_SURNAMES)]}"
        args = (nick, name, CITIES[i % len(CITIES)], birth, interests)
        w.at(_t(days=400 - i * 3), lambda c, a=args: _user(c, w, *a))
        w.pool.append(nick)


def _delegate(c: Ctx, giver: User, target: str, area_id: str | None) -> None:
    """Tohumdaki havaleler kabul edilmiş başlar: istek ve kabul aynı anda (Hâtif kendiliğinden)."""
    row = delegation.request_delegation(c, giver, target, area_id)
    if row.status == "PENDING":
        delegation.accept_request(c, c.db.get(User, row.target_id), row.id)


def _delegations(w: World) -> None:
    def run(c: Ctx) -> None:
        u = w.users
        _delegate(c, u["aylin"], "baris", None)
        _delegate(c, u["baris"], "ceren", "ulasim")
        for nick in ("gizem", "hakan"):
            _delegate(c, u[nick], oracle.ORACLE_NICKNAME, "kultur")
        for nick in ("deniz", "elif", "ferhat", "irem", "kaan"):
            _delegate(c, u[nick], "selin", "felsefe")
        c.commit()

    w.at(_t(days=30), run)

    # Havale kabulü demosu: aylin'in Ulaşım havalesini mert reddetti (aylin'in Havale sayfasında
    # "reddedildi"); elif'in aylin'e verdiği Kent havalesi bekliyor (aylin girişte Kabul et /
    # Reddet görür). İkisi de grafa girmez, oylamaları etkilemez.
    def rejected(c: Ctx) -> None:
        row = delegation.request_delegation(c, w.users["aylin"], "mert", "ulasim")
        w.ids["havale_red"] = row.id

    w.at(_t(days=3), rejected)
    w.at(_t(days=2), lambda c: delegation.reject_request(c, w.users["mert"], w.ids["havale_red"]))

    def pending(c: Ctx) -> None:
        w.ids["havale_bekliyor"] = delegation.request_delegation(c, w.users["elif"], "aylin",
                                                                 "kent").id

    w.at(_t(days=1), pending)


def _background(w: World) -> None:
    _topic(w, "felsefe", "selin", "Felsefe okuma grubu",
           "Her hafta bir diyalog okuyup tartışalım; ilk metin Menon.", "felsefe", "genel",
           _t(days=27))
    _topic(w, "film", "leyla", "Film günleri",
           "Her ayın ilk cuması bir film izleyip ardından konuşalım.", "sinema", "ilgi:sinema",
           _t(days=26))
    _topic(w, "siir", "okan", "Şiir akşamları",
           "Ayda bir kez herkes sevdiği bir şiiri okusun.", "siir", "genel", _t(days=25))
    _msg(w, "m_felsefe", "tolga", "felsefe", "Menon'daki köle çocuk sahnesi hâlâ tartışmalı.",
         _t(days=25, hours=2))
    _msg(w, "m_felsefe2", "selin", "felsefe",
         "Sokrates çocuğa gerçekten hatırlatıyor mu, yoksa cevabı sorularının içine mi "
         "saklıyor? İlk buluşmada bunu konuşalım.", _t(days=24, hours=20), reply_to="m_felsefe")
    _msg(w, "m_film1", "leyla", "film", "İlk film için Tarkovski'nin Solaris'ini öneriyorum.",
         _t(days=24))
    _msg(w, "m_film2", "mert", "film", "Solaris uzun; ilk buluşma için daha kısa bir film seçelim.",
         _t(days=24, hours=-2), reply_to="m_film1")
    _msg(w, "m_felsefe3", "deniz", "felsefe",
         "Menon'dan sonra Euthyphron'u öneririm: kısa ve hâlâ cevapsız bir sorusu var.",
         _t(days=23, hours=22))
    _msg(w, "m_film4", "nazli", "film",
         "Kısa bir başlangıç için Dekalog'un ilk bölümü olabilir; bir saat sürer, konuşacak çok "
         "şey bırakır.", _t(days=23, hours=20), reply_to="m_film2")
    _msg(w, "m_felsefe4", "elif", "felsefe",
         "Bir şey tanrılar sevdiği için mi iyidir, iyi olduğu için mi sevilir? Buradaki "
         "oylamalara da uyuyor: kabul edildiği için mi doğru, doğru olduğu için mi kabul edildi?",
         _t(days=23, hours=19), reply_to="m_felsefe3")
    _msg(w, "m_film5", "leyla", "film", "Dekalog'a varım. Solaris'i kış aylarına saklayalım.",
         _t(days=23, hours=18), reply_to="m_film4")
    _msg(w, "m_felsefe5", "kaan", "felsefe",
         "Buluşmalar çevrim içi de olabilir mi? İzmir'den katılmak istiyorum.",
         _t(days=23, hours=16))
    _msg(w, "m_felsefe6", "selin", "felsefe",
         "Olur; her buluşmanın özetini de buraya yazarım.", _t(days=23, hours=14),
         reply_to="m_felsefe5")
    _msg(w, "m_siir", "pinar", "siir", "Ben Nâzım'dan başlarım.", _t(days=23))
    _msg(w, "m_siir2", "okan", "siir", "Ben Cemal Süreya getireceğim; kısa ama yoğun.",
         _t(days=22, hours=20), reply_to="m_siir")
    _msg(w, "m_siir3", "rana", "siir", "Çeviri şiir de okunabilir mi? Szymborska'yı çok seviyorum.",
         _t(days=22, hours=14))
    _msg(w, "m_siir4", "okan", "siir", "Tabii; aslını da yanında okursak daha iyi olur.",
         _t(days=22, hours=2), reply_to="m_siir3")
    _msg(w, "m_film3", "ayse", "film", "Salon için perşembe akşamı uygun.", _t(days=22))
    w.at(_t(days=21), lambda c: topics.edit_own_message(
        c, w.users["ayse"], w.ids["m_film3"], "Salon için cuma akşamı uygun; perşembe dolu."))
    _msg(w, "m_film6", "hakan", "film",
         "Gösterimlerde Türkçe altyazılı kopya kullanalım; altyazı yüzünden gelmeyen olmasın.",
         _t(days=21, hours=-4))
    _msg(w, "m_siir5", "leyla", "siir",
         "Okunan şiirleri bir listede toplayalım; yıl sonunda küçük bir seçki olur.",
         _t(days=21, hours=-6))
    _topic(w, "belgesel-ayi", "nazli", "Belgesel ayı",
           "Kasım ayını belgesellere ayıralım; her hafta bir belgesel.", "belgesel",
           "ilgi:sinema", _t(days=20), parent="film")
    _topic(w, "pazar", "emre", "İstanbul semt pazarları",
           "Semt pazarlarının saatleri mahalleye göre ayarlansın.", "kent", "sehir:istanbul",
           _t(days=19))
    _msg(w, "m_belgesel1", "nazli", "belgesel-ayi",
         "İlk hafta için doğa belgeseli yerine bir şehir belgeseli öneriyorum.",
         _t(days=18, hours=14))
    _msg(w, "m_belgesel2", "mert", "belgesel-ayi",
         "Her gösterimden sonra yarım saat konuşalım; sorusunu önceden buraya yazalım.",
         _t(days=18), reply_to="m_belgesel1")
    _msg(w, "m_pazar", "ceren", "pazar", "Kadıköy pazarı akşam da açık olabilir.", _t(days=17))
    _msg(w, "m_belgesel3", "ayse", "belgesel-ayi",
         "Salon cuma akşamları bizde; belgesel ayında da aynı saat olsun.", _t(days=17, hours=-2))
    _msg(w, "m_pazar2", "emre", "pazar",
         "Akşam pazarı çalışanlar için iyi olur; ama sabah kurulan tezgâhın akşama kadar durması "
         "zor.", _t(days=16, hours=20), reply_to="m_pazar")
    _msg(w, "m_pazar3", "rana", "pazar",
         "Hafta içi bir gün yalnızca akşam kurulan bir pazar denenebilir.", _t(days=16, hours=14))
    _msg(w, "m_pazar4", "ceren", "pazar",
         "Önce bir mahallede deneyelim; tutarsa öneri olarak açarım.", _t(days=16),
         reply_to="m_pazar3")


def _scenario_deletion(w: World) -> None:
    """4. Silme: iki gerekçeli silme (IK-2 %60 → ret, IK-1 %67 → kabul) ve kendi mesajını silme."""
    _topic(w, "bisiklet", "hale", "Bisiklet yolları",
           "Ana caddelere korunaklı bisiklet yolu yapılsın.", "bisiklet", "genel", _t(days=16))
    _msg(w, "m_bis1", "ceren", "bisiklet", "Önce okul çevrelerinden başlayalım.", _t(days=14))
    _msg(w, "troll", "kaba_kul", "bisiklet",
         "Bu konuyu açanların hepsi cahil; bisikletliler trafiğin baş belası.", _t(days=13))
    _msg(w, "m_bis2", "hale", "bisiklet", "Eleştiri olur, hakaret olmaz.",
         _t(days=13, hours=-1))
    _msg(w, "spam", "kaba_kul", "bisiklet",
         "Kaçırmayın! Katlanır bisiklette büyük indirim kampanyası, sipariş için profilime tıklayın.",
         _t(days=12))
    _msg(w, "m_kendi", "ceren", "bisiklet",
         "Gönüllü olmak isteyenler beni arasın: telefonum 0532 000 00 00.", _t(days=11))

    def delete(key: str, who: str, target: str, when: datetime, body: str, rules=(), excerpt=""):
        w.at(when, lambda c: w.ids.__setitem__(key, proposals.open_proposal(
            c, w.users[who], ProposalInput(
                type="SILME", target_message_id=w.ids[target], body=body,
                content_rules=list(rules), excerpt=excerpt,
            )).id))

    delete("silme_60", "hale", "troll", _t(days=8, hours=2),
           "Katılımcılara hakaret ediyor.", ["IK-2"], "Bu konuyu açanların hepsi cahil")
    delete("silme_67", "hale", "spam", _t(days=8, hours=1),
           "Tartışmayla ilgisi olmayan reklam.", ["IK-1"],
           "büyük indirim kampanyası, sipariş için profilime tıklayın")
    delete("silme_kendi", "ceren", "m_kendi", _t(days=8, minutes=30),
           "Telefon numaramı yanlışlıkla paylaştım; mesajımın kaldırılmasını istiyorum.")


def _scenario_closure(w: World) -> None:
    """5. Kapanış."""
    _topic(w, "parklar", "zeynep", "Parkların kapanış saati",
           "Mahalle parkları gece kaçta kapanmalı?", "parklar", "genel", _t(days=12))
    _msg(w, "m_park1", "burak", "parklar", "22:00 hem güvenli hem yeterli.", _t(days=10))
    _msg(w, "m_park2", "ilker", "parklar", "Yazın gece yarısına kadar açık kalmalı.",
         _t(days=10, hours=-3))
    _msg(w, "m_park3", "zeynep", "parklar",
         "Aydınlatma yetersizse saat tartışması anlamsız; önce ışıklandırma.",
         _t(days=9, hours=20))
    _msg(w, "m_park4", "burak", "parklar", "Gece yarısına kadar açık kalacaksa bekçi de gerekir.",
         _t(days=9, hours=14), reply_to="m_park2")
    _msg(w, "m_park5", "ilker", "parklar",
         "Bekçi yerine iyi aydınlatma yeter; asıl tehlikeli olan boş kalan park.",
         _t(days=9, hours=12), reply_to="m_park4")
    opened = _t(days=8, hours=12)
    w.at(opened, lambda c: w.ids.__setitem__("kapanis", proposals.open_proposal(
        c, w.users["zeynep"], ProposalInput(
            type="KAPANIS", target_topic_id=w.ids["parklar"],
            body="Parklar her gün 20:00'de kapansın.",
        )).id))
    w.at(opened + timedelta(hours=4), lambda c: proposals.add_rival(
        c, w.users["burak"], w.ids["kapanis"], "Parklar her gün 22:00'de kapansın."))
    w.at(opened + timedelta(hours=12), lambda c: proposals.add_rival(
        c, w.users["ilker"], w.ids["kapanis"], "Parklar yazın 24:00'te, kışın 22:00'de kapansın."))

    def end(c: Ctx) -> None:
        proposals.end_rival_period(c, c.db.get(Proposal, w.ids["kapanis"]))
        c.commit()

    w.at(opened + timedelta(hours=48), end)


def _scenarios_voting(w: World) -> None:
    """2. Havale zinciri, 3. Yönetmelik, 7. Baskın, 8. Hâtif için Karar Saati kuyruğu."""
    _queued_by_objection(w, "metro", "umut", ProposalInput(
        type="KONU", title="Gece metro seferleri",
        body="Metro hafta sonları gece de çalışsın; sefer aralıkları 20 dakika olsun.",
        area_id="ulasim", scope_id="genel",
    ), _t(days=8, hours=8), ["vedat", "yasemin", "cansu"])
    w.at(_t(days=8), lambda c: w.ids.__setitem__("yonetmelik_60", proposals.open_proposal(
        c, w.users["dogan"], ProposalInput(
            type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45},
            body="Reddedilen önerilerin hemen geri gelmesini önlemek için süre uzasın.",
        )).id))
    w.at(_t(days=7, hours=22), lambda c: w.ids.__setitem__("yonetmelik_67", proposals.open_proposal(
        c, w.users["ece"], ProposalInput(
            type="YONETMELIK", article_key="sessiz_onay_suresi", new_value={"saat": 36},
            body="Hafta sonu açılan önerileri kaçırmamak için sessiz onay 36 saat olsun.",
        )).id))
    _queued_by_objection(w, "baskin", "emre", ProposalInput(
        type="KONU", title="Parklar sabaha kadar açık kalsın",
        body="Mahalle parkları gece kapanmasın; parklar sabaha kadar açık kalsın.",
        area_id="parklar", scope_id="genel",
    ), _t(days=7, hours=18), ["fatih", "gulsen", "harun"])
    _queued_by_objection(w, "hatif", "ipek", ProposalInput(
        type="KONU", title="Belgesel film gösterimleri",
        body="Her ay bir belgesel izleyip ardından belgesel üzerine konuşalım.",
        area_id="edebiyat", scope_id="genel",
    ), _t(days=7, hours=12), ["kerem", "melis", "nevzat"])
    # 10. Eşzamanlı çoğunluk: orantısız etkilenen İstanbul ayrıca oylar; eşit kesinti tek oylama.
    w.at(_t(days=7, hours=10), lambda c: w.ids.__setitem__("pay_yarisi", proposals.open_proposal(
        c, w.users["hale"], ProposalInput(
            type="KONU", title="İstanbul payının yarısı Ankara'ya",
            body="Ankara'daki etkinlikler daha kalabalık; etkinlik bütçesinde İstanbul payının "
                 "yarısı Ankara'ya aktarılsın.",
            area_id="kent", scope_id="genel", resource_ids=["butce"],
            share_effect={"butce": {"sehir:istanbul": 2000, "sehir:ankara": 8000}},
        )).id))
    _queued_by_objection(w, "kesinti", "dogan", ProposalInput(
        type="KONU", title="Tüm şehirlerin payında %10 kesinti",
        body="Etkinlik bütçesinde her şehrin payı %10 azaltılsın; artan kısım yedekte kalsın.",
        area_id="kent", scope_id="genel", resource_ids=["butce"],
        share_effect={"butce": {"sehir:istanbul": 3600, "sehir:ankara": 5400,
                                "sehir:izmir": 4500, "sehir:bursa": 4500}},
    ), _t(days=7, hours=6), ["okan", "pinar", "rana"])
    # 14. Pay çakışması: aynı bütçe, kesintiden sonraki numara. Kabul oyu alır ama kesinti önce
    #     uygulandığı için hedefleri (4.000 → 4.200 …) geçersizdir.
    _queued_by_objection(w, "artis", "ece", ProposalInput(
        type="KONU", title="Tüm şehirlerin payında %5 artış",
        body="Etkinlik bütçesinde her şehrin payı %5 artsın; yedekteki kısım kullanılsın.",
        area_id="kent", scope_id="genel", resource_ids=["butce"],
        share_effect={"butce": {"sehir:istanbul": 4200, "sehir:ankara": 6300,
                                "sehir:izmir": 5250, "sehir:bursa": 5250}},
    ), _t(days=7, hours=5), ["tolga", "umut", "yasemin"])


def _cellar_thread(c: Ctx, w: World, author: str, title: str, text: str,
                   replies: list[tuple[str, str]], first: int, gap: int) -> int:
    """Başlık ve yanıtları: ilk yanıt ``first`` dakika sonra, sonrakiler ``gap`` dakika arayla.

    Yanıtta "op" başlığı açandır; "{n}" n. mesaja (0 = açılış) >>N referansına dönüşür.
    """
    t = cellar.create_thread(c, w.users[author], title, text, acknowledge=True)
    op = c.db.execute(select(CellarPost.id).where(CellarPost.thread_id == t.id)).scalar_one()
    refs = [f">>{op}"]
    for j, (nick, body) in enumerate(replies):
        post = cellar.reply(c.at(c.now + timedelta(minutes=first + j * gap)),
                            w.users[author if nick == "op" else nick], t.id,
                            body.format(*refs), acknowledge=True)
        refs.append(f">>{post.id}")
    return t.id


def _cellar(w: World) -> None:
    """6. Mahzen: 90 dolgu başlık (çürüme görünsün), şiir başlığı ve ifşa oylaması açık demo
    başlığı. Dolgu başlıklar 1,5 saat arayla açılır; yanıtları bir sonraki başlıktan önce biter,
    sıra açılış sırasıdır."""
    for i in range(90):
        when = _t(days=6, hours=-i * 1.5)
        author = w.pool[(i * 7) % len(w.pool)]
        prompt = MAHZEN_PROMPTS[i]
        text = f"{prompt} {MAHZEN_OPENERS[i % len(MAHZEN_OPENERS)]}"
        if i in MAHZEN_DISCUSSIONS:
            replies, first, gap = MAHZEN_DISCUSSIONS[i], 10, 12
        else:
            replies = [(w.pool[(i * 5 + j * 11 + 3) % len(w.pool)],
                        MAHZEN_REPLIES[(i + j) % len(MAHZEN_REPLIES)]) for j in range(i % 3)]
            first, gap = 40, 50
        w.at(when, lambda c, a=(author, prompt, text, replies, first, gap):
             _cellar_thread(c, w, *a))

    at = _t(hours=8)

    def demo(c: Ctx) -> None:
        u = w.users
        t = cellar.create_thread(
            c, u["ayse"], "Çoğunluk haklı olabilir mi?",
            "Bir şeyin doğru olması için çoğunluğun onu kabul etmesi yeterli mi? "
            "Oylamayla doğruya ulaşılır mı, yoksa yalnızca karara mı?", acknowledge=True)
        replies = [
            ("pinar", "Oylama doğruyu değil, birlikte yaşama biçimini belirler."),
            ("rana", "Ama bilimsel doğrular oylanmaz; kapsam önemli."),
            ("selin", "Condorcet: bireyler yarıdan fazla doğruysa çoğunluk daha da doğrudur."),
            ("tolga", "Bu varsayım bağımsızlık ister; forumlarda herkes birbirini etkiler."),
        ]
        for i, (nick, text) in enumerate(replies):
            cellar.reply(c.at(c.now + timedelta(minutes=30 * (i + 1))), u[nick], t.id, text,
                         acknowledge=True)
        w.ids["mahzen"] = t.id

    w.at(at, demo)
    # Şiir başlığı demo başlığından sonra açılır (demo No.91 kalır); son yanıtı demo başlığının
    # son yanıtından önce gelir: listede demo başlığı en üstte, şiir ikinci.
    w.at(_t(hours=7, minutes=45), lambda c: w.ids.__setitem__("koyluler", _cellar_thread(
        c, w, "okan", KOYLULER_BASLIK, KOYLULER_SIIR, KOYLULER_YANITLAR, 12, 13)))
    w.at(_t(hours=5),lambda c: cellar.open_reveal_vote(c, w.users["ayse"], w.ids["mahzen"]))
    for nick, yes in (("pinar", True), ("rana", True), ("selin", False)):
        w.at(_t(hours=4, minutes=30), lambda c, nick=nick, yes=yes: cellar.cast_reveal_vote(
            c, w.users[nick], w.ids["mahzen"], yes))


def _raiders(w: World) -> None:
    """7. Baskın: art arda açılmış, birbirine yanıt veren beş hesap."""
    for i, nick in enumerate(RAIDERS):
        w.at(_t(hours=5, minutes=-8 * i), lambda c, nick=nick, i=i: _user(
            c, w, nick, nick.replace("_", " ").title(), "İstanbul", date(2000, 1 + i, 10),
            last_login=_t(hours=4)))
    _msg(w, "raid0", RAIDERS[0], "parklar", "Parklar sabaha kadar açık!", _t(hours=4))
    for i, nick in enumerate(RAIDERS[1:], start=1):
        _msg(w, f"raid{i}", nick, "parklar", "Kesinlikle katılıyorum!",
             _t(hours=4, minutes=-5 * i), reply_to="raid0")


def _scenario_istanbul(w: World) -> None:
    """1. İstanbul vakası: seçmen İstanbul, kaynak bölünebilir bütçe → İstanbul payına daralır."""
    w.at(_t(hours=3), lambda c: w.ids.__setitem__("istanbul", proposals.open_proposal(
        c, w.users["emre"], ProposalInput(
            type="KONU", title="Etkinlik bütçesinin tamamı İstanbul'a",
            body="İstanbul'daki etkinlikler için tüm bütçe kullanılsın.",
            area_id="kent", scope_id="sehir:istanbul", resource_ids=["butce"],
        )).id))


def _scenario_maturation(w: World) -> None:
    """9. Olgunlaşma: Genel kapsamlı yönetmelik önerisi Karar Saati'nden 10 dakika önce açılır.

    Genel olgunlaşma süresi (7 gün) dolmadığı için bu oturuma alınmaz; 7 gün dolduktan sonraki
    ilk oturuma (Pazar 11 Ekim) kayar. Oy planı yok.
    """
    w.at(_t(minutes=10), lambda c: w.ids.__setitem__("olgunlasma", proposals.open_proposal(
        c, w.users["kerem"], ProposalInput(
            type="YONETMELIK", article_key="musavir_esigi", new_value={"deger": 3},
            body="Müşavir etiketi daha erken görünsün; eşik 3 havale olsun.",
        )).id))


def _vote_plan(ctx: Ctx, w: World) -> None:
    names = w.pool
    plan: list[tuple[str, str, object]] = []

    # 2. Havale zinciri: 4 EVET + Hâtif = 5, 5 HAYIR → eşitlik; ceren (ağırlık 3) sonucu belirler.
    plan += [("metro", n, "EVET") for n in names[20:24]]
    plan += [("metro", n, "HAYIR") for n in names[24:29]]

    # 3. Yönetmelik: 29 yurttaş + Hâtif (EVET) = 30 oy.
    #    red_bekleme: 17 + 1 = 18/30 = %60 → geçemez; sessiz_onay_suresi: 19 + 1 = 20/30 → geçer.
    for i, n in enumerate(names[:29]):
        plan.append(("yonetmelik_60", n, "EVET" if i < 17 else "HAYIR"))
        plan.append(("yonetmelik_67", n, "EVET" if i < 19 else "HAYIR"))

    # 4. Silme: gerekçeli silme 2/3 ister. 29 yurttaş + Hâtif (kural karşılığı var → EVET) = 30.
    #    Hakaret: 17 + 1 = 18/30 = %60 → geçemez; reklam: 19 + 1 = 20/30 → geçer.
    #    Kendi mesajı basit çoğunluk: 6 + 1 = 7/12 (%58) → geçer (2/3 olsaydı geçemezdi).
    for i, n in enumerate(names[:29]):
        plan.append(("silme_60", n, "EVET" if i < 17 else "HAYIR"))
        plan.append(("silme_67", n, "EVET" if i < 19 else "HAYIR"))
    plan += [("silme_kendi", n, "EVET" if i < 6 else "HAYIR") for i, n in enumerate(names[:11])]

    # 5. Kapanış (onay oylaması): 22:00 metni kazanır; ilker kendi metnini onaylar.
    texts = proposals.closure_texts(ctx, ctx.db.get(Proposal, w.ids["kapanis"]))
    t20, t22, t24 = (ct.id for ct in texts)
    approvals: dict[str, list[int]] = {"zeynep": [t20, t22], "burak": [t22], "ilker": [t24]}
    approvals |= {n: [t22] for n in names[0:5]}
    approvals |= {n: [t20] for n in names[5:8]}
    approvals |= {n: [t22, t24] for n in names[8:11]}
    approvals |= {n: [t24] for n in names[11:13]}
    plan += [("kapanis", n, choice) for n, choice in approvals.items()]

    # 7. Baskın: beş yeni hesap EVET (dışlanacaklar); yurttaşlardan 1 EVET, 4 HAYIR.
    plan += [("baskin", n, "EVET") for n in RAIDERS]
    plan += [("baskin", n, "EVET" if i == 0 else "HAYIR") for i, n in enumerate(names[13:18])]

    # 8. Hâtif: yanlış alan etiketi; Hâtif (+2 havale) HAYIR. Yurttaşlar 4 EVET, 3 HAYIR.
    plan += [("hatif", n, "EVET" if i < 4 else "HAYIR") for i, n in enumerate(names[18:25])]

    # 10. Eşzamanlı çoğunluk. Genel: 15 + Hâtif = 16/25 = %64 → geçer. İstanbul'un ayrı oylaması
    #     (Hâtif şehir kapsamının üyesi değil): 2/9 = %22 → reddedilir; öneri reddedilir.
    #     Eşit kesinti orantısız değil: tek oylama, 12 + Hâtif = 13/21 → geçer.
    plan += [("pay_yarisi", n, "EVET" if i < 15 else "HAYIR") for i, n in enumerate(names[:24])]
    scoped = [("pay_yarisi", "sehir:istanbul", n, "EVET" if n in ("mert", "rana") else "HAYIR")
              for n in ("mert", "rana", "deniz", "hakan", "vedat", "cansu", "gulsen", "melis",
                        "emre")]
    plan += [("kesinti", n, "EVET" if i < 12 else "HAYIR") for i, n in enumerate(names[:20])]
    # 14. Pay çakışması: artış da 12 + Hâtif = 13/21 ile kabul oyu alır; kesinti (daha küçük
    #     numara) önce uygulandığı için çakışma nedeniyle uygulanamaz.
    plan += [("artis", n, "EVET" if i < 12 else "HAYIR") for i, n in enumerate(names[:20])]

    for key, nick, choice in plan:
        ctx.db.add(DevVotePlan(proposal_id=w.ids[key], voter_id=w.users[nick].id, choice=choice))
    for key, scope, nick, choice in scoped:
        ctx.db.add(DevVotePlan(proposal_id=w.ids[key], voter_id=w.users[nick].id, choice=choice,
                               vote_scope_id=scope))
    ctx.db.commit()


# --- giriş noktası --------------------------------------------------------------------------------


def _reset(ctx: Ctx) -> Iterator[str]:
    from mesveret.db.base import create_schema, drop_schema

    ctx.db.close()
    drop_schema()
    create_schema()
    ctx.graph.reset()
    if hasattr(ctx.graph, "ensure_constraints"):
        ctx.graph.ensure_constraints()
    yield "PostgreSQL ve Neo4j sıfırlandı."
    try:
        ctx.ledger.reset()
        yield "Defter sıfırlandı (üç düğüm)."
    except Exception as exc:  # noqa: BLE001
        yield f"UYARI: defter sıfırlanamadı ({type(exc).__name__}); eski kayıtlar kalabilir."


def run(ctx: Ctx, *, reset: bool = False) -> Iterator[str]:
    # Zamanlayıcı (API içindeki arka plan iş parçacığı) sıfırlama ve tohum kurulurken araya
    # girmesin: geçmiş tarihli öneriler adım adım kurulurken süresi "dolmuş" görünürler.
    with scheduler.exclusive(ctx.db.get_bind()):
        if reset:
            yield from _reset(ctx)
            from mesveret.db.base import get_sessionmaker

            ctx.db = get_sessionmaker()()
        elif ctx.db.execute(select(User.id).limit(1)).first():
            yield "Veritabanı boş değil; yeniden kurmak için: meşveret-dev seed --reset"
            return
        yield from _build(ctx)


def _build(ctx: Ctx) -> Iterator[str]:
    clock.reset_to(ctx.db, SEED_NOW)
    ctx.db.commit()
    ctx = ctx.at(SEED_NOW)
    base = ctx.at(_t(days=3650))
    ontology.install_base(base, AREAS, RESOURCES, cities=CITIES)
    oracle.ensure_oracle(base)
    ctx.db.merge(SchedulerState(id=1, last_tick_at=SEED_NOW))
    ctx.db.commit()

    w = World()
    _people(w)
    _delegations(w)
    _background(w)
    _scenario_deletion(w)
    _scenario_closure(w)
    _scenarios_voting(w)
    _cellar(w)
    _raiders(w)
    _scenario_istanbul(w)
    _scenario_maturation(w)
    w.run(ctx)
    w.users["ayse"].cellar_warned_at = None  # sunumda Mahzen giriş uyarısı görünsün
    _vote_plan(ctx, w)
    ctx.commit()

    yield f"Sahte saat: {SEED_NOW.astimezone(clock.ISTANBUL):%d.%m.%Y %H:%M} (İstanbul)."
    yield (f"{len(w.users) + 1} hesap (Hâtif dahil). "
           f"Tüm tohum hesaplarının şifresi: {DEMO_PASSWORD}")
    yield "Senaryo önerileri: " + ", ".join(
        f"{k}=#{w.ids[k]}" for k in ("istanbul", "metro", "yonetmelik_60", "yonetmelik_67",
                                     "silme_60", "silme_67", "silme_kendi", "kapanis", "baskin",
                                     "hatif", "pay_yarisi", "kesinti", "artis", "olgunlasma"))
    yield f"Mahzen demo başlığı: #{w.ids['mahzen']}"
    yield "Sonraki adım: README'deki senaryolar (meşveret-dev run-karar-saati)."


def scenario_ids(ctx: Ctx) -> dict[str, int]:
    """Testler ve CLI için: senaryo önerilerinin numaraları (başlıklarından)."""
    titles = {
        "istanbul": "Etkinlik bütçesinin tamamı İstanbul'a",
        "metro": "Gece metro seferleri",
        "yonetmelik_60": "Yönetmelik: Red bekleme süresi",
        "yonetmelik_67": "Yönetmelik: Sessiz onay süresi",
        "kapanis": "Kapanış: Parkların kapanış saati",
        "baskin": "Parklar sabaha kadar açık kalsın",
        "hatif": "Belgesel film gösterimleri",
        "pay_yarisi": "İstanbul payının yarısı Ankara'ya",
        "kesinti": "Tüm şehirlerin payında %10 kesinti",
        "artis": "Tüm şehirlerin payında %5 artış",
        "olgunlasma": "Yönetmelik: Müşavir eşiği",
    }
    out = {}
    for key, title in titles.items():
        pid = ctx.db.execute(select(Proposal.id).where(Proposal.title == title)).scalar()
        if pid is not None:
            out[key] = pid
    silmeler = ctx.db.execute(
        select(Proposal.id).where(Proposal.type == "SILME").order_by(Proposal.id).limit(3)
    ).scalars().all()
    out |= dict(zip(("silme_60", "silme_67", "silme_kendi"), silmeler, strict=False))
    return out
