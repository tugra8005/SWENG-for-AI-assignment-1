"""Raporun UML ve diğer diyagramları (``{{uml:ad}}`` yer tutucuları).

Her işlev bir ``uml.Diagram`` döner. İçerik koddan alınır: tablolar, sınıflar ve paket
bağımlılıkları ``sema.json``'dan (``sema.py`` üretir), commit'ler git geçmişinden. Akışlar (sıralama,
durum, etkinlik) kodun ilgili işlevleri okunarak çizildi; her birinin başında kaynağı yazılıdır.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import uml
from uml import (GREY, INK, SOFT, WASH, WHITE, Box, Canvas, action, actor, bar, box, cls,
                 component, db_icon, decision, dfd_entity, dfd_process, dfd_store, edge,
                 ellipse_point, entity, final_node, hv, node3d, note, package, sequence,
                 start_node, state, swimlanes, tree, tw, usecase, vh)

ROOT = Path(__file__).resolve().parent
SEMA = json.loads((ROOT / "sema.json").read_text(encoding="utf-8"))


def _uc_link(c: Canvas, a: Box, uc: Box, *, side: str = "r") -> None:
    """Aktör–kullanım durumu ilişkisi (yönsüz çizgi)."""
    p = (a.r + 2, a.y + 24) if side == "r" else (a.x - 2, a.y + 24)
    edge(c, [p, ellipse_point(uc, p)])


def _uc_dep(c: Canvas, src: Box, dst: Box, kind: str, *, via: list | None = None,
            lpos: tuple[float, float] | None = None) -> None:
    """«include» / «extend»: kesikli, açık uçlu ok (extend uzantıdan tabana)."""
    a = ellipse_point(src, via[0] if via else (dst.cx, dst.cy))
    b = ellipse_point(dst, via[-1] if via else (src.cx, src.cy))
    pts = [a, *(via or []), b]
    edge(c, pts, head="open", dash=True, label=f"«{kind}»", lkind="serifi", lsize=8.8, lpos=lpos)


def _gen(c: Canvas, child: Box, parent: Box, pts: list | None = None) -> None:
    edge(c, pts or [child.p("t"), parent.p("b")], head="tri")


# =====================================================================================================
# KULLANIM DURUMU DİYAGRAMLARI
# Kaynak: routers/*.py (hangi uç nokta giriş ister), services/*.py (kim yapabilir).
# =====================================================================================================


def uc_hesap() -> uml.Diagram:
    c = Canvas()
    c.rect(130, 0, 500, 420, fill="none")
    c.text(380, 18, "Meşveret · hesap, okuma ve tartışma", 11, "serifb", anchor="middle")
    left = [
        ("UC-11", "Kayıt ol, e-postayı doğrula", 60), ("UC-12", "Giriş yap", 108),
        ("UC-13", "Ön sayfayı, takvimi oku", 156), ("UC-14", "Konu, öneri, dilekçe,\nKarar Saati sonucunu oku", 210),
        ("UC-15", "Ara", 266), ("UC-16", "Defteri doğrula", 314), ("UC-17", "Kılavuzu oku", 362),
    ]
    right = [
        ("UC-18", "Profili ve adresi yönet", 62), ("UC-19", "İlgi alanına katıl, ayrıl", 110),
        ("UC-21", "Kendi mesajını düzenle", 158), ("UC-22", "Bildirimleri oku", 206),
        ("UC-20", "Tartışmaya yaz, yanıtla", 268),
    ]
    L = {code: usecase(c, 265, y, t, code=code) for code, t, y in left}
    R = {code: usecase(c, 505, y, t, code=code) for code, t, y in right}
    img = usecase(c, 505, 356, "Görsel ekle\n(alt metin zorunlu)", code="UC-23")
    _uc_dep(c, img, R["UC-20"], "extend", lpos=(548, 316))
    ziy = actor(c, 40, 150, "Ziyaretçi")
    yur = actor(c, 720, 150, "Yurttaş")
    for b in L.values():
        _uc_link(c, ziy, b)
    for b in R.values():
        _uc_link(c, yur, b, side="l")
    edge(c, [(720, 150), (720, -26), (40, -26), (40, 150)], head="tri")
    c.text(380, -31, "Yurttaş, ziyaretçinin yapabildiği her şeyi yapar (genelleme)", 9, "serifi",
           anchor="middle", fill=SOFT)
    led = actor(c, 380, 450, "Defter", system=True, stereo="sistem")
    edge(c, [led.p("t", 0.3), ellipse_point(L["UC-16"], led.p("t", 0.3))])
    edge(c, [led.p("t", 0.7), ellipse_point(img, led.p("t", 0.7))])
    edge(c, [led.p("t", 0.5), ellipse_point(R["UC-20"], led.p("t", 0.5))])
    return c.done("Kullanım durumu diyagramı: hesap, okuma ve tartışma")


def uc_yonetisim() -> uml.Diagram:
    c = Canvas()
    c.rect(140, 0, 470, 470, fill="none")
    c.text(375, 18, "Meşveret · öneri, oylama ve havale", 11, "serifb", anchor="middle")
    U = {}
    for code, t, y in [("UC-01", "Öneri aç", 52), ("UC-02", "İtiraz et", 104),
                       ("UC-03", "Karar Saati'nde\noy ver", 160), ("UC-24", "Şerh ekle", 216),
                       ("UC-04", "Havale ver, geri al,\nyenile", 274),
                       ("UC-25", "Havale isteğini kabul et,\nreddet, iade et", 340),
                       ("UC-26", "Kapanış öner,\nrakip metin ekle", 412)]:
        U[code] = usecase(c, 262, y, t, code=code)
    for code, t, y in [("UC-29", "Etkinlik ekle", 46), ("UC-27", "Öneriyi yorumla\n(H1–H4)", 104),
                       ("UC-28", "Kural zinciri\n(R1–R9)", 168), ("UC-30", "Oyu mühürle\n(commit)", 236),
                       ("UC-31", "Karar Saati'ni aç,\nsay, kapat", 312),
                       ("UC-32", "Sessiz onayı\nsonuçlandır", 404)]:
        U[code] = usecase(c, 492, y, t, code=code)
    _uc_dep(c, U["UC-01"], U["UC-28"], "include")
    _uc_dep(c, U["UC-01"], U["UC-27"], "include")
    _uc_dep(c, U["UC-29"], U["UC-01"], "extend", lpos=(372, 40))
    _uc_dep(c, U["UC-03"], U["UC-30"], "include")
    c.text(262, 446, "KAPANIŞ da bir öneridir: UC-01'in denetimi uygulanır", 8.6, "serifi",
           anchor="middle", fill=SOFT)
    yur = actor(c, 46, 120, "Yurttaş")
    tem = actor(c, 46, 290, "Temsilci")
    kat = actor(c, 46, 400, "Konu\nkatılımcısı")
    for code in ("UC-01", "UC-02", "UC-03", "UC-24", "UC-04"):
        _uc_link(c, yur, U[code])
    _uc_link(c, tem, U["UC-25"])
    _uc_link(c, kat, U["UC-26"])
    _gen(c, tem, yur, [(54, 290), (54, 196)])
    _gen(c, kat, yur, [(36, 400), (16, 380), (16, 210), (34, 196)])
    hat = actor(c, 700, 90, "Hâtif", system=True, stereo="sistem aktörü")
    zam = actor(c, 700, 330, "Zamanlayıcı", system=True, stereo="zaman")
    edge(c, [hat.p("l"), ellipse_point(U["UC-27"], hat.p("l"))])
    edge(c, [hat.p("b", 0.3), ellipse_point(U["UC-31"], hat.p("b", 0.3))])
    edge(c, [zam.p("l", 0.3), ellipse_point(U["UC-31"], zam.p("l", 0.3))])
    edge(c, [zam.p("l", 0.8), ellipse_point(U["UC-32"], zam.p("l", 0.8))])
    return c.done("Kullanım durumu diyagramı: öneri, oylama ve havale")


def uc_mahzen() -> uml.Diagram:
    c = Canvas()
    c.rect(150, 0, 440, 360, fill="none")
    c.text(370, 18, "Meşveret · Mahzen", 11, "serifb", anchor="middle")
    U = {}
    for code, t, y in [("UC-33", "Mahzen'e gir\n(uyarıyı onayla)", 58), ("UC-34", "Başlık aç", 116),
                       ("UC-35", "Yanıt yaz", 164), ("UC-36", "Kendi mesajını imzala", 218),
                       ("UC-05", "İfşa oylaması aç", 268), ("UC-37", "İfşa oyu ver,\ndeğiştir", 326)]:
        U[code] = usecase(c, 278, y, t, code=code)
    U["UC-38"] = usecase(c, 484, 236, "Baskın tespiti", code="UC-38")
    U["UC-39"] = usecase(c, 484, 318, "Başlığı ifşa et,\ntaslak öneri oluştur", code="UC-39")
    U["UC-40"] = usecase(c, 484, 96, "Kapasite dolunca\nen alttakini sil", code="UC-40")
    _uc_dep(c, U["UC-05"], U["UC-38"], "include")
    _uc_dep(c, U["UC-39"], U["UC-37"], "extend")
    _uc_dep(c, U["UC-40"], U["UC-34"], "extend")
    c.text(484, 352, "[EVET > seçmenlerin yarısı]", 8.6, "serifi", anchor="middle", fill=SOFT)
    yur = actor(c, 50, 70, "Yurttaş")
    kat = actor(c, 50, 240, "Başlık\nkatılımcısı")
    for code in ("UC-33", "UC-34", "UC-35"):
        _uc_link(c, yur, U[code])
    for code in ("UC-36", "UC-05", "UC-37"):
        _uc_link(c, kat, U[code])
    _gen(c, kat, yur, [(50, 240), (50, 146)])
    led = actor(c, 690, 290, "Defter", system=True, stereo="sistem")
    edge(c, [led.p("l"), ellipse_point(U["UC-39"], led.p("l"))])
    c.text(690, 336, "ifşa kaydı; yaşayan başlık", 8.6, "serifi", anchor="middle", fill=SOFT)
    c.text(690, 347, "deftere yazılmaz", 8.6, "serifi", anchor="middle", fill=SOFT)
    return c.done("Kullanım durumu diyagramı: Mahzen")


def uc_sonuc() -> uml.Diagram:
    c = Canvas()
    c.rect(150, 0, 440, 410, fill="none")
    c.text(370, 18, "Meşveret · kararların sonucu", 11, "serifb", anchor="middle")
    U = {}
    for code, t, y in [("UC-41", "Takvimi ve etkinliği\ngörüntüle", 58), ("UC-42", "Dilekçeyi görüntüle,\nyazdır", 120),
                       ("UC-43", "Takvime abone ol\n(.ics)", 182), ("UC-44", "Geliyorum de,\ngeri al", 246),
                       ("UC-06", "Etkinlik raporu yaz", 312), ("UC-07", "Kurum yanıtını işle", 372)]:
        U[code] = usecase(c, 278, y, t, code=code)
    U["UC-45"] = usecase(c, 488, 290, "Fotoğraf ekle", code="UC-45")
    U["UC-46"] = usecase(c, 488, 372, "Taranmış belge ekle", code="UC-46")
    U["UC-47"] = usecase(c, 488, 82, "Konuyu muhataba ilet:\ndilekçe ya da takvim", code="UC-47")
    _uc_dep(c, U["UC-45"], U["UC-06"], "extend")
    _uc_dep(c, U["UC-46"], U["UC-07"], "extend")
    ziy = actor(c, 46, 60, "Ziyaretçi")
    yur = actor(c, 46, 196, "Yurttaş")
    ekt = actor(c, 46, 296, "Etkinlik\nkatılımcısı")
    ktl = actor(c, 110, 420, "Konu katılımcısı")
    for code in ("UC-41", "UC-42", "UC-43"):
        _uc_link(c, ziy, U[code])
    _uc_link(c, yur, U["UC-44"])
    _uc_link(c, ekt, U["UC-06"])
    edge(c, [(ktl.r, 446), ellipse_point(U["UC-07"], (ktl.r, 446))])
    _gen(c, yur, ziy, [(46, 196), (46, 130)])
    _gen(c, ekt, yur, [(46, 296), (46, 266)])
    edge(c, [(ktl.x + 8, 446), (12, 446), (12, 250), (34, 250)], head="tri")
    tak = actor(c, 690, 150, "Takvim\nuygulaması", system=True, stereo="dış sistem")
    zam = actor(c, 690, 40, "Zamanlayıcı", system=True, stereo="zaman")
    edge(c, [tak.p("l"), ellipse_point(U["UC-43"], tak.p("l"))])
    edge(c, [zam.p("l"), ellipse_point(U["UC-47"], zam.p("l"))])
    c.text(690, 92, "konu kabul edilince", 8.6, "serifi", anchor="middle", fill=SOFT)
    return c.done("Kullanım durumu diyagramı: kararların sonucu")


# =====================================================================================================
# SINIF DİYAGRAMLARI (tasarım) — sema.json'daki sınıflardan
# =====================================================================================================


def _k(name: str) -> dict:
    hits = [v for k, v in SEMA["classes"].items() if k.endswith("." + name)]
    if len(hits) != 1:
        raise SystemExit(f"sema.json'da sınıf bulunamadı ya da birden çok: {name}")
    return hits[0]


def _ops(name: str, *, only: list[str] | None = None, sig: dict | None = None) -> list[str]:
    """Sınıfın kendi tanımladığı işlemler, ``ad()`` biçiminde; soyutlar «abstract» işaretli."""
    k = _k(name)
    out = []
    for m in k["methods"]:
        if m.startswith("_") and not (only and m in only):
            continue
        if only is not None and m not in only:
            continue
        s = (sig or {}).get(m, "()")
        out.append(f"{'+'} {m}{s}" + ("  {abstract}" if m in k["abstract"] else ""))
    return out


def cd_oneri() -> uml.Diagram:
    c = Canvas()
    fac = cls(c, 0, 0, "proposals", [], [
        "+ open_proposal(ctx, user, inp)", "+ submit_draft(...)", "+ object_to(ctx, user, id)",
        "+ add_rival(...)", "+ enter_session(ctx, p, oturum)", "+ accept(ctx, p, ...)",
        "+ reject(ctx, p, not)", "+ proposal_view(ctx, p, izleyen)"], stereo="facade · modül")
    reg = cls(c, 300, 0, "Registry[T]", ["- _items: dict[str, T]"],
              _ops("Registry", sig={"register": "(anahtar)", "get": "(anahtar): T",
                                    "create": "(anahtar, **kw): T"}))
    kinds = cls(c, 300, 128, "KINDS", [], [], stereo="nesne · Registry[ProposalKind]", head=WHITE)
    pk = _k("ProposalKind")
    base = cls(c, 505, 0, "ProposalKind", ["+ type: ProposalType", "+ ballot: str = \"binary\"",
                                           "+ takes_cover: bool"],
               _ops("ProposalKind", sig={"prepare": "(ctx, user, inp): Prepared",
                                         "apply": "(ctx, p, kazanan)", "threshold_key": "(p): str",
                                         "draft_fields": "(p): dict", "content_check": "(ctx, p)",
                                         "after_open": "(ctx, p, ad)", "view": "(ctx, p): dict"}),
               italic=True, stereo="abstract · Strategy")
    assert set(pk["abstract"]) == {"apply", "prepare"}
    edge(c, [fac.p("r", 0.25), reg.p("l", 0.4)], head="open", label="kind_for(p)")
    edge(c, [kinds.p("t"), reg.p("b")], head="tri", dash=True)
    edge(c, [kinds.p("r"), (base.x - 20, kinds.cy), (base.x - 20, base.cy), base.p("l")],
         head="open", tail="odiamond", label="0..*", lpos=(base.x - 30, base.cy - 6), lanchor="end")
    y2 = 300
    nt = cls(c, 40, y2, "_NewTopic", [], ["+ prepare()", "+ apply()", "+ view()",
                                           "# _parent()", "# _target_key()"], italic=True)
    leaf = []
    x = nt.r + 24
    for n, t in [("ReopenKind", "KONU/yeniden"), ("EditKind", "DUZENLEME"), ("DeletionKind", "SILME"),
                 ("RegulationKind", "YONETMELIK"), ("ClosureKind", "KAPANIS")]:
        attrs = [f"type = {t}"] + (["ballot = \"approval\""] if n == "ClosureKind" else [])
        b = cls(c, x, y2, n, attrs, [])
        leaf.append(b)
        x = b.r + 12
    tree(c, base, [nt, *leaf], bus=y2 - 26)
    tk = cls(c, 0, y2 + 130, "TopicKind", ["type = KONU"], [])
    sk = cls(c, 110, y2 + 130, "SubtopicKind", ["type = ALT_KONU"], ["# _parent()", "# _target_key()"])
    tree(c, nt, [tk, sk], bus=y2 + 112)
    inp = cls(c, 300, y2 + 130, "ProposalInput", [f"{len(_k('ProposalInput')['fields'])} alan: type, title,",
                                                  "body, scope_id, addressee,", "event, share_effect, …"],
              [], stereo="dataclass")
    prep = cls(c, 470, y2 + 130, "Prepared", ["type, title, body, area_id,", "scope_id, resource_ids,",
                                              "target_key, payload"], [], stereo="dataclass")
    trunk = base.r + 14
    edge(c, [base.p("r", 0.62), (trunk, base.y + base.h * 0.62), (trunk, prep.y - 12),
             (prep.cx, prep.y - 12), prep.p("t")], head="open", dash=True, label="«create»",
         lkind="serifi", lsize=8.8, lpos=(prep.cx + 30, prep.y - 16))
    edge(c, [(trunk, base.y + base.h * 0.62), (trunk, prep.y - 26), (inp.cx, prep.y - 26), inp.p("t")],
         head="open", dash=True, label="«use»", lkind="serifi", lsize=8.8, lpos=(inp.cx + 22, prep.y - 30))
    return c.done("Sınıf diyagramı: öneri motoru")


def cd_durum() -> uml.Diagram:
    c = Canvas()
    base = cls(c, 250, 0, "ProposalState", ["+ status: str", "+ pending: bool"],
               ["+ submit()", "+ object()", "+ add_rival()", "+ escalate()", "+ end_rival_period()",
                "+ enter_session()", "+ accept()", "+ reject()", "+ conflict()"],
               stereo="State · varsayılan: InvalidTransition")
    pend = cls(c, 40, 230, "_Pending", ["pending = True"], ["+ accept() → Accepted", "+ reject() → Rejected",
                                                          "+ conflict() → Conflicted"])
    draft = cls(c, 300, 230, "Draft", ["status = DRAFT"], ["+ submit()"])
    acc = cls(c, 400, 230, "Accepted", ["status = ACCEPTED"], [])
    rej = cls(c, 525, 230, "Rejected", ["status = REJECTED"], [])
    con = cls(c, 645, 230, "Conflicted", ["status = CONFLICT"], [])
    tree(c, base, [pend, draft, acc, rej, con], bus=205)
    y3 = 360
    sil = cls(c, 0, y3, "Silent", ["status = SILENT"], ["+ object()", "+ escalate() → Queued"])
    riv = cls(c, 150, y3, "RivalPeriod", ["status = RIVAL_PERIOD"], ["+ add_rival()",
                                                                     "+ end_rival_period() → Queued"])
    que = cls(c, 340, y3, "Queued", ["status = QUEUED"], ["+ enter_session() → Voting"])
    vot = cls(c, 515, y3, "Voting", ["status = VOTING"], [])
    tree(c, pend, [sil, riv, que, vot], bus=y3 - 20)
    note(c, 520, 30, ["Durum sınıfları saftır; veritabanında", "durum metin olarak durur,",
                      "state_of(status) sınıfı bulur.", "Geçersiz geçiş gerekçeli",
                      "InvalidTransition fırlatır."])
    return c.done("Sınıf diyagramı: önerinin durumları (State)")


def cd_kurallar() -> uml.Diagram:
    c = Canvas()
    rule = cls(c, 250, 0, "Rule", ["+ code: str", "+ types: frozenset | None", "+ next: Rule | None"],
               ["+ handle(taslak, bağlam, rapor): RuleReport", "+ check(taslak, bağlam, rapor)  {abstract}"],
               italic=True, stereo="abstract · Chain of Responsibility")
    assert _k("Rule")["abstract"] == ["check"]
    edge(c, [rule.p("l", 0.35), (rule.x - 40, rule.y + rule.h * 0.35), (rule.x - 40, rule.y - 18),
             (rule.cx, rule.y - 18), rule.p("t")], head="open", tail="odiamond",
         label="next 0..1", lpos=(rule.x - 44, rule.y + 2), lanchor="end")
    names = [("AreaExists", "Alan var", "tümü"), ("SubtopicArea", "R1", "ALT_KONU"),
             ("OwnershipAndRegulation", "R2 · R3", "tümü"), ("ProposerVoteRight", "R5", "tümü"),
             ("RejectionCooldown", "R6", "tümü"), ("DeletionGround", "R7", "SILME"),
             ("RegulationFloor", "R8", "YONETMELIK"), ("AddresseeJurisdiction", "R9", "KONU, ALT_KONU")]
    boxes = []
    row = [names[:4], names[4:]]
    y = 150
    for r in row:
        x = 0
        for n, code, types in r:
            _k(n)
            b = cls(c, x, y, n, [f"code = {code}", f"types: {types}"], ["+ check()"], size=10.5)
            boxes.append(b)
            x = b.r + 14
        y += 96
    tree(c, rule, boxes[:4], bus=128)
    trunk_x = max(b.r for b in boxes) + 9
    bus2 = boxes[4].y - 10
    for b in boxes[4:]:
        c.line([(b.cx, b.y), (b.cx, bus2)])
    c.line([(boxes[4].cx, bus2), (trunk_x, bus2), (trunk_x, 128), (boxes[3].cx, 128)])
    rep = cls(c, 600, 150, "RuleReport", ["+ violations: list[Violation]", "+ narrowings: list[Narrowing]"],
              ["+ ok(): bool"], stereo="dataclass")
    ctxb = cls(c, 600, 250, "RuleContext", ["+ onto: OntologyView", "+ reg: Regulation", "+ now",
                                            "+ proposer_right: VoteRight", "+ last_rejection"],
               [], stereo="dataclass")
    dr = cls(c, 600, 0, "ProposalDraft", [f"{len(_k('ProposalDraft')['fields'])} alan: type, scope_id,",
                                          "resource_ids, target_key, …"], [], stereo="dataclass")
    edge(c, [rule.p("r", 0.75), (585, rule.y + rule.h * 0.75), (585, rep.cy), rep.p("l")],
         head="open", dash=True, label="«use»", lkind="serifi", lsize=8.8, lpos=(570, 120))
    edge(c, [(585, rep.cy), (585, ctxb.cy), ctxb.p("l")], head="open", dash=True)
    edge(c, [rule.p("r", 0.2), (dr.x, rule.y + rule.h * 0.2)], head="open", dash=True)
    note(c, 0, 360, ["proposal_chain() halkaları bu sırayla bağlar.",
                     "Zincir kesilmez: kişi bütün gerekçeleri görsün diye",
                     "her halka kendi türlerini denetler ve devreder."])
    return c.done("Sınıf diyagramı: kural zinciri")



def cd_isler() -> uml.Diagram:
    """Kaynak: services/jobs.py (Job ve alt sınıfları, SOURCES, due), services/scheduler.py."""
    c = Canvas()
    src = cls(c, 0, 0, "jobs", ["SOURCES = proposal_jobs,", "  delegation_jobs,",
                                "  decision_hour_jobs"], ["+ due(ctx, until, son): list[Job]"],
              stereo="modül")
    sch = cls(c, src.r + 70, 0, "scheduler", [], ["+ tick(ctx, until)", "+ background_tick(...)",
                                                  "+ exclusive(db)  (kilit)"], stereo="modül · çağırıcı")
    edge(c, [sch.p("l", 0.4), (src.r, sch.y + sch.h * 0.4)], head="open", label="due()")
    job = cls(c, sch.r + 70, 0, "Job", ["+ due_at: datetime"], ["+ label: str  {abstract}",
                                                                 "+ run(ctx)  {abstract}"],
              italic=True, stereo="abstract · Command")
    assert set(_k("Job")["abstract"]) == {"label", "run"}
    edge(c, [sch.p("r", 0.4), (job.x, sch.y + sch.h * 0.4)], head="open", label="run(ctx)")
    edge(c, [src.p("t", 0.5), (src.cx, -18), (job.cx, -18), job.p("t", 0.5)], head="open", dash=True,
         label="«create»", lkind="serifi", lsize=8.8, lpos=(job.cx - 50, -22))
    row = max(src.b, sch.b, job.b) + 46
    kids = []
    x = 0
    for n in ("_ProposalJob", "OpenDecisionHour", "CloseDecisionHour", "ExpireDelegation",
              "ExpireDelegationRequest"):
        k = _k(n)
        attrs = [f for f in k["fields"] if f != "due_at"]
        b = cls(c, x, row, n, attrs, ["+ run(ctx)"] if n == "_ProposalJob" else [],
                italic=n.startswith("_"), size=10.5)
        kids.append(b)
        x = b.r + 12
    tree(c, job, kids, bus=row - 20)
    pj = kids[0]
    gy = max(k.b for k in kids) + 40
    gk = [cls(c, 0, gy, "EndSilentPeriod", [], ["# _transition()"], size=10.5)]
    gk.append(cls(c, gk[0].r + 12, gy, "EndRivalPeriod", [], ["# _transition()"], size=10.5))
    tree(c, pj, gk, bus=gy - 18)
    note(c, gk[-1].r + 40, gy, ["Her iş idempotenttir: durumu denetler,",
                                "ikinci çalıştırmada deftere yazmaz.",
                                "Eşit vadede SOURCES sırası geçerlidir."])
    return c.done("Sınıf diyagramı: zamanlanmış işler (Command)")


def cd_oylama_olaylar() -> uml.Diagram:
    """Kaynak: services/decision_hour.py (BallotMethod), services/events.py (EventBus, olaylar)."""
    c = Canvas()
    bm = cls(c, 0, 0, "BallotMethod", ["+ kind: str"], [
        "+ normalize(ctx, p, seçim)  {abstract}", "+ oracle_choice(ctx, p, oy)  {abstract}",
        "+ ballot_extra(ctx, p): dict", "+ close(ctx, oturum, p, oylamalar, yön.)  {abstract}"],
        italic=True, stereo="abstract · Strategy")
    assert set(_k("BallotMethod")["abstract"]) == {"close", "normalize", "oracle_choice"}
    yn = cls(c, 0, 160, "YesNoBallot", ["kind = \"binary\""], ["+ close(): eşik, alt kapsamlar"])
    ap = cls(c, yn.r + 14, 160, "ApprovalBallot", ["kind = \"approval\""], ["+ close(): en çok onay"])
    tree(c, bm, [yn, ap])
    bf = cls(c, 0, 280, "ballot_for(p)", [], ["BALLOTS[proposals.ballot_kind(p)]"], stereo="işlev")
    edge(c, [bf.p("t", 0.5), (bf.cx, yn.b)], head="open", dash=True, label="seçer", lkind="serifi",
         lsize=8.8, lpos=(bf.cx + 6, yn.b + 18), lanchor="start")
    bus = cls(c, 430, 0, "EventBus", ["- _subs: dict[type, list]"],
              ["+ subscribe(olay_türü, işlev)", "+ publish(ctx, olay)"], stereo="Observer")
    evs = ["TopicAccepted", "DecisionMade", "SilentPeriodEnded", "MovedToSlowLane", "SessionClosed",
           "PetitionSent", "PetitionReplied"]
    for n in evs:
        _k(n)
    ev = cls(c, 430, 120, "olaylar", ["TopicAccepted, DecisionMade,", "SilentPeriodEnded,",
                                       "MovedToSlowLane, SessionClosed,", "PetitionSent, PetitionReplied"],
             [], stereo="dataclass ×7", mkind="serif")
    edge(c, [bus.p("b", 0.3), (bus.x + bus.w * 0.3, ev.y)], head="open", dash=True, label="«use»",
         lkind="serifi", lsize=8.8, lpos=(bus.x + bus.w * 0.3 + 6, bus.b + 14), lanchor="start")
    sub = cls(c, 430, 260, "aboneler", ["petitions ← TopicAccepted, DecisionMade",
                                         "calendar ← TopicAccepted",
                                         "notifications ← SessionClosed,",
                                         "  SilentPeriodEnded, MovedToSlowLane,",
                                         "  PetitionSent, PetitionReplied"], [], stereo="modüller",
              mkind="serif")
    right = max(bus.r, sub.r, ev.r) + 18
    edge(c, [bus.p("r", 0.6), (right, bus.y + bus.h * 0.6), (right, sub.cy), sub.p("r")], head="open",
         label="publish → çağırır", lpos=(right + 4, sub.y - 8), lanchor="end")
    pub = cls(c, 430, 400, "yayımlayanlar", ["proposal_kinds, proposals,", "decision_hour, petitions"],
              [], stereo="modüller", mkind="serif")
    edge(c, [pub.p("l", 0.5), (400, pub.cy), (400, bus.cy), bus.p("l")], head="open",
         label="publish(olay)", lpos=(396, 230), lanchor="end")
    return c.done("Sınıf diyagramı: oylama biçimleri (Strategy) ve alan olayları (Observer)")


def cd_depolar() -> uml.Diagram:
    c = Canvas()
    ctxb = cls(c, 270, 0, "Ctx", ["+ db: Session", "+ graph: GraphStore", "+ ledger: LedgerClient",
                                   "+ now: datetime", "+ settings: Settings", "+ reg: Regulation"],
               ["+ at(an): Ctx", "+ commit()"], stereo="dataclass · istek bağlamı")
    ov = cls(c, 0, 210, "OntologyView", [], ["+ area(id)", "+ scope(id)", "+ is_strict_subset(a, b)",
                                             "+ resource(id)", "+ topic_area(id)", "…"],
             stereo="Protocol · Repository")
    gs = cls(c, 0, 380, "GraphStore", [], ["+ set_membership(...)", "+ delegation_edges(an)",
                                          "+ set_delegation(...)", "+ add_interaction(a, b, w)",
                                          "+ articles(), set_article(...)", "+ record_proposal(...)", "…"],
             stereo="Protocol")
    edge(c, [gs.p("t"), ov.p("b")], head="tri")
    mem = cls(c, 230, 400, "InMemoryGraph", ["bellek içi sözlükler"], [], size=11)
    neo = cls(c, 230, 470, "Neo4jGraph", ["- driver: neo4j.Driver"], ["+ ensure_constraints()"],
              stereo="Adapter · Cypher")
    for b in (mem, neo):
        edge(c, [b.p("l"), (gs.r + 20, b.cy), (gs.r + 20, gs.cy), gs.p("r")], head="tri", dash=True)
    lc = cls(c, 500, 210, "LedgerClient", [], ["+ append(tür, yük, ts)", "+ append_batch(kayıtlar)",
                                              "+ get(url, yol)", "+ node_urls()", "+ reset()"],
             stereo="Protocol · Repository")
    http = cls(c, 440, 400, "HttpLedgerClient", ["- leader_url, node_urls,", "  token"], [],
               stereo="Adapter · HTTP")
    fake = cls(c, 610, 400, "FakeLedgerClient", ["bellek içi zincir (testler)"], [])
    tree(c, lc, [http, fake], dash=True)
    edge(c, [ctxb.p("l", 0.35), (ov.cx, ctxb.y + ctxb.h * 0.35), ov.p("t")], head="open",
         tail="odiamond", label="graph", lpos=(150, ctxb.y + ctxb.h * 0.35 - 4))
    edge(c, [ctxb.p("r", 0.45), (lc.cx, ctxb.y + ctxb.h * 0.45), lc.p("t")], head="open",
         tail="odiamond", label="ledger", lpos=(560, ctxb.y + ctxb.h * 0.45 - 4))
    note(c, 440, 500, ["Kurallar ve servisler yalnızca protokolü bilir.",
                       "İki graf uygulaması aynı sözleşme",
                       "testlerinden geçer (graph_contract.py)."])
    return c.done("Sınıf diyagramı: depolar ve uyarlayıcılar")



def _spine(c: Canvas, parent: Box, kids: list[Box], x: float) -> None:
    """Dikey omurgalı kalıtım: çocuklar alt alta, ebeveyne tek uç."""
    c.line([(x, parent.b + 14), (x, kids[-1].cy)])
    for k in kids:
        c.line([(x, k.cy), (k.x, k.cy)])
    edge(c, [(x, parent.b + 14), (parent.x + 14 if x < parent.x + 14 else x, parent.b + 14),
             (parent.x + 14 if x < parent.x + 14 else x, parent.b)], head="tri")


def cd_degerlendirme() -> uml.Diagram:
    """Kaynak: evaluation/ (harness, repository, detectors, observers, metrics, scenarios)."""
    c = Canvas()
    rp = cls(c, 0, 0, "ScenarioRepository", [], ["+ load(): list[Scenario]  {abstract}"],
             italic=True, stereo="abstract · Repository")
    reps = []
    y = rp.b + 26
    for n, a in [("GeneratedScenarioRepository", "üreteç (tohumlu)"), ("JsonScenarioRepository", "sabit dosya; freeze()"),
                 ("LiveScenarioRepository", "canlı yığın"), ("InMemoryScenarioRepository", "testler")]:
        _k(n)
        b = cls(c, 26, y, n, [a], [], size=10, mkind="serif")
        reps.append(b)
        y = b.b + 10
    _spine(c, rp, reps, 12)
    ev = cls(c, 300, 0, "Evaluation", ["+ config: dict", "+ repository", "+ observers"],
             ["+ run(): dict", "+ detectors()", "+ costs()"], stereo="dataclass · Facade")
    edge(c, [ev.p("l", 0.3), (rp.r, ev.y + ev.h * 0.3)], head="open", tail="odiamond", label="1",
         lpos=(rp.r + 12, ev.y + ev.h * 0.3 - 4))
    det = cls(c, 560, 0, "Detector", ["+ name, description"], ["+ fit(senaryolar)", "+ predict(s): set",
                                                                 "+ explain(): str"],
              italic=True, stereo="abstract · Strategy")
    edge(c, [ev.p("r", 0.3), (det.x, ev.y + ev.h * 0.3)], head="open", label="1..*",
         lpos=(det.x - 8, ev.y + ev.h * 0.3 - 4), lanchor="end")
    c.text((ev.r + det.x) / 2, ev.y + ev.h * 0.3 + 14, "DETECTORS", 8.8, "serifi", anchor="middle", fill=SOFT)
    ds = []
    y = det.b + 26
    for n in ("RandomDetector", "NobodyDetector", "NewMemberRule", "ClusterDetector", "DecisionTreeDetector"):
        _k(n)
        b = cls(c, det.x + 26, y, n, [], [], size=10)
        ds.append(b)
        y = b.b + 8
    _spine(c, det, ds, det.x + 12)
    ob = cls(c, 300, ev.b + 50, "EvaluationObserver", [], ["+ on_start()", "+ on_result()", "+ on_extra()",
                                                          "+ on_finish()"], stereo="Observer")
    edge(c, [ev.p("b", 0.5), ob.p("t", 0.5)], head="open", tail="odiamond", label="0..*",
         lpos=(ev.cx + 6, ev.b + 28), lanchor="start")
    obs = []
    y = ob.b + 26
    for n, a in [("ConsoleReporter", "konsol tablosu"), ("JsonReporter", "sonuclar.json"),
                 ("MlflowReporter", "MLflow: üst koşu + tespitçi başına alt koşu")]:
        _k(n)
        b = cls(c, ob.x + 26, y, n, [a], [], size=10, mkind="serif")
        obs.append(b)
        y = b.b + 10
    _spine(c, ob, obs, ob.x + 12)
    sc = cls(c, 0, reps[-1].b + 44, "Scenario", ["name, at, joined,", "interactions, raiders, groups"],
             ["+ newcomers(pencere)"], stereo="dataclass")
    edge(c, [(reps[-1].cx, reps[-1].b), (reps[-1].cx, sc.y)], head="open", dash=True,
         label="load() üretir", lkind="serifi", lsize=8.8, lpos=(reps[-1].cx + 6, reps[-1].b + 26),
         lanchor="start")
    cf = cls(c, det.x, ds[-1].b + 40, "Confusion", ["tp, fn, fp, tn"],
             ["+ precision(), recall()", "+ f_beta(β), cost(...)"], stereo="dataclass")
    lx = det.x - 16
    edge(c, [ev.p("r", 0.85), (lx, ev.y + ev.h * 0.85), (lx, cf.cy), cf.p("l")], head="open", dash=True,
         label="run() hesaplar", lkind="serifi", lsize=8.8, lpos=(lx - 4, cf.cy - 6), lanchor="end")
    return c.done("Sınıf diyagramı: değerlendirme düzeneği")


# --- alan modeli (kavramsal) --------------------------------------------------------------------


def _assoc(c: Canvas, pts: list, a: str = "", b: str = "", name: str = "", *, head: str | None = None,
           tail: str | None = None, dash: bool = False, nlpos=None) -> None:
    edge(c, pts, head=head, tail=tail, dash=dash, label=name or None, lkind="serifi", lsize=9,
         lpos=nlpos)
    for txt, (p, q) in ((a, (pts[0], pts[1])), (b, (pts[-1], pts[-2]))):
        if not txt:
            continue
        ux, uy = uml._unit(p, q)
        x, y = p[0] + ux * 10 + (-uy) * 9, p[1] + uy * 10 + ux * 9
        if abs(uy) > 0.5:
            x, y = p[0] + 5, p[1] + uy * 14 + 3
        else:
            x, y = p[0] + ux * 6 + (2 if ux > 0 else -2), p[1] - 4
        c.text(x, y, txt, 9, "mono", anchor="start" if ux >= 0 else "end", fill=SOFT)



def dm_kimlik() -> uml.Diagram:
    """Kavramsal model. Kaynak: DESIGN.md §4 (ontoloji), db/models.py (User, DelegationRequest),
    graph/neo4j_store.py (UYE, ALT_KUMESI, SAHIBI, HAVALE, ALT_ALANI)."""
    c = Canvas()
    S = dict(mkind="serif")
    yur = cls(c, 0, 0, "Yurttaş", ["takma ad", "e-posta (doğrulanmış)", "şehir, ilçe, adres",
                                    "doğum tarihi", "rol: yurttaş | Hâtif"], [], **S)
    kap = cls(c, 380, 0, "Kapsam", ["ad", "tür"], [], italic=True, **S)
    kay = cls(c, 600, 0, "Kaynak", ["ad", "bölünebilir", "paylar: kapsam → puan"], [], italic=True, **S)
    y_line = 22
    _assoc(c, [(yur.r, y_line), (kap.x, y_line)], "0..*", "1..*", "üyesidir",
           nlpos=((yur.r + kap.x) / 2 + 40, y_line - 5))
    mid = 215
    uye = cls(c, mid - 70, 175, "Üyelik", ["since (katılım anı)", "neden: kayıt | adres |", "  yaş | katılım"],
              [], stereo="ilişki sınıfı", **S)
    c.line([(mid, y_line), (mid, uye.y)], dash="4 3")
    edge(c, [(kap.x + 20, kap.y), (kap.x + 20, kap.y - 16), (kap.x + 60, kap.y - 16), (kap.x + 60, kap.y)])
    c.text(kap.x + 64, kap.y - 8, "alt kümesi 0..*", 9, "serifi", fill=SOFT)
    _assoc(c, [kay.p("l", 0.35), (kap.r, kay.y + kay.h * 0.35)], "0..*", "1", "sahibi",
           nlpos=((kap.r + kay.x) / 2, kay.y + kay.h * 0.35 - 5))
    ks = []
    x = 262
    for n, a in [("Genel", "herkes"), ("Şehir", "adresten"), ("YaşGrubu", "doğum tarihinden"),
                 ("İlgi", "alana katılımla")]:
        b = cls(c, x, 110, n, [a], [], size=10.5, **S)
        ks.append(b)
        x = b.r + 8
    tree(c, kap, ks, bus=90)
    ys = []
    x = 400
    for n in ("Alan", "Konu", "YönetmelikMaddesi", "OrtakKaynak"):
        b = cls(c, x, 250, n, [], [], size=10.5, **S)
        ys.append(b)
        x = b.r + 10
    tree(c, kay, ys, bus=200)
    al = ys[0]
    edge(c, [(al.x + 10, al.b), (al.x + 10, al.b + 16), (al.x + 40, al.b + 16), (al.x + 40, al.b)])
    c.text(al.x, al.b + 28, "alt alanı 0..*", 9, "serifi", fill=SOFT)
    note(c, 400, 310, ["Alan: anahtar kelimeler (Hâtif) · Konu: başlık, durum, muhatap",
                       "YönetmelikMaddesi: değer, izinli aralık · OrtakKaynak: bütçe, salon",
                       "Konu, onu kabul eden önerinin seçmen kapsamına aittir."], size=9)
    hav = cls(c, 0, 290, "Havale", ["alan: Alan ya da genel", "since, bitiş (180 gün)"], [], **S)
    _assoc(c, [(hav.x + 18, hav.y), (hav.x + 18, yur.b)], "0..*", "1")
    c.text(hav.x + 22, 200, "veren", 9, "serifi", fill=SOFT)
    _assoc(c, [(hav.r - 18, hav.y), (hav.r - 18, yur.b)], "0..*", "1")
    c.text(hav.r - 22, 240, "alan (temsilci)", 9, "serifi", anchor="end", fill=SOFT)
    ist = cls(c, 0, 400, "Havaleİsteği", ["durum: bekliyor | kabul | ret |", "  iptal | süresi doldu |",
                                          "  iade | bitti", "kabul için son gün"], [], **S)
    _assoc(c, [ist.p("t", 0.3), (ist.x + ist.w * 0.3, hav.b)], "1", "0..1", "kabulle doğar",
           nlpos=(ist.x + ist.w * 0.3 + 50, (ist.y + hav.b) / 2 + 4))
    return c.done("Alan modeli: yurttaş, kapsam, kaynak ve havale")


def dm_oneri() -> uml.Diagram:
    """Kavramsal model. Kaynak: db/models.py (proposals, objections, closure_texts, decisions,
    dissents, topics, messages, message_versions, decision_sessions, session_items, ballots)."""
    c = Canvas()
    S = dict(mkind="serif")
    yur = cls(c, 0, 0, "Yurttaş", [], [], size=11, **S)
    on = cls(c, 190, 0, "Öneri", ["tür: konu | alt konu | düzenleme |", "  silme | yönetmelik | kapanış",
                                   "durum, şerit, metin", "daraltma, Hâtif yorumu"], [], **S)
    _assoc(c, [yur.p("r", 0.5), (on.x, yur.cy)], "1", "0..*", "açar", nlpos=((yur.r + on.x) / 2, yur.cy - 5))
    kap = cls(c, 600, 0, "Kapsam", [], [], size=11, italic=True, **S)
    kay = cls(c, 600, 50, "Kaynak", [], [], size=11, italic=True, **S)
    _assoc(c, [(on.r, kap.cy), kap.p("l")], "0..*", "1", "seçmen", nlpos=((on.r + kap.x) / 2, kap.cy - 5))
    _assoc(c, [(on.r, kay.cy), kay.p("l")], "0..*", "0..*", "etkiler", nlpos=((on.r + kay.x) / 2, kay.cy - 5))
    r1 = 160
    it = cls(c, 0, r1, "İtiraz", ["an"], [], w=90, **S)
    km = cls(c, 130, r1, "KapanışMetni", ["metin"], [], **S)
    ko = cls(c, 340, r1, "Konu", ["başlık, durum", "muhatap"], [], **S)
    ot = cls(c, 600, r1, "KararSaatiOturumu", ["açılış, kapanış", "yönetmelik (anlık)"], [], **S)
    _assoc(c, [(it.cx - 20, it.y), (it.cx - 20, yur.b)], "0..*", "1")
    _assoc(c, [(it.cx + 20, it.y), (it.cx + 20, 56), (on.x, 56)], "0..*", "1")
    _assoc(c, [(km.cx + 20, km.y), (km.cx + 20, on.b)], "2..*", "1")
    c.text(km.cx + 24, on.b + 26, "rakip metinler", 9, "serifi", fill=SOFT)
    _assoc(c, [(ko.cx, ko.y), (ko.cx, on.b)], "0..1", "1")
    c.text(ko.cx + 4, on.b + 26, "kabulle açılır", 9, "serifi", fill=SOFT)
    edge(c, [(ko.r, ko.y + 8), (ko.r + 26, ko.y + 8), (ko.r + 26, ko.y + 26), (ko.r, ko.y + 26)])
    c.text(ko.r + 30, ko.y + 21, "alt konusu", 9, "serifi", fill=SOFT)
    r2 = 270
    se = cls(c, 0, r2, "Şerh", ["metin (silinemez)"], [], **S)
    ka = cls(c, 150, r2, "Karar", ["metin"], [], **S)
    me = cls(c, 340, r2, "Mesaj", ["yanıtladığı mesaj", "sildiren öneri (varsa)"], [], **S)
    ol = cls(c, 600, r2, "Oylama", ["seçmenler, çözülmüş", "havaleler, işaretliler,", "sonuç"], [],
             stereo="oturumdaki bir öneri", **S)
    _assoc(c, [se.p("r"), (ka.x, se.cy)], "0..*", "1")
    _assoc(c, [(ka.cx, ka.y), (ka.cx, km.b)], "0..1", "1")
    c.text(ka.cx + 4, km.b + 22, "kazanan metin", 9, "serifi", fill=SOFT)
    _assoc(c, [ka.p("r", 0.3), (ko.x - 20, ka.y + ka.h * 0.3), (ko.x - 20, ko.cy), ko.p("l")], "0..*", "1")
    _assoc(c, [(me.cx, me.y), (me.cx, ko.b)], "0..*", "1")
    _assoc(c, [(ol.cx, ol.y), (ol.cx, ot.b)], "1..*", "1")
    uml._end(c, (ol.cx, ot.b), (ol.cx, ol.y), "diamond")
    _assoc(c, [ol.p("l", 0.25), (560, ol.y + ol.h * 0.25), (560, 120), (on.r - 30, 120), (on.r - 30, on.b)],
           "0..*", "1")
    r3 = 390
    sv = cls(c, 340, r3, "MesajSürümü", ["no, metin, düzenleyen"], [], **S)
    pu = cls(c, 600, r3, "Pusula", ["seçim (mühürlü)", "tuz, commit"], [], **S)
    _assoc(c, [(sv.cx, sv.y), (sv.cx, me.b)], "1..*", "1")
    uml._end(c, (sv.cx, me.b), (sv.cx, sv.y), "diamond")
    _assoc(c, [(pu.cx, pu.y), (pu.cx, ol.b)], "0..*", "1")
    _assoc(c, [pu.p("b", 0.5), (pu.cx, pu.b + 16), (-16, pu.b + 16), (-16, yur.cy), yur.p("l")], "0..*", "1")
    c.text(-12, pu.b + 12, "veren", 9, "serifi", fill=SOFT)
    return c.done("Alan modeli: öneri, tartışma, karar ve oylama")


def od_havale() -> uml.Diagram:
    """Nesne diyagramı: tohumdaki havale zinciri, Karar Saati #1'de №9 (Gece metro seferleri).
    Kaynak: seed._delegations (aylin→baris genel, baris→ceren Ulaşım; aylin→mert reddedildi;
    elif→aylin bekliyor) ve test_seed: ceren'in №9'daki ağırlığı 3."""
    c = Canvas()

    def obj(x, y, title, slots, w=None):
        lines_w = [tw(title, 10.5, "serifb")] + [tw(s, 9.4, "mono") for s in slots]
        width = w or max(lines_w) + 18
        h = 20 + len(slots) * 12.6 + 6
        c.rect(x, y, width, h)
        c.rect(x, y, width, 20, fill=WASH)
        tx = c.text(x + width / 2, y + 14, title, 10.5, "serifb", anchor="middle")
        c.line([(x + width / 2 - tx / 2, y + 16), (x + width / 2 + tx / 2, y + 16)], sw=0.8)
        c.line([(x, y + 20), (x + width, y + 20)])
        ty = y + 32
        for s in slots:
            c.text(x + 7, ty, s, 9.4, "mono")
            ty += 12.6
        return Box(x, y, width, h)

    ay = obj(0, 0, "aylin : Yurttaş", ["şehir = Ankara"])
    ba = obj(240, 0, "baris : Yurttaş", ["şehir = İzmir"])
    ce = obj(500, 0, "ceren : Yurttaş", ["şehir = İstanbul"])
    h1 = obj(70, 100, "h1 : Havale", ["alan = (genel)", "bitiş = since + 180 gün"])
    h2 = obj(330, 100, "h2 : Havale", ["alan = Ulaşım", "bitiş = since + 180 gün"])
    edge(c, [ay.p("r"), ba.p("l")], head="open", label="h1 (genel)")
    edge(c, [ba.p("r"), ce.p("l")], head="open", label="h2 (Ulaşım)")
    for h in (h1, h2):
        c.line([(h.cx, h.y), (h.cx, ay.cy)], dash="3 3")
    it = obj(0, 210, "r1 : Havaleİsteği", ["veren = aylin, alan = mert", "alan_id = Ulaşım",
                                                             "durum = REJECTED"])
    it2 = obj(260, 210, "r2 : Havaleİsteği", ["veren = elif, alan = aylin", "alan_id = Kent",
                                             "durum = PENDING"])
    so = obj(520, 150, "o9 : Oylama", ["öneri = №9 Gece metro", "alan = Ulaşım",
                                      "çözülmüş: aylin → ceren,", "  baris → ceren",
                                      "açık oy: ceren (ağırlık 3)"])
    edge(c, [so.p("t", 0.5), ce.p("b", 0.5)], head="open", dash=True, label="ağırlık = 3",
         lpos=(so.cx + 36, 132), lanchor="start")
    note(c, 0, 300, ["r1 ve r2 grafa girmez: reddedilen ve bekleyen istek oylamayı etkilemez.",
                     "Ulaşım alt alanı Kent'in altındadır; aylin'in genel havalesi baris'e,",
                     "baris'in Ulaşım havalesi ceren'e gider. Zincirin sonu ceren'dir."])
    return c.done("Nesne diyagramı: Karar Saati #1'de №9 için havale zinciri")


# =====================================================================================================
# SIRALAMA DİYAGRAMLARI
# =====================================================================================================


def sd_oneri_ac() -> uml.Diagram:
    """Kaynak: routers/proposals.py POST /proposals → services/proposals.open_proposal,
    _finish_opening, run_rules; context.Ctx.commit → services/ledger.flush."""
    return sequence("Sıralama diyagramı: öneri açma", [
        ("u", "Yurttaş", "actor"), ("cl", "İstemci\nExpo", "obj"), ("f", "proposals\n«facade»", "obj"),
        ("k", "ProposalKind\n«strategy»", "obj"), ("r", "Kural zinciri\nR1–R9", "obj"),
        ("pg", "PostgreSQL", "db"), ("g", "Neo4j", "db"), ("l", "Defter\nlider", "ext")], [
        ("msg", "u", "cl", "formu gönder"),
        ("msg", "cl", "f", "POST /proposals"),
        ("on", "f"),
        ("msg", "f", "k", "prepare(ctx, user, inp)"),
        ("ret", "k", "f", "Prepared"),
        ("msg", "f", "r", "check_proposal(taslak)"),
        ("self", "r", "her halka: check → next"),
        ("ret", "r", "f", "RuleReport"),
        ("frag", "alt", "[ihlal var]", "cl", "l"),
        ("ret", "f", "cl", "422 · gerekçeler (R…)"),
        ("else", "[ihlal yok]"),
        ("self", "f", "Hâtif yorumu (H1–H4)"),
        ("self", "f", "_start_lane: ilk durum"),
        ("msg", "f", "pg", "INSERT proposals"),
        ("msg", "f", "g", "record_proposal"),
        ("msg", "f", "pg", "outbox: ONERI_ACILDI"),
        ("msg", "f", "k", "after_open(p)"),
        ("msg", "f", "pg", "COMMIT"),
        ("msg", "f", "l", "append-batch"),
        ("ret", "l", "f", "seq, hash"),
        ("ret", "f", "cl", "201 · öneri"),
        ("end",),
        ("off", "f"),
        ("ret", "cl", "u", "öneri sayfası"),
    ])


def sd_oy() -> uml.Diagram:
    """Kaynak: routers/decision_hour.py POST /decision-hour/votes → decision_hour.cast_vote, _cast."""
    return sequence("Sıralama diyagramı: Karar Saati'nde oy verme", [
        ("u", "Yurttaş", "actor"), ("cl", "İstemci", "obj"), ("d", "decision_hour", "obj"),
        ("b", "BallotMethod\n«strategy»", "obj"), ("pg", "PostgreSQL", "db"), ("l", "Defter\nlider", "ext")], [
        ("msg", "u", "cl", "EVET / HAYIR ya da metinleri onayla"),
        ("msg", "cl", "d", "POST /decision-hour/votes"),
        ("on", "d"),
        ("self", "d", "pencere açık mı, seçmen mi?"),
        ("frag", "alt", "[işaretli · oy hakkı yok · havale etti · zaten oy verdi]", "cl", "l"),
        ("ret", "d", "cl", "403 / 409 · gerekçe"),
        ("else", "[oy verebilir]"),
        ("msg", "d", "b", "normalize(seçim)"),
        ("ret", "b", "d", "geçerli seçim"),
        ("self", "d", "tuz; commit = sha256(oy belgesi ‖ tuz)"),
        ("msg", "d", "pg", "INSERT ballots"),
        ("msg", "d", "pg", "outbox: OY_MUHUR (yalnızca commit)"),
        ("msg", "d", "pg", "COMMIT"),
        ("msg", "d", "l", "append-batch"),
        ("ret", "d", "cl", "oyunuz mühürlendi"),
        ("end",),
        ("off", "d"),
    ])


def sd_kapanis() -> uml.Diagram:
    """Kaynak: jobs.CloseDecisionHour → decision_hour.close_session, _close_proposal,
    BallotMethod.close, proposals.accept, ProposalKind.apply, events.publish.
    Aboneler: petitions (dilekçe), calendar (takvim), notifications (zil)."""
    return sequence("Sıralama diyagramı: Karar Saati'nin kapanışı", [
        ("z", "Zamanlayıcı", "ext"), ("d", "decision_hour", "obj"), ("b", "BallotMethod", "obj"),
        ("f", "proposals", "obj"), ("k", "ProposalKind", "obj"), ("e", "EventBus", "obj"),
        ("s", "Aboneler", "obj"), ("pg", "PostgreSQL", "db")], [
        ("msg", "z", "d", "close_session"),
        ("on", "d"),
        ("self", "d", "restore_voted_state"),
        ("frag", "loop", "[her öneri, numara sırasıyla]", "d", "pg"),
        ("msg", "d", "b", "close(p, oylamalar)"),
        ("msg", "b", "pg", "OY_ACILDI"),
        ("self", "b", "ağırlıklı sayım"),
        ("frag", "alt", "[geçti]", "b", "pg"),
        ("msg", "b", "f", "accept_or_conflict"),
        ("self", "f", "state.accept()"),
        ("msg", "f", "k", "apply(p)"),
        ("msg", "k", "e", "publish"),
        ("msg", "e", "s", "TopicAccepted"),
        ("else", "[geçmedi]"),
        ("msg", "b", "f", "reject(p, not)"),
        ("end",),
        ("msg", "d", "pg", "OYLAMA_SONUCU"),
        ("end",),
        ("msg", "d", "e", "publish(SessionClosed)"),
        ("msg", "e", "s", "sonuç bildirimleri"),
        ("msg", "d", "pg", "OTURUM_KAPANDI, YONETMELIK_DURUMU"),
        ("off", "d"),
    ])


def sd_defter() -> uml.Diagram:
    """Kaynak: context.Ctx.commit, services/ledger.flush, HttpLedgerClient.append_batch,
    ledger/app.py /append-batch ve /replicate-batch."""
    return sequence("Sıralama diyagramı: defter yazımı ve çoğaltma", [
        ("s", "Servis\nctx.commit()", "obj"), ("pg", "PostgreSQL", "db"), ("fl", "ledger.flush", "obj"),
        ("l1", "ledger-1\nlider", "ext"), ("l2", "ledger-2\ntakipçi", "ext"), ("l3", "ledger-3\ntakipçi", "ext")], [
        ("msg", "s", "pg", "COMMIT (iş + outbox)"),
        ("msg", "s", "fl", "flush(ctx)"),
        ("on", "fl"),
        ("msg", "fl", "pg", "pg_try_advisory_xact_lock"),
        ("msg", "fl", "pg", "bekleyen outbox (id sırası)"),
        ("self", "fl", "zaman damgası azalmaz"),
        ("frag", "loop", "[200'lük parçalar]", "fl", "l3"),
        ("msg", "fl", "l1", "POST /append-batch"),
        ("self", "l1", "hash = sha256(prev ‖ yük ‖ ts ‖ tür)"),
        ("self", "l1", "SQLite: tek işlem"),
        ("msg", "l1", "l2", "POST /replicate-batch"),
        ("ret", "l2", "l1", "uç (seq)"),
        ("msg", "l1", "l3", "POST /replicate-batch"),
        ("ret", "l3", "l1", "uç (seq)"),
        ("ret", "l1", "fl", "kayıtlar (seq, hash)"),
        ("msg", "fl", "pg", "sent_at, hash satırına yaz"),
        ("end",),
        ("frag", "opt", "[lider erişilemez]", "fl", "l3"),
        ("self", "fl", "kayıtlar bekler, sonra sırayla"),
        ("end",),
        ("off", "fl"),
    ])


def sd_ifsa() -> uml.Diagram:
    """Kaynak: services/cellar.open_reveal_vote, cast_reveal_vote, _reveal; proposals.create_draft."""
    return sequence("Sıralama diyagramı: Mahzen başlığının ifşası", [
        ("u", "Başlık\nkatılımcısı", "actor"), ("c", "cellar", "obj"), ("r", "baskın\ntespiti", "obj"),
        ("pg", "PostgreSQL", "db"), ("f", "proposals\n«facade»", "obj")], [
        ("msg", "u", "c", "POST …/reveal-vote (aç)"),
        ("self", "c", "yazmış mı? açık oylama var mı?"),
        ("msg", "c", "r", "detect_raids(açılış anları)"),
        ("ret", "r", "c", "işaretliler"),
        ("msg", "c", "pg", "INSERT cellar_votes (seçmenler)"),
        ("frag", "loop", "[seçmenler oy verir ya da değiştirir]", "u", "f"),
        ("msg", "u", "c", "PUT …/reveal-vote (EVET/HAYIR)"),
        ("msg", "c", "pg", "UPSERT cellar_ballots; EVET say"),
        ("frag", "opt", "[EVET > seçmenlerin yarısı]", "c", "f"),
        ("self", "c", "başlık donar, takma adlar açılır"),
        ("msg", "c", "pg", "outbox: MAHZEN_IFSA"),
        ("msg", "c", "f", "create_draft(KONU taslağı)"),
        ("end",),
        ("ret", "c", "u", "revealed: true | false"),
        ("end",),
    ])


def com_sessiz() -> uml.Diagram:
    """İletişim diyagramı: sessiz onayla kabul ve takvime yazılma.
    Kaynak: scheduler._tick_locked → jobs.EndSilentPeriod → proposals.end_silent_period →
    accept_or_conflict → accept → ProposalKind.apply → events.publish → calendar._on_topic_accepted."""
    c = Canvas()

    def ob(x, y, t):
        b = box(c, x, y, [t], size=10.5, kinds=["serifb"], rx=0, center_x=True, fill=WHITE)
        w = tw(t, 10.5, "serifb")
        c.line([(b.cx - w / 2, b.b - 6), (b.cx + w / 2, b.b - 6)], sw=0.8)
        return b

    def lab(x, y, lines, anchor="middle"):
        for i, t in enumerate(lines):
            c.text(x, y + i * 11, t, 9.2, "serif", anchor=anchor)

    sc = ob(60, 0, ":scheduler")
    jb = ob(300, 0, ":EndSilentPeriod")
    pr = ob(580, 0, ":proposals")
    st = ob(580, 150, ":Silent")
    kd = ob(330, 150, ":TopicKind")
    bus = ob(330, 280, ":EventBus")
    cal = ob(150, 400, ":calendar")
    ntf = ob(520, 400, ":notifications")
    ldg = ob(150, 500, ":ledger outbox")
    edge(c, [sc.p("r"), jb.p("l")])
    lab((sc.r + jb.x) / 2, sc.cy - 6, ["1: run(ctx) →"])
    edge(c, [jb.p("r"), pr.p("l")])
    lab((jb.r + pr.x) / 2, jb.cy - 6, ["1.1: end_silent_period(p) →"])
    edge(c, [pr.p("b", 0.5), st.p("t", 0.5)])
    lab(pr.cx + 8, 70, ["1.1.1: accept() ↓", "Silent → Accepted"], anchor="start")
    edge(c, [pr.p("b", 0.15), kd.p("t", 0.8)])
    lab(440, 92, ["1.1.2: apply(p) ↙"], anchor="end")
    edge(c, [kd.p("b", 0.5), bus.p("t", 0.5)])
    lab(kd.cx + 8, 222, ["1.1.2.1: publish(TopicAccepted) ↓"], anchor="start")
    rx = pr.cx + 8 + tw("Silent → Accepted", 9.2) + 24
    edge(c, [pr.p("r"), (rx, pr.cy), (rx, bus.cy), bus.p("r")])
    lab(rx - 6, bus.cy - 6, ["1.1.3: publish(SilentPeriodEnded) ←"], anchor="end")
    edge(c, vh((bus.x + 18, bus.b), cal.p("t"), bus.b + 30))
    lab(bus.x + 10, bus.b + 50, ["1.1.2.1.1: _on_topic_accepted ↙"], anchor="end")
    edge(c, vh((bus.r - 18, bus.b), ntf.p("t"), bus.b + 30))
    lab(bus.r - 10, bus.b + 50, ["1.1.3.1: zile bildirim ↘"], anchor="start")
    edge(c, [cal.p("b"), ldg.p("t")])
    lab(cal.cx + 8, (cal.b + ldg.y) / 2 + 4, ["1.1.2.1.1.1: ETKINLIK_PLANLANDI ↓"], anchor="start")
    note(c, 330, 470, ["Etkinlik, başlangıç geçmemişse ve salon aynı saatte",
                       "boşsa yazılır; yoksa öneri sahibine bildirim gider.",
                       "Dilekçe aboneliği de TopicAccepted'ı alır, takvim",
                       "muhatabında bir şey yapmaz."])
    return c.done("İletişim diyagramı: sessiz onayla kabul ve takvime yazılma")


# =====================================================================================================
# DURUM DİYAGRAMLARI
# =====================================================================================================


def _lab(c: Canvas, x: float, y: float, text: str, anchor: str = "start", size: float = 9.2) -> None:
    """Geçiş etiketi (çok satırlı, beyaz zeminli)."""
    for k, t in enumerate(text.split("\n")):
        w = tw(t, size)
        x0 = x - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        c.rect(x0 - 2, y + k * (size + 2) - size * 0.85, w + 4, size + 2, fill=WHITE, stroke=WHITE, sw=0)
        c.text(x, y + k * (size + 2), t, size, anchor=anchor)


def _st(c: Canvas, cx: float, cy: float, name: str, inner: list[str] = (), **kw) -> Box:
    """Ortası (cx, cy) olan durum."""
    h = 24 + (len(inner) * 11 + 6 if inner else 0)
    return state(c, cx, cy - h / 2, name, list(inner), **kw)


def st_oneri() -> uml.Diagram:
    """Kaynak: domain/lifecycle.py (durum sınıfları, opening_state), services/proposals.py
    (object_to → escalate, end_silent_period, end_rival_period, enter_session, mark_conflict,
    share_conflicts), services/decision_hour.py (olgunlaşma denetimi, kapanış)."""
    c = Canvas()
    X0, X1, X2 = 110, 340, 590
    y1 = 56
    s0 = start_node(c, X1, 0)
    d1 = decision(c, X1, y1)
    edge(c, [s0.p("b"), d1.p("t")], head="open")
    _lab(c, X1 + 8, 32, "aç (POST /proposals) / R1–R9")
    f1 = final_node(c, X2 + 60, y1)
    edge(c, [d1.p("r"), f1.p("l")], head="open")
    _lab(c, (d1.r + f1.x) / 2, y1 - 6, "[ihlal var] / 422 ve gerekçeler; kayıt açılmaz", "middle")
    s1 = start_node(c, X0, 0)
    ta = _st(c, X0, y1, "Taslak")
    edge(c, [s1.p("b"), ta.p("t")], head="open")
    _lab(c, X0 - 8, 26, "Mahzen ifşası", "end")
    edge(c, [ta.p("r"), d1.p("l")], head="open")
    _lab(c, (ta.r + d1.x) / 2, y1 - 6, "gönder", "middle")
    y2 = 124
    d2 = decision(c, X1, y2)
    edge(c, [d1.p("b"), d2.p("t")], head="open")
    _lab(c, X1 + 8, (y1 + y2) / 2 + 3, "[ihlal yok] / Hâtif yorumu, ONERI_ACILDI")
    si = _st(c, X0, 200, "SessizOnay", ["do / itirazları say", "itiraz [< eşik] / kaydet"])
    ri = _st(c, X2, 200, "RakipSüresi", ["rakip metin [katılımcı] / ekle"])
    edge(c, [d2.p("l"), (X0, y2), si.p("t")], head="open")
    _lab(c, (X0 + d2.x) / 2, y2 - 6, "[hızlı şerit]", "middle")
    edge(c, [d2.p("r"), (X2, y2), ri.p("t")], head="open")
    _lab(c, (X2 + d2.r) / 2, y2 - 6, "[KAPANIS]", "middle")
    ku = _st(c, X1, 300, "Kuyruk", ["do / olgunlaşma süresi işler",
                                    "Karar Saati [olgun değil] / kal"])
    edge(c, [d2.p("b"), ku.p("t")], head="open")
    _lab(c, X1 + 8, 190, "[yavaş şerit]")
    xa = si.x + si.w * 0.78
    edge(c, [(xa, si.b), (xa, ku.cy), ku.p("l")], head="open")
    _lab(c, (xa + ku.x) / 2, ku.cy - 17, "itiraz [≥ eşik]\n/ yavaş şerit", "middle")
    edge(c, [ri.p("b"), (X2, ku.cy), ku.p("r")], head="open")
    _lab(c, (X2 + ku.r) / 2, ku.cy - 6, "süre doldu (48 saat)", "middle")
    oy = _st(c, X1, 400, "Oylama", ["oy / mühürle (commit)", "do / havale grafı kilitli"])
    edge(c, [ku.p("b"), oy.p("t")], head="open")
    _lab(c, X1 + 8, ku.b + 16, "Karar Saati açıldı [olgun]\n/ anlık görüntü")
    y3 = 486
    d3 = decision(c, X1, y3)
    edge(c, [oy.p("b"), d3.p("t")], head="open")
    _lab(c, X1 + 8, oy.b + 18, "pencere kapandı / oyları aç, say")
    re = _st(c, X2, y3, "Ret", ["entry / red_bekleme başlar"], final_like=True)
    edge(c, [d3.p("r"), re.p("l")], head="open")
    _lab(c, (d3.r + re.x) / 2, y3 - 6, "[eşik aşılmadı]", "middle")
    y4 = 552
    d4 = decision(c, X1, y4)
    edge(c, [d3.p("b"), d4.p("t")], head="open")
    _lab(c, X1 + 8, (y3 + y4) / 2 + 4, "[eşik aşıldı]")
    xb = si.x + si.w * 0.25
    edge(c, [(xb, si.b), (xb, y4), d4.p("l")], head="open")
    _lab(c, (xb + d4.x) / 2, y4 - 6, "süre doldu (24 saat)", "middle")
    ca = _st(c, X2, y4, "Çakışma", ["entry / uygulanmaz", "yeniden açılabilir"], final_like=True)
    edge(c, [d4.p("r"), ca.p("l")], head="open")
    _lab(c, (d4.r + ca.x) / 2, y4 - 6, "[pay hedefi eskidi]", "middle")
    ka = _st(c, X1, 630, "Kabul", ["entry / apply(p), olay yayımla"], final_like=True)
    edge(c, [d4.p("b"), ka.p("t")], head="open")
    _lab(c, X1 + 8, (y4 + ka.y) / 2 + 4, "[pay hedefleri güncel]")
    note(c, 0, 600, ["Kalın çerçeveli durumlar sondur.",
                     "Durumda geçersiz bir işlem (ör. kuyruktaki",
                     "öneriye itiraz) InvalidTransition ile",
                     "durumun kendi gerekçesiyle reddedilir."])
    return c.done("Durum diyagramı: önerinin yaşam döngüsü")


def st_havale() -> uml.Diagram:
    """Kaynak: services/delegation.py (request_delegation, accept_request, reject_request,
    cancel_request, expire_request, return_delegation, renew_delegation, expire, revoke_delegation)."""
    c = Canvas()
    yc = 130
    s0 = start_node(c, -30, yc)
    d = decision(c, 40, yc)
    edge(c, [s0.p("r"), d.p("l")], head="open")
    _lab(c, -30, yc + 24, "havale ver\n[pencere kapalı]", "start")
    bek = _st(c, 210, yc, "Bekliyor", ["do / kabul süresi (7 gün) işler"])
    edge(c, [d.p("r"), bek.p("l")], head="open")
    _lab(c, (d.r + bek.x) / 2, yc - 6, "[alan Hâtif değil]", "middle")
    yur = _st(c, 520, yc, "Yürürlükte", ["entry / HAVALE kenarı grafa", "yenile / bitiş = şimdi + 180 gün",
                                         "do / son 14 günde uyarı şeridi"])
    edge(c, [bek.p("r"), yur.p("l")], head="open")
    _lab(c, (bek.r + yur.x) / 2, yc - 6, "kabul\n[pencere kapalı]".split("\n")[0], "middle")
    _lab(c, (bek.r + yur.x) / 2, yc + 14, "[pencere kapalı]", "middle")
    top = 20
    red = _st(c, bek.cx - 62, top, "Reddedildi", final_like=True)
    sd = _st(c, bek.cx + 62, top, "KabulSüresiDoldu", final_like=True)
    edge(c, [(red.cx, bek.y), red.p("b")], head="open")
    _lab(c, red.cx - 6, 70, "ret", "end")
    edge(c, [(sd.cx, bek.y), sd.p("b")], head="open")
    _lab(c, sd.cx + 6, 70, "süre doldu\n/ zamanlayıcı")
    ip = _st(c, bek.cx, 226, "İptal", final_like=True)
    edge(c, [bek.p("b"), ip.p("t")], head="open")
    _lab(c, bek.cx + 8, bek.b + 22, "veren geri aldı | aynı alana\nyenisini verdi")
    hy = -40
    edge(c, [d.p("t"), (d.cx, hy), (yur.cx, hy), yur.p("t")], head="open")
    _lab(c, (d.cx + yur.cx) / 2, hy - 6, "[alan Hâtif] / hemen kabul", "middle")
    xi, xs = yur.x + 30, yur.r - 40
    iade = _st(c, xi, 260, "İadeEdildi", final_like=True)
    son = _st(c, xs, 330, "SonaErdi", final_like=True)
    edge(c, [(xi, yur.b), iade.p("t")], head="open")
    _lab(c, xi - 8, yur.b + 30, "iade\n[pencere kapalı]", "end")
    edge(c, [(xs, yur.b), son.p("t")], head="open")
    _lab(c, xs + 8, yur.b + 22, "geri al [pencere kapalı]\n| bitiş geldi\n  / HAVALE_SURESI_DOLDU\n"
         "| aynı alanda yenisi\n  kabul edildi")
    note(c, -30, 290, ["Grafta yalnızca Yürürlükte durumu vardır (HAVALE kenarı).",
                       "Kalın çerçeveli durumlar sondur; satır geçmiş olarak kalır."])
    return c.done("Durum diyagramı: havale isteği")


def st_mahzen() -> uml.Diagram:
    """Kaynak: services/cellar.py (create_thread, reply, sign_post, _prune, open_reveal_vote,
    cast_reveal_vote, _reveal), domain/cellar.py (should_bump, threads_to_prune, reveal_passes)."""
    c = Canvas()
    W, H = 520, 150
    c.rect(0, 0, W, H, rx=12)
    c.text(12, 17, "Yaşıyor", 10.8, "serifb")
    c.line([(0, 24), (W, 24)], dash="4 3")
    ta = _st(c, 140, 90, "Tartışılıyor", ["yanıt [< üst sınır] / yükselt", "yanıt [≥ üst sınır] / yerinde kal",
                                           "imzala / takma ad görünür"])
    io = _st(c, 405, 90, "İfşaOylamasında", ["oy / ver ya da değiştir", "yanıt / yükselt, oylama sürer"])
    edge(c, [ta.p("r"), io.p("l")], head="open")
    _lab(c, (ta.r + io.x) / 2, 72, "oylama aç [yazmış]\n/ seçmenler dondurulur", "middle")
    s0 = start_node(c, ta.cx, -50)
    edge(c, [s0.p("b"), ta.p("t")], head="open")
    _lab(c, ta.cx + 8, -26, "başlık aç [uyarı onaylı] / Gölge kimliği")
    ie = _st(c, 680, 90, "İfşaEdildi", ["başlık donar", "takma adlar açılır", "entry / MAHZEN_IFSA"],
             final_like=True)
    edge(c, [io.p("r"), ie.p("l")], head="open")
    _lab(c, (io.r + ie.x) / 2, 72, "EVET > seçmenlerin\nyarısı / KONU taslağı", "middle")
    f = final_node(c, 140, H + 60)
    edge(c, [(140, H), f.p("t")], head="open")
    _lab(c, 150, H + 24, "kapasite aşıldı [en alttaki başlık] / kalıcı silinir (açık oylamasıyla)")
    note(c, 300, H + 50, ["Yaşayan başlık deftere yazılmaz.",
                          "Silinen başlık geri gelmez (bilinçli açık)."])
    return c.done("Durum diyagramı: Mahzen başlığı")


def st_etkinlik_dilekce() -> uml.Diagram:
    """Kaynak: services/calendar.py (_on_topic_accepted, status, attend, report_refusal),
    services/petitions.py (send, _on_topic_accepted, _on_decision_made, _recipient_rows, add_reply)."""
    c = Canvas()
    package(c, 0, 0, 360, 430, "stm Etkinlik")
    x = 200
    s0 = start_node(c, x, 30)
    d = decision(c, x, 84)
    edge(c, [s0.p("b"), d.p("t")], head="open")
    _lab(c, x + 8, 54, "konu kabul edildi\n[muhatap Takvim]")
    f = final_node(c, 40, 84)
    edge(c, [d.p("l"), f.p("r")], head="open")
    _lab(c, (d.x + f.r) / 2, 70, "[başlangıç geçti |\nsalon dolu]", "middle")
    _lab(c, (d.x + f.r) / 2, 104, "/ sahibine bildirim", "middle")
    ya = _st(c, x, 190, "Yaklaşıyor", ["Geliyorum / katılım bildir", "vazgeç / geri al"])
    edge(c, [d.p("b"), ya.p("t")], head="open")
    _lab(c, x + 8, 118, "[ileride, salon boş]\n/ ETKINLIK_PLANLANDI")
    su = _st(c, x, 285, "Sürüyor", ["katılım değişmez"])
    edge(c, [ya.p("b"), su.p("t")], head="open")
    _lab(c, x + 8, (ya.b + su.y) / 2 + 4, "başlangıç anı")
    ge = _st(c, x, 375, "Gerçekleşti", ["rapor [katıldı, ilk raporu] / ekle"])
    edge(c, [su.p("b"), ge.p("t")], head="open")
    _lab(c, x + 8, (su.b + ge.y) / 2 + 4, "bitiş anı")
    X = 380
    package(c, X, 0, 370, 430, "stm Dilekçe alıcısı")
    s1 = start_node(c, X + 120, 30)
    be = _st(c, X + 120, 130, "Bekliyor", ["entry / DILEKCE_ILETILDI"])
    edge(c, [s1.p("b"), be.p("t")], head="open")
    _lab(c, X + 128, 54, "konu kabulü ya da Karar\n[muhatap kurum] / ilet")
    yt = _st(c, X + 120, 340, "Yanıtlandı", ["entry / DILEKCE_YANITI"])
    edge(c, [be.p("b"), yt.p("t")], head="open")
    _lab(c, X + 112, 230, "yanıt işlendi\n[konu katılımcısı]", "end")
    sx = X + 290
    sdo = _st(c, sx, 235, "SüreDoldu", ["“süresinde yanıt", "verilmedi”"])
    edge(c, [be.p("r"), (sx, be.cy), sdo.p("t")], head="open")
    _lab(c, (be.r + sx) / 2 + 10, be.cy - 6, "30 gün (3071 s. K.)", "middle")
    edge(c, [sdo.p("b"), (sx, yt.cy), yt.p("r")], head="open")
    _lab(c, (yt.r + sx) / 2, yt.cy - 6, "geç yanıt işlendi", "middle")
    note(c, 0, 450, ["İki makinede de durum sütunu yoktur: saatten ve kayıtlardan hesaplanır",
                     "(calendar.status, petitions._recipient_rows)."])
    return c.done("Durum diyagramları: etkinlik ve dilekçe alıcısı")


# =====================================================================================================
# ETKİNLİK DİYAGRAMLARI
# =====================================================================================================


def _timer(c: Canvas, x: float, y: float, text: str) -> Box:
    """Zaman olayı (kum saati) ve altında adı."""
    c.path(f"M{x - 7} {y - 9} H{x + 7} L{x - 7} {y + 9} H{x + 7} Z", (x - 7, y - 9, x + 7, y + 9))
    for k, t in enumerate(text.split("\n")):
        c.text(x, y + 22 + k * 11, t, 9.2, "serifi", anchor="middle", fill=SOFT)
    return Box(x - 7, y - 9, 14, 18)


def _rake(c: Canvas, b: Box) -> None:
    """Çağrı eylemi işareti (tırmık): başka bir etkinliği çağırır."""
    x, y = b.r - 14, b.b - 13
    c.line([(x, y), (x, y + 9)])
    c.line([(x - 5, y + 9), (x - 5, y + 4), (x + 5, y + 4), (x + 5, y + 9)])


def _region(c: Canvas, x: float, y: float, w: float, h: float, text: str) -> None:
    """Genişleme bölgesi (kesikli, yuvarlak köşeli); text satırları sol üstte."""
    c.rect(x, y, w, h, rx=10, fill="none", dash="5 3")
    for k, t in enumerate(["«iterative»", *text.split("\n")]):
        c.text(x + 8, y + 13 + k * 11, t, 8.8, "serifi", fill=SOFT)


def _flow(c: Canvas, a: Box, b: Box, label: str | None = None, *, lx: float | None = None) -> None:
    """Dikey akış: a'nın altından b'nin üstüne."""
    edge(c, [a.p("b"), b.p("t")], head="open")
    if label:
        _lab(c, (lx if lx is not None else a.cx + 8), (a.b + b.y) / 2 + 4, label)


def ac_oneri() -> uml.Diagram:
    """Kaynak: services/proposals.py (open_proposal, object_to, end_silent_period),
    services/decision_hour.py (open_session, cast_vote, close_session), services/scheduler.py,
    services/petitions.py ve calendar.py (abonelikler)."""
    c = Canvas()
    xs = swimlanes(c, 0, 0, [175, 270, 165, 150], 690, ["Seçmenler", "Meşveret", "Öneri sahibi",
                                                         "Zamanlayıcı"])
    S, M, Y, Z = xs
    s0 = start_node(c, Y, 40)
    a1 = action(c, Y, 58, "Öneriyi yaz: tür, kapsam,\nalan, muhatap, kaynak")
    edge(c, [s0.p("b"), a1.p("t")], head="open")
    a2 = action(c, M, a1.cy - 12.1, "R1–R9 denetimi")
    edge(c, [a1.p("l"), a2.p("r")], head="open")
    d1 = decision(c, M, 140)
    _flow(c, a2, d1)
    a3 = action(c, Y, 140 - 19.2, "Gerekçeyi oku,\nöneriyi düzelt")
    edge(c, [d1.p("r"), a3.p("l")], head="open")
    _lab(c, (d1.r + a3.x) / 2, 134, "[ihlal var]", "middle")
    edge(c, [a3.p("t"), a1.p("b")], head="open")
    a4 = action(c, M, 172, "Hâtif yorumu;\nONERI_ACILDI")
    _flow(c, d1, a4, "[ihlal yok]")
    d2 = decision(c, M, 240)
    _flow(c, a4, d2)
    a5 = action(c, S, 240 - 19.2, "İtiraz et ya da sus\n(24 saat)")
    edge(c, [d2.p("l"), a5.p("r")], head="open")
    _lab(c, (d2.x + a5.r) / 2, 234, "[hızlı şerit]", "middle")
    yq = 292
    d3 = decision(c, 212, yq)
    edge(c, [a5.p("b"), (S, yq), d3.p("l")], head="open")
    ku = action(c, M, yq - 12.1, "Kuyruğa al")
    _flow(c, d2, ku, "[yavaş şerit]")
    edge(c, [d3.p("r"), ku.p("l")], head="open")
    _lab(c, (d3.r + ku.x) / 2, yq - 6, "[≥ eşik]", "middle")
    j1 = bar(c, M - 40, 342, 80)
    _flow(c, ku, j1)
    t1 = _timer(c, Z, 342, "Pazar 20:00\n(olgun öneriler)")
    edge(c, [t1.p("l"), j1.p("r")], head="open")
    a6 = action(c, M, 364, "Oturumu aç: anlık görüntü,\nbaskın tespiti, Hâtif oyu")
    _flow(c, j1, a6)
    a7 = action(c, S, 364, "Oy ver ya da\nhavalede bırak")
    edge(c, [a6.p("l"), a7.p("r")], head="open")
    j2 = bar(c, M - 40, 446, 80)
    _flow(c, a6, j2)
    edge(c, [a7.p("b"), (S, 446), j2.p("l")], head="open")
    t2 = _timer(c, Z, 446, "pencere doldu\n(60 dakika)")
    edge(c, [t2.p("l"), j2.p("r")], head="open")
    a8 = action(c, M, 468, "Oyları aç, ağırlıkla say")
    _flow(c, j2, a8)
    yd = 528
    d4 = decision(c, M, yd)
    _flow(c, a8, d4)
    rj = action(c, M + 98, yd - 19.2, "Reddet;\nred_bekleme")
    edge(c, [d4.p("r"), rj.p("l")], head="open")
    _lab(c, (d4.r + rj.x) / 2, yd - 6, "[geçmedi]", "middle")
    f2 = final_node(c, rj.cx, rj.b + 30)
    _flow(c, rj, f2)
    ym = 580
    mg = decision(c, M, ym)
    _flow(c, d4, mg, "[geçti]")
    edge(c, [d3.p("b"), (d3.cx, yq + 26), (12, yq + 26), (12, ym), mg.p("l")], head="open")
    _lab(c, 20, yq + 42, "[24 saat doldu,\neşik aşılmadı]")
    a9 = action(c, M, 608, "Uygula; muhataba ilet:\ndilekçe, takvim, ön sayfa")
    _flow(c, mg, a9)
    f1 = final_node(c, M, 672)
    _flow(c, a9, f1)
    return c.done("Etkinlik diyagramı: bir önerinin yolu (kulvarlı)")


def ac_karar_saati() -> uml.Diagram:
    """Kaynak: services/decision_hour.open_session ve _snapshot; domain/raid.detect_raids."""
    c = Canvas()
    X = 190
    s0 = start_node(c, X, 30)
    d0 = decision(c, X, 66)
    _flow(c, s0, d0)
    f0 = final_node(c, 48, 66)
    edge(c, [d0.p("l"), f0.p("r")], head="open")
    _lab(c, (d0.x + f0.r) / 2, 60, "[açık oturum var] / 409", "middle")
    steps = ["Oylamasız farkları kaydet,\nson oylanmış hâle dön", "Yönetmeliği anlık görüntüle;\nkapanış = açılış + pencere",
             "Kuyruktaki olgun önerileri seç\n(olgunlaşmayan sonrakine kalır)"]
    prev, y = d0, 98
    for k, t in enumerate(steps):
        b = action(c, X, y, t, w=230)
        _flow(c, prev, b, "[yok]" if k == 0 else None)
        prev, y = b, b.b + 22
    ry = y
    inner = [("Seçmenleri al (oy hakkı, R5)", False), ("Baskın tespiti", True),
             ("İşaretlileri seçmenlerden çıkar", False),
             ("Havaleleri çöz\n(açılışta yürürlükte olanlar)", False),
             ("Oylamayı yaz; öneri Oylama'ya", False)]
    y = ry + 46
    for t, call in inner:
        b = action(c, X, y, t, w=210)
        if call:
            _rake(c, b)
        _flow(c, prev, b)
        prev, y = b, b.b + 18
    _region(c, 22, ry, 336, y - ry - 4, "her öneri ve orantısız\netkilenen alt kapsam")
    y += 18
    for t in ["OTURUM_ACILDI (işaretliler\nyalnızca sayıyla)", "Hâtif oyunu ver:\nR1–R9 ve H1–H4", "COMMIT; deftere gönder"]:
        b = action(c, X, y, t, w=200)
        _flow(c, prev, b)
        prev, y = b, b.b + 20
    f1 = final_node(c, X, y + 4)
    _flow(c, prev, f1)
    H = f1.b + 16
    package(c, 0, 0, 380, H, "act Karar Saati'ni aç", fill="none")

    X0 = 400
    package(c, X0, 0, 360, H, "act Baskın tespiti", fill="none")
    X = X0 + 180
    s1 = start_node(c, X, 30)
    a = action(c, X, 52, "Adaylar: son 7 günde katılan seçmenler\n(baskin_yeni_uye_suresi)", w=270)
    _flow(c, s1, a)
    d = decision(c, X, a.b + 30)
    _flow(c, a, d)
    fn = final_node(c, X0 + 330, d.cy)
    edge(c, [d.p("r"), fn.p("l")], head="open")
    _lab(c, (d.r + fn.x) / 2, d.cy - 6, "[aday yok]", "middle")
    prev, y = d, d.b + 26
    for k, t in enumerate(["Adaylar arası ETKILESIM\nağırlıklarını iki yönde topla",
                           "Ağırlığı ≥ baskin_min_agirlik (1)\nolan çiftler yönsüz kenar",
                           "Bağlı bileşenleri bul"]):
        b = action(c, X, y, t, w=230)
        _flow(c, prev, b, "[aday var]" if k == 0 else None)
        prev, y = b, b.b + 22
    ry = y
    dd = decision(c, X, ry + 44)
    _flow(c, prev, dd)
    mk = action(c, X, dd.b + 40, "Kümeyi gerekçesiyle işaretle", w=200)
    _flow(c, dd, mk, "[boyut ≥ 4 ∧ yoğunluk ≥ 1/2\n ∧ katılım yayılımı ≤ 24 saat]")
    mg = decision(c, X, mk.b + 30)
    _flow(c, mk, mg)
    xr = X0 + 316
    edge(c, [dd.p("r"), (xr, dd.cy), (xr, mg.cy), mg.p("r")], head="open")
    _lab(c, xr - 4, dd.cy - 6, "[değil]", "end")
    _region(c, X0 + 18, ry, 324, mg.b + 14 - ry, "her bileşen")
    out = action(c, X, mg.b + 36, "İşaretli kümeleri döndür", w=200)
    _flow(c, mg, out)
    f2 = final_node(c, X, out.b + 28)
    _flow(c, out, f2)
    note(c, X0 + 18, f2.b + 22, ["Eşikler yönetmelik maddesidir; değerleri",
                                 "açılıştaki anlık görüntüden okunur."])
    return c.done("Etkinlik diyagramları: Karar Saati'nin açılışı ve baskın tespiti")


# =====================================================================================================
# ZAMANLAMA DİYAGRAMI
# =====================================================================================================


def tm_hafta() -> uml.Diagram:
    """Bir haftada üç öneri, Karar Saati penceresi ve havale grafı.
    Süreler yönetmelik varsayılanlarından (domain/regulation.py): sessiz_onay_suresi 24 saat,
    olgunlasma_genis 72 saat, olgunlasma_genel 7 gün, karar_saati Pazar 20:00 ve 60 dakika.
    Olgunlaşma, itirazla yavaş şeride düşen öneride düştüğü andan sayılır (domain/maturation.py)."""
    c = Canvas()
    X0, X1, HRS = 168, 744, 132
    gap = 13

    def tx(h: float) -> float:
        return X0 + (X1 - X0) * h / HRS

    rows = [
        ("Öneri A", "geniş kapsam", ["Kabul", "Oylama", "Kuyruk", "SessizOnay", "—"],
         [(0, "—"), (12, "SessizOnay"), (33, "Kuyruk"), (116, "Oylama"), (117, "Kabul")]),
        ("Öneri B", "genel kapsam", ["Kuyruk", "—"], [(0, "—"), (82, "Kuyruk")]),
        ("Öneri C", "hızlı şerit", ["Kabul", "SessizOnay", "—"],
         [(0, "—"), (62, "SessizOnay"), (86, "Kabul")]),
        ("Karar Saati", "penceresi", ["açık", "kapalı"], [(0, "kapalı"), (116, "açık"), (117, "kapalı")]),
        ("Havale grafı", "", ["kilitli", "açık"], [(0, "açık"), (116, "kilitli"), (117, "açık")]),
    ]
    y = 30
    levels_y: dict[str, dict[str, float]] = {}
    for name, sub, levels, steps in rows:
        h = 16 + gap * (len(levels) - 1) + 16
        c.rect(0, y, X1, h, fill="none")
        c.line([(X0 - 70, y), (X0 - 70, y + h)], stroke=SOFT)
        c.text(6, y + 16, name, 10.5, "serifb")
        if sub:
            c.text(6, y + 28, sub, 9, "serifi", fill=SOFT)
        ly = {lv: y + 16 + gap * i for i, lv in enumerate(levels)}
        levels_y[name] = ly
        for lv, yy in ly.items():
            c.text(X0 - 6, yy + 3, lv, 8.8, "serifi", anchor="end", fill=SOFT)
        pts = []
        for i, (t, lv) in enumerate(steps):
            t2 = steps[i + 1][0] if i + 1 < len(steps) else HRS
            if pts:
                pts.append((tx(t), ly[lv]))
            pts += [(tx(t), ly[lv]), (tx(t2), ly[lv])]
        c.line(pts, sw=1.6)
        y += h
    bottom = y
    for t in (116, 117):
        c.line([(tx(t), 22), (tx(t), bottom)], dash="3 3", stroke=SOFT)
    _lab(c, tx(116) - 4, 16, "Pazar 20:00–21:00: Karar Saati", "end")
    edge(c, [(tx(116) - 2, 13), (tx(116.5), 13), (tx(116.5), 26)], head="filled")

    def span(row: str, lv: str, a: float, b: float, text: str, dy: float = -6) -> None:
        yy = levels_y[row][lv] + dy
        c.line([(tx(a), yy), (tx(b), yy)], sw=0.8, stroke=SOFT)
        for xx in (tx(a), tx(b)):
            c.line([(xx, yy - 3), (xx, yy + 3)], sw=0.8, stroke=SOFT)
        _lab(c, (tx(a) + tx(b)) / 2, yy + 3, text, "middle", size=8.8)

    span("Öneri A", "Kuyruk", 33, 105, "{olgunlaşma ≥ 72 saat}")
    span("Öneri A", "SessizOnay", 12, 33, "itiraz eşiği aşıldı ↓", dy=-6)
    span("Öneri C", "SessizOnay", 62, 86, "{24 saat, itirazsız}")
    _lab(c, tx(84), levels_y["Öneri B"]["Kuyruk"] + 13, "olgunlaşmadı (7 gün): oturuma alınmaz", "start", size=8.8)
    # zaman ekseni
    c.line([(X0, bottom + 8), (X1, bottom + 8)])
    days = ["Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar", "Pzt"]
    for d in range(6):
        c.line([(tx(d * 24), bottom + 4), (tx(d * 24), bottom + 12)])
        c.line([(tx(d * 24 + 12), bottom + 6), (tx(d * 24 + 12), bottom + 10)], sw=0.8)
        c.text(tx(d * 24 + (12 if d < 5 else 6)), bottom + 24, days[d], 9.2, anchor="middle")
    c.text(X0 - 6, bottom + 24, "saat →", 9, "serifi", anchor="end", fill=SOFT)
    return c.done("Zamanlama diyagramı: bir haftada üç öneri ve Karar Saati")


# =====================================================================================================
# MİMARİ: BİLEŞEN, PAKET, DAĞITIM
# =====================================================================================================

_REPO = ROOT.parent.parent


def _assembly(c: Canvas, req: tuple[float, float], prov: tuple[float, float], label: str,
              *, lpos: tuple[float, float] | None = None, at: float = 0.5) -> None:
    """Top ve yuva bağlayıcısı (yatay ya da dikey): req gerektiren, prov sağlayan uç."""
    (ax, ay), (bx, by) = req, prov
    horiz = abs(ax - bx) >= abs(ay - by)
    if horiz:
        mx, my = ax + (bx - ax) * at, ay
        sgn = 1 if bx > ax else -1
        c.line([(ax, ay), (mx - sgn * 10, my)])
        c.line([(mx + sgn * 6, my), (bx, by)])
        start, end = (mx - sgn * 3, my - 9), (mx - sgn * 3, my + 9)
        sweep = 1 if sgn > 0 else 0
    else:
        mx, my = ax, ay + (by - ay) * at
        sgn = 1 if by > ay else -1
        c.line([(ax, ay), (mx, my - sgn * 10)])
        c.line([(mx, my + sgn * 6), (bx, by)])
        start, end = (mx + 9, my - sgn * 3), (mx - 9, my - sgn * 3)
        sweep = 1 if sgn > 0 else 0
    c.circle(mx, my, 6)
    c.path(f"M{start[0]:.1f} {start[1]:.1f} A9 9 0 0 {1 - sweep} {end[0]:.1f} {end[1]:.1f}",
           (mx - 10, my - 10, mx + 10, my + 10))
    if label:
        lx, ly = lpos or (mx, my - 14)
        for k, t in enumerate(label.split("\n")):
            c.text(lx, ly + k * 10.5, t, 8.8, "serifi", anchor="middle", fill=SOFT)


def _dep(c: Canvas, pts: list, label: str | None = None, **kw) -> None:
    edge(c, pts, head="open", dash=True, label=label, lkind="serifi", lsize=8.6, **kw)


def cmp_sistem() -> uml.Diagram:
    """Kaynak: client/src (app, components, api/client.ts), api/src/mesveret (alt paketler),
    ledger/src/ledger/app.py (uç noktalar), docker-compose.yml."""
    c = Canvas()
    screens = [p for p in (_REPO / "client/src/app").rglob("*.tsx") if not p.name.startswith("_")]
    comps = list((_REPO / "client/src/components").rglob("*.tsx"))
    routers = [p for p in (_REPO / "api/src/mesveret/routers").glob("*.py")
               if p.stem not in ("__init__", "deps")]
    services = [p for p in (_REPO / "api/src/mesveret/services").glob("*.py") if p.stem != "__init__"]
    # istemci
    c.rect(0, 30, 190, 300)
    c.text(10, 47, "«subsystem»", 8.6, "serifi", fill=SOFT)
    c.text(10, 61, "İstemci (Expo)", 11, "serifb")
    sc = component(c, 14, 76, "ekranlar", [f"{len(screens)} rota (expo-router)"], w=162)
    bl = component(c, 14, 156, "bileşenler", [f"{len(comps)} dosya, iki tema"], w=162)
    ac = component(c, 14, 246, "api istemcisi", ["src/api/client.ts, JWT"], w=162)
    _dep(c, [sc.p("b", 0.3), (sc.x + sc.w * 0.3, bl.y)])
    _dep(c, [(sc.x + sc.w * 0.8, sc.b), (sc.x + sc.w * 0.8, ac.y)])
    # API
    AX, AW = 260, 300
    c.rect(AX, 0, AW, 520)
    c.text(AX + 10, 17, "«subsystem»", 8.6, "serifi", fill=SOFT)
    c.text(AX + 10, 31, "API (FastAPI, mesveret)", 11, "serifb")
    ro = component(c, 280, 46, "routers", [f"{len(routers)} modül, REST uçları"], w=160)
    sh = component(c, 452, 46, "scheduler", ["arka plan iş", "parçacığı"], w=96)
    sv = component(c, 280, 140, "services", [f"{len(services)} modül: öneri, Karar", "Saati, Mahzen, defter…"],
                   w=180)
    db = component(c, 280, 250, "db", ["SQLAlchemy", "modelleri"], w=118)
    gr = component(c, 430, 250, "graph", ["GraphStore:", "bellek içi | Neo4j"], w=118)
    dm = component(c, 330, 350, "domain", ["saf kurallar R1–R9,", "sayım, baskın"], w=130)
    ev = component(c, 280, 446, "evaluation", ["baskın tespiti", "değerlendirmesi"], w=120)
    _dep(c, [(344, ro.b), (344, sv.y)])
    _dep(c, [sh.p("b", 0.5), (sh.cx, sv.y + 18), (sv.r, sv.y + 18)])
    _dep(c, [(320, sv.b), (320, db.y)])
    _dep(c, [(445, sv.b), (445, gr.y)])
    _lab(c, 451, 226, "ctx.graph", size=8.6)
    _dep(c, [(415, sv.b), (415, dm.y)])
    _dep(c, [(455, gr.b), (455, dm.y)])
    _dep(c, [(360, ev.y), (360, dm.b)])
    # REST
    edge(c, [ac.p("r"), (210, ac.cy), (210, ro.cy)])
    _assembly(c, (210, ro.cy), (ro.x, ro.cy), "HTTP/JSON :8000", lpos=(232, ro.cy - 16), at=0.45)
    # sağ taraf
    RX = 600
    ly = sv.y + 44
    lg = component(c, RX, 0, "Defter", ["ledger-1 lider,", "ledger-2/3 takipçi;", "SQLite, hash zinciri"],
                   w=160)
    lg = Box(lg.x, lg.y, lg.w, lg.h)
    c.line([(sv.r, ly), (AX + AW, ly)], dash="5 3")
    _assembly(c, (AX + AW, ly), (RX + 20, ly), "/append-batch,\n/records, /verify", lpos=(580, ly + 22),
              at=0.5)
    c.line([(RX + 20, ly), (RX + 20, lg.b)])
    nj = component(c, RX, gr.cy - 23, "Neo4j 5", ["ontoloji, havale"], w=160, stereo="database")
    c.line([(gr.r, gr.cy), (AX + AW, gr.cy)], dash="5 3")
    _assembly(c, (AX + AW, gr.cy), (RX, gr.cy), "Bolt / Cypher", lpos=(580, gr.cy - 16))
    pg = component(c, 20, 420, "PostgreSQL 16", ["işlemsel çekirdek", "+ defter outbox"], w=160,
                   stereo="database")
    c.line([(db.x, db.cy), (268, db.cy), (268, pg.cy), (AX, pg.cy)], dash="5 3")
    _assembly(c, (AX, pg.cy), (pg.r, pg.cy), "SQL (psycopg)", lpos=(220, pg.cy - 16))
    note(c, RX, 360, ["Kesikli ok: bağımlılık", "(içe aktarma ya da çağrı).",
                      "Top: sağlanan, yuva: gereken", "arayüz."])
    return c.done("Bileşen diyagramı: istemci, API, defter ve veritabanları")


def pkg_bagimlilik() -> uml.Diagram:
    """Kaynak: sema.json (mesveret alt paketleri arasındaki içe aktarmalar, sema.py üretir).
    Üç ve daha çok satırlık bağımlılıklar çizilir; tamamı DSM tablosundadır."""
    c = Canvas()
    P = SEMA["packages"]
    common = {"config", "errors", "data"}
    pos = {
        "devserver": (40, 0), "main": (320, 0), "cli": (590, 0),
        "routers": (190, 100), "evaluation": (560, 100),
        "services": (330, 200),
        "context": (90, 300), "db": (330, 300), "graph": (500, 300), "clock": (640, 300),
        "domain": (330, 410),
    }
    assert set(pos) | common == set(P["units"]), set(P["units"]) - set(pos) - common
    boxes = {}

    def pk(u: str, x: float, y: float) -> Box:
        w = tw(u, 10.5, "monob") + 30
        c.rect(x, y - 12, min(w * 0.45, 40), 12, fill=WASH)
        c.rect(x, y, w, 30)
        c.text(x + w / 2, y + 19, u, 10.5, "monob", anchor="middle")
        return Box(x, y, w, 30)

    for u, (x, y) in pos.items():
        boxes[u] = pk(u, x, y)

    def clip(b: Box, toward: tuple[float, float]) -> tuple[float, float]:
        dx, dy = toward[0] - b.cx, toward[1] - b.cy
        t = min(b.w / 2 / abs(dx) if dx else 1e9, (b.h / 2 + (12 if dy < 0 else 0)) / abs(dy) if dy else 1e9)
        return (b.cx + dx * t, b.cy + dy * t)

    for u, deps in P["deps"].items():
        for v, n in deps.items():
            if v in common or n < 3:
                continue
            a, b = boxes[u], boxes[v]
            p1, p2 = clip(a, (b.cx, b.cy)), clip(b, (a.cx, a.cy))
            edge(c, [p1, p2], head="open", dash=True)
            mx, my = p1[0] + (p2[0] - p1[0]) * 0.5, p1[1] + (p2[1] - p1[1]) * 0.5
            c.rect(mx - 9, my - 7, 18, 12, fill=WHITE, stroke=WHITE, sw=0)
            c.text(mx, my + 3, str(n), 8.6, "mono", anchor="middle", fill=SOFT)
    y = 490
    c.text(0, y, "ortak paketler (hemen her paket kullanır):", 9, "serifi", fill=SOFT)
    x = 0
    for u in sorted(common):
        b = pk(u, x, y + 22)
        x = b.r + 14
    note(c, 300, y - 6, ["Ok: içe aktarma; sayı: içe aktaran satır sayısı (≥ 3).",
                         "1–2 satırlık bağımlılıklar ve ortak paketler DSM",
                         "tablosundadır. domain hiçbir pakete bağımlı değildir."])
    return c.done("Paket diyagramı: mesveret alt paketleri arasındaki bağımlılıklar")


def dep_dagitim() -> uml.Diagram:
    """Kaynak: docker-compose.yml, api/Dockerfile, ledger/Dockerfile, client/package.json, DEMO.md."""
    c = Canvas()
    node3d(c, 0, 14, 572, 560, "«device» Geliştirme bilgisayarı (Linux)")
    node3d(c, 14, 150, 540, 410, "«execution environment» Docker Compose", d=6)

    def cont(x, y, w, h, name, sub, arts):
        b = node3d(c, x, y, w, h, name, d=5, sub=sub)
        yy = y + 36
        for a, s_ in arts:
            ab = uml.artifact(c, x + 8, yy, a, w=w - 16, sub=s_)
            yy = ab.b + 6
        return b

    def lab(x, y, text, anchor="start"):
        for k, t in enumerate(text.split("\n")):
            _lab(c, x, y + k * 10.5, t, anchor, size=8.6)

    br = node3d(c, 30, 52, 200, 70, "«device» Tarayıcı", d=5, sub="localhost:8081")
    me = node3d(c, 300, 52, 236, 82, "«execution env.» Node 26", d=5, sub="Expo Metro · :8081")
    uml.artifact(c, 308, 92, "istemci paketi", w=220, sub="Expo 57, React Native 0.86")
    api = cont(30, 188, 200, 120, "api", "python:3.12-slim · :8000",
               [("mesveret (uvicorn)", "FastAPI, ENV=dev"), ("zamanlayıcı", "arka plan iş parçacığı")])
    pg = cont(30, 330, 200, 92, "postgres", "postgres:16-alpine · 5433→5432", [("pgdata", "kalıcı birim")])
    nj = cont(30, 446, 200, 92, "neo4j", "neo4j:5-community · 7474, 7687", [("neo4jdata", "kalıcı birim")])
    l1 = cont(300, 188, 236, 92, "ledger-1 «lider»", "python:3.12-slim · 8101→8100",
              [("ledger (uvicorn) + ledger1", "SQLite, yalnızca ekleme")])
    l2 = cont(300, 330, 236, 92, "ledger-2 «takipçi»", "8102→8100", [("ledger + ledger2", "SQLite")])
    l3 = cont(300, 446, 236, 92, "ledger-3 «takipçi»", "8103→8100", [("ledger + ledger3", "SQLite")])
    ph = node3d(c, 600, 52, 150, 70, "«device» Android", d=5, sub="Expo Go 57")
    c.line([(br.r, 87), (me.x, 87)])
    lab(br.r + 8, 81, "paket")
    c.line([(100, br.b), (100, api.y)])
    lab(106, br.b + 14, "HTTP/JSON :8000")
    c.line([(ph.x, 87), (me.r, 87)])
    lab(me.r + 6, 81, "LAN")
    c.line([(ph.cx, ph.b), (ph.cx, 140), (190, 140), (190, api.y)])
    lab(560, 136, "LAN :8000", "end")
    c.line([(api.r, 218), (l1.x, 218)])
    lab(api.r + 6, 210, "HTTP\n/append-batch")
    c.line([(api.r, 268), (282, 268), (282, l3.cy), (l3.x, l3.cy)])
    c.line([(282, l2.cy), (l2.x, l2.cy)])
    lab(286, l2.y - 14, "GET /verify")
    c.line([(api.r, 296), (252, 296), (252, nj.cy), (api.r, nj.cy)])
    lab(248, nj.cy - 6, "Bolt\n7687", "end")
    c.line([(api.cx - 30, api.b), (api.cx - 30, pg.y)])
    lab(api.cx - 24, api.b + 14, "TCP 5432")
    c.line([(l1.cx, l1.b), (l1.cx, l2.y)])
    lab(l1.cx + 6, l1.b + 16, "HTTP /replicate-batch")
    c.line([(l1.r - 16, l1.b), (l1.r - 16, 300), (546, 300), (546, l3.cy), (l3.r, l3.cy)])
    return c.done("Dağıtım diyagramı: Docker Compose yığını ve istemciler")


# =====================================================================================================
# VARLIK–İLİŞKİ (PostgreSQL) ve GRAF ŞEMASI (Neo4j)
# Kaynak: sema.json (db/models.py'nin SQLAlchemy metadata'sı), graph/neo4j_store.py.
# Gösterim: kaz ayağı; PK birincil, FK yabancı anahtar, U tekil; "?" boş olabilir.
# =====================================================================================================


def _cols(table: str, keep: list[str], inside: set[str]) -> tuple[list[tuple[str, str]], int]:
    t = SEMA["tables"][table]
    single_u = {u[0] for u in t["unique"] if len(u) == 1}
    by = {cc["name"]: cc for cc in t["columns"]}
    cols, shown = [], set()
    for cc in t["columns"]:
        if cc["pk"]:
            cols.append(("PK", cc["name"]))
            shown.add(cc["name"])
    for cc in t["columns"]:
        if cc["fk"] and not cc["pk"]:
            tgt = cc["fk"][0].split(".")[0]
            n = cc["name"] + ("?" if cc["null"] else "") + ("" if tgt in inside else f" → {tgt}")
            cols.append(("FK", n))
            shown.add(cc["name"])
    for k in keep:
        cols.append(("U" if k in single_u else "", k + ("?" if by[k]["null"] else "")))
        shown.add(k)
    seen = set()
    for u in t["unique"]:
        if len(u) < 2 or tuple(u) in seen:
            continue
        seen.add(tuple(u))
        line = ""
        for i, part in enumerate(u):
            piece = part + ("+" if i < len(u) - 1 else "")
            if line and len(line) + len(piece) > 24:
                cols.append(("U" if not any(r[0] == "U" and r[1].startswith("(") for r in cols[-1:]) and
                             not line.startswith(" ") else "", line))
                line = " " + piece
            else:
                line += piece
        cols.append(("U" if not line.startswith(" ") else "", line))
    return cols, len(t["columns"]) - len(shown)


def _ent(c: Canvas, x: float, y: float, table: str, keep: list[str] = (), *, inside: set[str] = frozenset(),
         w: float | None = None) -> Box:
    cols, more = _cols(table, list(keep), set(inside))
    return entity(c, x, y, table, cols, more=more, w=w)


def _ry(b: Box, i: int) -> float:
    """Varlığın i. satırının ortası (0: PK satırı)."""
    return b.y + 18 + 10.5 + i * 11.6 - 3.2


def _rel(c: Canvas, pts: list, child: str, col: str) -> None:
    """Yabancı anahtar ilişkisi: pts çocuktan ebeveyne."""
    t = SEMA["tables"][child]
    cc = next(x for x in t["columns"] if x["name"] == col)
    assert cc["fk"], (child, col)
    parent = "crow_zero_one" if cc["null"] else "crow_one"
    kid = "crow_zero_one" if [col] in t["unique"] else "crow_many"
    edge(c, pts, head=parent, tail=kid)


def er_kimlik() -> uml.Diagram:
    c = Canvas()
    ins = {"users"}
    us = _ent(c, 290, 40, "users", ["nickname", "nickname_key", "email", "full_name", "birth_date",
                                    "city_scope_id", "role", "refuses_delegations"], inside=ins)
    vc = _ent(c, 0, 20, "verification_codes", ["code", "used_at"], inside=ins)
    nt = _ent(c, 0, 150, "notifications", ["kind", "link", "read_at"], inside=ins)
    dr = _ent(c, 560, 0, "delegation_requests", ["area_id", "status", "decide_by"], inside=ins)
    md = _ent(c, 560, 160, "media", ["sha256", "alt", "attached_kind", "attached_id"], inside=ins)
    _rel(c, [(vc.r, _ry(vc, 1)), (us.x, _ry(vc, 1))], "verification_codes", "user_id")
    _rel(c, [(nt.r, _ry(nt, 1)), (us.x, _ry(nt, 1))], "notifications", "user_id")
    _rel(c, [(dr.x, _ry(dr, 1)), (us.r, _ry(dr, 1))], "delegation_requests", "giver_id")
    _rel(c, [(dr.x, _ry(dr, 2)), (us.r, _ry(dr, 2))], "delegation_requests", "target_id")
    _rel(c, [(md.x, _ry(md, 1)), (us.r, _ry(md, 1))], "media", "owner_id")
    n_users = sum(1 for t in SEMA["tables"].values() for cc in t["columns"]
                  for f in cc["fk"] if f.startswith("users."))
    note(c, 0, 270, [f"users'a toplam {n_users} yabancı anahtar bağlanır; öteki şemalarda",
                     "çizilmez, sütun adının yanında \"→ users\" yazar.",
                     "PK birincil, FK yabancı, U tekil anahtar; \"?\" boş olabilir."])
    return c.done("Varlık–ilişki diyagramı: kimlik ve kişisel kayıtlar")


def er_oneri() -> uml.Diagram:
    c = Canvas()
    ins = {"proposals", "objections", "closure_texts", "decisions", "dissents", "decision_sessions",
           "session_items", "ballots", "dev_vote_plan"}
    pr = _ent(c, 270, 130, "proposals", ["type", "status", "lane", "scope_id", "area_id", "target_key",
                                          "session_id"], inside=ins)
    ob = _ent(c, 0, 0, "objections", [], inside=ins)
    ct = _ent(c, 0, 130, "closure_texts", ["text"], inside=ins)
    de = _ent(c, 0, 260, "decisions", ["text"], inside=ins)
    di = _ent(c, 0, 400, "dissents", ["text"], inside=ins)
    ds = _ent(c, 540, 0, "decision_sessions", ["scheduled_for", "opened_at", "closes_at", "status",
                                                "regulation"], inside=ins)
    si = _ent(c, 540, 150, "session_items", ["vote_scope_id", "eligible", "resolved", "flagged"],
              inside=ins)
    bl = _ent(c, 540, 340, "ballots", ["vote_scope_id", "choice", "salt", "commit"], inside=ins)
    dv = _ent(c, 290, 380, "dev_vote_plan", ["choice"], inside=ins)
    _rel(c, [(ob.r, _ry(ob, 1)), (240, _ry(ob, 1)), (240, _ry(pr, 1)), (pr.x, _ry(pr, 1))], "objections",
         "proposal_id")
    _rel(c, [(ct.r, _ry(ct, 1)), (pr.x, _ry(ct, 1))], "closure_texts", "proposal_id")
    _rel(c, [(de.r, _ry(de, 2)), (250, _ry(de, 2)), (250, _ry(pr, 8)), (pr.x, _ry(pr, 8))], "decisions",
         "proposal_id")
    _rel(c, [(30, de.y), (30, ct.b)], "decisions", "closure_text_id")
    _rel(c, [(30, di.y), (30, de.b)], "dissents", "decision_id")
    _rel(c, [(di.x, _ry(di, 3)), (-16, _ry(di, 3)), (-16, _ry(ct, 3)), (ct.x, _ry(ct, 3))], "dissents",
         "closure_text_id")
    _rel(c, [(570, si.y), (570, ds.b)], "session_items", "session_id")
    _rel(c, [(si.x, _ry(si, 2)), (pr.r, _ry(si, 2))], "session_items", "proposal_id")
    xr = max(bl.r, ds.r, si.r) + 16
    _rel(c, [(bl.r, _ry(bl, 1)), (xr, _ry(bl, 1)), (xr, _ry(ds, 3)), (ds.r, _ry(ds, 3))], "ballots",
         "session_id")
    _rel(c, [(bl.x, _ry(bl, 2)), (500, _ry(bl, 2)), (500, _ry(pr, 9)), (pr.r, _ry(pr, 9))], "ballots",
         "proposal_id")
    _rel(c, [(dv.cx, dv.y), (dv.cx, pr.b)], "dev_vote_plan", "proposal_id")
    note(c, 0, 530, ["proposals.session_id yabancı anahtar değildir (mantıksal başvuru);",
                     "Karar Saati oylaması session_items ve ballots üzerinden bağlanır."])
    return c.done("Varlık–ilişki diyagramı: öneri, Karar ve Karar Saati")


def er_tartisma() -> uml.Diagram:
    c = Canvas()
    ins = {"topics", "messages", "message_versions", "calendar_events", "event_attendance",
           "event_reports", "petitions", "petition_replies"}
    to = _ent(c, 250, 120, "topics", ["title", "area_id", "owner_scope_id", "status", "addressee",
                                      "accepted_proposal_id"], inside=ins)
    me = _ent(c, 0, 120, "messages", ["is_opening", "current_version", "deleted_by_proposal_id"],
              inside=ins)
    mv = _ent(c, 0, 300, "message_versions", ["version_no", "text", "via_proposal_id"], inside=ins)
    ce = _ent(c, 520, 0, "calendar_events", ["title", "starts_at", "ends_at", "venue_kind"], inside=ins)
    ea = _ent(c, 520, 170, "event_attendance", [], inside=ins)
    er = _ent(c, 520, 280, "event_reports", ["text", "headcount"], inside=ins)
    pe = _ent(c, 250, 330, "petitions", ["kind", "addressee", "recipients", "subject", "sent_at"],
              inside=ins)
    pp = _ent(c, 250, 510, "petition_replies", ["recipient_id", "replied_on", "reference"], inside=ins)
    _rel(c, [(me.r, _ry(me, 1)), (to.x, _ry(me, 1))], "messages", "topic_id")
    _rel(c, [(me.x, _ry(me, 3)), (-14, _ry(me, 3)), (-14, _ry(me, 0)), (me.x, _ry(me, 0))], "messages",
         "reply_to_id")
    _rel(c, [(30, mv.y), (30, me.b)], "message_versions", "message_id")
    _rel(c, [(to.r, _ry(to, 1)), (to.r + 30, _ry(to, 1)), (to.r + 30, to.y - 14), (to.r - 30, to.y - 14),
             (to.r - 30, to.y)], "topics", "parent_id")
    _rel(c, [(ce.x, _ry(ce, 1)), (480, _ry(ce, 1)), (480, _ry(to, 4)), (to.r, _ry(to, 4))],
         "calendar_events", "topic_id")
    _rel(c, [(550, ea.y), (550, ce.b)], "event_attendance", "event_id")
    xr = max(ce.r, er.r, ea.r) + 16
    _rel(c, [(er.r, _ry(er, 1)), (xr, _ry(er, 1)), (xr, _ry(ce, 3)), (ce.r, _ry(ce, 3))], "event_reports",
         "event_id")
    _rel(c, [(pe.cx, pe.y), (pe.cx, to.b)], "petitions", "topic_id")
    _rel(c, [(pp.cx, pp.y), (pp.cx, pe.b)], "petition_replies", "petition_id")
    note(c, 0, 470, ["calendar_events.topic_id tekildir:", "bir konunun en çok bir etkinliği olur.",
                     "topics.accepted_proposal_id ve", "messages.deleted_by_proposal_id",
                     "mantıksal başvurudur."])
    return c.done("Varlık–ilişki diyagramı: tartışma, takvim ve dilekçe")


def er_mahzen() -> uml.Diagram:
    c = Canvas()
    ins = {"cellar_threads", "cellar_posts", "cellar_votes", "cellar_ballots"}
    th = _ent(c, 0, 0, "cellar_threads", ["title", "bumped_at", "reply_count", "frozen", "revealed_at",
                                          "draft_proposal_id"], inside=ins)
    po = _ent(c, 0, 180, "cellar_posts", ["text", "signed"], inside=ins)
    vo = _ent(c, 230, 0, "cellar_votes", ["electorate", "flagged", "status", "passed_at"], inside=ins)
    ba = _ent(c, 230, 180, "cellar_ballots", ["yes", "updated_at"], inside=ins)
    _rel(c, [(30, po.y), (30, th.b)], "cellar_posts", "thread_id")
    _rel(c, [(vo.x, _ry(vo, 1)), (th.r, _ry(vo, 1))], "cellar_votes", "thread_id")
    _rel(c, [(260, ba.y), (260, vo.b)], "cellar_ballots", "vote_id")
    X = 450
    c.text(X, -6, "Yabancı anahtarı olmayan işletim tabloları", 9.2, "serifi", fill=SOFT)
    lo = _ent(c, X, 4, "ledger_outbox", ["type", "payload", "ts", "sent_at", "ledger_seq", "ledger_hash",
                                         "ref_table", "ref_id"])
    rc = _ent(c, X + lo.w + 14, 4, "regulation_changes", ["key", "old_value", "new_value", "proposal_id"])
    y = max(lo.b, rc.b) + 14
    sm = _ent(c, X, y, "sim_clock", ["offset_us", "frozen_at"])
    ss = _ent(c, X + lo.w + 14, y, "scheduler_state", ["last_tick_at"])
    _ent(c, X + lo.w + 14, ss.b + 10, "demo_state", ["step"])
    note(c, 0, 300, ["Yaşayan başlık deftere yazılmaz; ifşada başlık donar",
                     "(frozen) ve draft_proposal_id KONU taslağını gösterir.",
                     "Kapasite aşılınca cellar_threads satırı ve ona bağlı",
                     "satırlar kalıcı silinir."])
    return c.done("Varlık–ilişki diyagramı: Mahzen ve işletim tabloları")


def gs_neo4j() -> uml.Diagram:
    """Kaynak: graph/neo4j_store.py (MERGE/CREATE kalıpları ve kısıtlar)."""
    c = Canvas()

    def gn(x, y, label, props, w=None):
        lines_w = [tw(label, 11, "monob")] + [tw(p, 8.8, "mono") for p in props]
        width = w or max(lines_w) + 22
        h = 22 + len(props) * 11.5 + 6
        c.rect(x, y, width, h, rx=12)
        c.text(x + width / 2, y + 15, label, 11, "monob", anchor="middle")
        c.line([(x + 6, y + 21), (x + width - 6, y + 21)], stroke=SOFT, sw=0.6)
        ty = y + 32
        for pr_ in props:
            c.text(x + 10, ty, pr_, 8.8, "mono", fill=SOFT)
            ty += 11.5
        return Box(x, y, width, h)

    def rel(pts, name, lpos=None, anchor="middle"):
        edge(c, pts, head="filled")
        if name:
            x, y = lpos or ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2 - 5)
            for k, t in enumerate(name.split("\n")):
                w = tw(t, 8.8, "mono" if k else "monob")
                x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
                c.rect(x0 - 2, y - 8 + k * 11, w + 4, 11, fill=WHITE, stroke=WHITE, sw=0)
                c.text(x, y + k * 11, t, 8.8, "mono" if k else "monob", anchor=anchor,
                       fill=INK if k == 0 else SOFT)

    def loop(b, side, name, lines=None):
        if side == "t":
            x0, x1 = b.x + b.w * 0.3, b.x + b.w * 0.7
            edge(c, [(x0, b.y), (x0, b.y - 22), (x1, b.y - 22), (x1, b.y)], head="filled")
            rel_lbl = ((x0 + x1) / 2, b.y - 27)
        elif side == "l":
            y0, y1 = b.y + b.h * 0.3, b.y + b.h * 0.75
            edge(c, [(b.x, y0), (b.x - 22, y0), (b.x - 22, y1), (b.x, y1)], head="filled")
            rel_lbl = (b.x - 26, (y0 + y1) / 2)
        else:
            x0, x1 = b.x + b.w * 0.3, b.x + b.w * 0.7
            edge(c, [(x0, b.b), (x0, b.b + 22), (x1, b.b + 22), (x1, b.b)], head="filled")
            rel_lbl = ((x0 + x1) / 2, b.b + 36)
        x, y = rel_lbl
        anchor = "end" if side == "l" else "middle"
        for k, t in enumerate([name, *(lines or [])]):
            c.text(x, y + k * 11 - (0 if side != "l" else 6), t, 8.8, "monob" if k == 0 else "mono",
                   anchor=anchor, fill=INK if k == 0 else SOFT)

    us = gn(110, 200, ":User", ["id (tekil)", "takma_ad, rol"])
    ka = gn(330, 30, ":Kapsam", ["id (tekil)", "tur, ad, alt_tur, deger"])
    ky = gn(560, 30, ":Kaynak", ["id (tekil)", "tur: ALAN | KONU |", "  YONETMELIK_MADDESI | ORTAK",
                                 "bolunebilir, paylar_json"], w=150)
    on = gn(330, 140, ":Oneri", ["id (tekil)", "tur, durum"])
    ko = gn(560, 200, ":Konu", ["ek etiket: Kaynak:Konu"], w=150)
    al = gn(560, 320, ":Alan", ["id (tekil)", "ad, anahtar_kelimeler"], w=150)
    ym = gn(560, 440, ":YonetmelikMaddesi", ["anahtar (tekil)", "deger_json, degistirilemez",
                                              "ek etiket: Kaynak"], w=150)
    kr = gn(330, 300, ":Karar", ["id (tekil)"])
    di = gn(110, 420, ":Diskur", ["id (tekil): Mahzen", "başlığı"])
    rel([(us.cx, us.y), (us.cx, ka.cy), (ka.x, ka.cy)], "UYE\n{since, neden}", lpos=(240, ka.cy - 8))
    loop(ka, "t", "ALT_KUMESI")
    rel([(ky.x, ka.cy), (ka.r, ka.cy)], "SAHIBI")
    rel([(on.cx, on.y), (on.cx, ka.b)], "SECMEN", lpos=(on.cx + 6, (on.y + ka.b) / 2 + 4), anchor="start")
    rel([(on.r, on.y + 10), (ky.x + 20, on.y + 10), (ky.x + 20, ky.b)], "ETKILER", lpos=(ky.x - 30, on.y + 5))
    loop(us, "l", "HAVALE", ["{since, alan_id,", " bitis}"])
    loop(us, "b", "ETKILESIM", ["{agirlik}"])
    edge(c, [(ko.r - 10, ko.y), (ko.r - 10, ky.b)], head="tri", dash=True)
    xr = ky.r + 14
    edge(c, [(ym.r, ym.y + 14), (xr, ym.y + 14), (xr, ky.y + 20), (ky.r, ky.y + 20)], head="tri", dash=True)
    loop(ko, "t", "ALT_KONUSU")
    rel([(ko.x + 20, ko.b), (ko.x + 20, al.y)], "ALANINDA", lpos=(ko.x + 26, (ko.b + al.y) / 2 + 4),
        anchor="start")
    loop(al, "l", "ALT_ALANI")
    rel([(kr.r, kr.y + 14), (520, kr.y + 14), (520, ko.cy), (ko.x, ko.cy)], "KONUSU",
        lpos=(516, kr.y + 9), anchor="end")
    rel([(us.x + 14, us.b), (us.x + 14, di.y)], "YAZDI {ilk}", lpos=(us.x + 18, di.y - 12), anchor="start")
    note(c, 0, 530, ["Dolu ok: ilişki (yönlü). Kesikli üçgen: ek etiket (aynı düğüm iki etiket taşır).",
                     "Kısıtlar: User, Alan, Kapsam, Kaynak, Oneri, Karar, Diskur için id;",
                     "YonetmelikMaddesi için anahtar tekildir (ensure_constraints)."])
    return c.done("Graf şeması: Neo4j düğüm etiketleri ve ilişkiler")


# =====================================================================================================
# VERİ AKIŞ DİYAGRAMLARI (Gane–Sarson)
# Kaynak: routers/*.py (girdiler), services/*.py (süreçler), db/models.py ve graph/ (depolar).
# =====================================================================================================


def _clip(b: Box, toward: tuple[float, float]) -> tuple[float, float]:
    dx, dy = toward[0] - b.cx, toward[1] - b.cy
    if dx == dy == 0:
        return (b.cx, b.cy)
    t = min(b.w / 2 / abs(dx) if dx else 1e9, b.h / 2 / abs(dy) if dy else 1e9)
    return (b.cx + dx * t, b.cy + dy * t)


def _flow2(c: Canvas, a: Box, b: Box, label: str = "", *, both: bool = False, off: float = 0,
           at: float = 0.5, pa: tuple | None = None, pb: tuple | None = None, anchor: str = "middle",
           ldx: float = 0, ldy: float = 0) -> None:
    """Veri akışı: a'dan b'ye düz çizgi (pa/pb verilirse o noktalardan)."""
    p1 = pa or _clip(a, (b.cx, b.cy + off))
    p2 = pb or _clip(b, (a.cx, a.cy + off))
    edge(c, [p1, p2], head="filled", tail="filled" if both else None)
    if label:
        mx, my = p1[0] + (p2[0] - p1[0]) * at + ldx, p1[1] + (p2[1] - p1[1]) * at + ldy
        n = label.count("\n")
        _lab(c, mx, my - n * 5 + 3, label, anchor, size=8.6)


def _pair(c: Canvas, a: Box, b: Box, ab: str, ba: str, *, gap: float = 6, at: float = 0.5,
          ab_d: float = 14, ba_d: float = 14) -> None:
    """İki yönlü veri akışı: paralel iki çizgi; ab (a→b) bir yanda, ba (b→a) öteki yanda."""
    ux, uy = uml._unit((a.cx, a.cy), (b.cx, b.cy))
    px, py = -uy * gap, ux * gap
    for sgn, (src, dst), text, dd in ((1, (a, b), ab, ab_d), (-1, (b, a), ba, ba_d)):
        p1 = _clip(src, (dst.cx + sgn * px, dst.cy + sgn * py))
        p2 = _clip(dst, (src.cx + sgn * px, src.cy + sgn * py))
        p1 = (p1[0] + sgn * px, p1[1] + sgn * py)
        p2 = (p2[0] + sgn * px, p2[1] + sgn * py)
        edge(c, [p1, p2], head="filled")
        if text:
            mx, my = (a.cx + (b.cx - a.cx) * at, a.cy + (b.cy - a.cy) * at)
            side = sgn if (ux >= 0) else -sgn
            lx, ly = mx + (-uy) * dd * side, my + ux * dd * side
            n = text.count("\n")
            _lab(c, lx, ly - n * 5 + 3, text, "middle", size=8.6)


def dfd_baglam() -> uml.Diagram:
    c = Canvas()
    p0 = dfd_process(c, 290, 120, "0", "Meşveret", w=170)
    yu = dfd_entity(c, 0, 20, "Yurttaş")
    zi = dfd_entity(c, 0, 270, "Ziyaretçi")
    ku = dfd_entity(c, 640, 20, "Kurum\n(muhatap)")
    ta = dfd_entity(c, 640, 260, "Takvim\nuygulaması")
    _pair(c, yu, p0, "kayıt, öneri, itiraz, oy, havale,\nmesaj, Mahzen yazısı, kurum yanıtı",
          "gerekçeli ret, sonuç,\nbildirim, doğrulama kodu", ab_d=26, ba_d=22)
    _pair(c, zi, p0, "okuma, arama,\ndoğrulama isteği", "ön sayfa, defter kayıtları,\ndoğrulama raporu",
          ab_d=22, ba_d=24)
    _flow2(c, p0, ku, "dilekçe (TALEP, KARAR)", ldy=-10)
    _flow2(c, p0, ta, "etkinlikler (.ics)", ldy=12)
    note(c, 250, 330, ["Kurumun yanıtı sisteme bir konu katılımcısının",
                       "elinden girer (Yurttaş akışında \"kurum yanıtı\")."])
    return c.done("Veri akış diyagramı: bağlam (düzey 0)")


def dfd_duzey1() -> uml.Diagram:
    c = Canvas()
    W = 130
    p1 = dfd_process(c, 110, 0, "1.0", "Hesap ve\nüyelik", w=W)
    p2 = dfd_process(c, 110, 154, "2.0", "Öneri ve kural\ndenetimi", w=W)
    p4 = dfd_process(c, 110, 280, "4.0", "Havale", w=W)
    p5 = dfd_process(c, 110, 390, "5.0", "Tartışma ve\nMahzen", w=W)
    p6 = dfd_process(c, 480, 60, "6.0", "Sonuç ve\niletim", w=120)
    p3 = dfd_process(c, 480, 160.5, "3.0", "Karar Saati", w=120)
    p7 = dfd_process(c, 480, 330, "7.0", "Defter", w=120)
    ya = dfd_entity(c, 0, 86, "Yurttaş")
    yb = dfd_entity(c, 0, 336, "Yurttaş")
    yr = dfd_entity(c, 650, 230, "Yurttaş")
    for e in (yb, yr):
        c.line([(e.x + 3, e.y + 10), (e.x + 10, e.y + 3)], sw=1)
    ku = dfd_entity(c, 650, 64, "Kurum")
    ta = dfd_entity(c, 650, 124, "Takvim\nuyg.")
    zi = dfd_entity(c, 650, 336, "Ziyaretçi")
    d1 = dfd_store(c, 290, 16, "D1", "Kullanıcılar", w=140)
    d3 = dfd_store(c, 290, 170, "D3", "Öneriler ve oylar", w=140)
    d2 = dfd_store(c, 290, 290, "D2", "Ontoloji grafı", w=140)
    d4 = dfd_store(c, 290, 406, "D4", "İçerik ve Mahzen", w=140)
    d5 = dfd_store(c, 480, 0, "D5", "Sonuçlar", w=120)
    d6 = dfd_store(c, 480, 260, "D6", "Defter outbox", w=120)
    d7 = dfd_store(c, 480, 410, "D7", "Zincir ×3", w=120)
    _flow2(c, ya, p1, "kayıt, giriş", ldx=-4, ldy=-4, anchor="end")
    _flow2(c, ya, p2, "öneri, itiraz /\ngerekçe", both=True, ldx=-4, ldy=12, anchor="end")
    _flow2(c, yb, p4, "havale", ldx=-4, ldy=-4, anchor="end")
    _flow2(c, yb, p5, "mesaj, yazı,\nifşa oyu", ldx=-4, ldy=12, anchor="end")
    _flow2(c, p1, d1, "", both=True, pa=(p1.r, d1.cy), pb=(d1.x, d1.cy))
    _flow2(c, p2, d3, "", both=True, pa=(p2.r, d3.cy), pb=(d3.x, d3.cy))
    _flow2(c, d3, p3, "kuyruk /\noy, sonuç", both=True, pa=(d3.r, d3.cy), pb=(p3.x, d3.cy), ldy=-14)
    _flow2(c, p4, d2, "HAVALE", both=True, pa=(p4.r, d2.cy), pb=(d2.x, d2.cy), ldy=-6)
    _flow2(c, p5, d4, "", both=True, pa=(p5.r, d4.cy), pb=(d4.x, d4.cy))
    _flow2(c, d2, p2, "kapsam,\nsahiplik", pa=(d2.x + 14, d2.y), pb=(p2.r, p2.b - 8), at=0.5, ldx=6,
           anchor="start")
    _flow2(c, d2, p3, "seçmen, havale,\nyönetmelik", pa=(d2.r - 14, d2.y), pb=(p3.x + 10, p3.b), at=0.5,
           ldx=-6, anchor="end")
    _flow2(c, p5, d2, "ETKILESIM", pa=(p5.r, p5.y + 8), pb=(d2.x + 40, d2.b), at=0.5, ldx=6, anchor="start")
    _flow2(c, p3, p6, "kabul (olay)", pa=(p3.cx, p3.y), pb=(p3.cx, p6.b), ldx=6, anchor="start")
    _flow2(c, p6, d5, "", both=True, pa=(p6.cx, p6.y), pb=(p6.cx, d5.b))
    _flow2(c, p6, ku, "dilekçe", pa=(p6.r, ku.cy), pb=(ku.x, ku.cy), ldy=-6)
    _flow2(c, p6, ta, ".ics", pa=(p6.r, p6.b - 12), pb=(ta.x, ta.cy), ldy=-6)
    _flow2(c, yr, p6, "kurum yanıtı /\nön sayfa, bildirim", both=True, pa=(yr.x + 10, yr.y),
           pb=(p6.r, p6.b - 2), at=0.3, ldx=6, anchor="start")
    _flow2(c, yr, p3, "oy / mühür", both=True, pa=(yr.x, yr.cy), pb=(p3.r, p3.b - 10), at=0.5, ldy=12)
    _flow2(c, p3, d6, "kayıtlar", pa=(p3.cx, p3.b), pb=(p3.cx, d6.y), ldx=6, anchor="start")
    _flow2(c, d6, p7, "bekleyen", pa=(p7.cx, d6.b), pb=(p7.cx, p7.y), ldx=6, anchor="start")
    _flow2(c, p7, d7, "", pa=(p7.cx, p7.b), pb=(p7.cx, d7.y))
    _flow2(c, zi, p7, "doğrula /\nrapor", both=True, pa=(zi.x, p7.cy), pb=(p7.r, p7.cy), ldy=-14)
    note(c, 0, 470, ["Her süreç kendi kayıtlarını D6'ya aynı işlemde yazar (yalnızca 3.0 çizildi).",
                     "5.0 ifşada 2.0'a KONU taslağı verir; 1.0 üyelikleri D2'ye de yazar;",
                     "Ziyaretçi de 6.0'ın ön sayfasını okur."])
    return c.done("Veri akış diyagramı: düzey 1")


# =====================================================================================================
# GANTT (git geçmişinden)
# =====================================================================================================

_GANTT = [
    ("Tasarım ve iskelet", "c214035 04ee82f 52eb1d2 c37ce05 8f830ef"),
    ("Çekirdek: kimlik, ontoloji, öneri,\nhavale, Karar Saati, Mahzen", "2241440 39478e8 421492c 16c5056 11b9b18 690db29"),
    ("Arayüz (Meydan, Mahzen, Android)",
     "4696525 b727665 91e6eb2 63f75d0 a97d787 14f6c99 3926224 118e1e1 9208bae 4d1b59d 10bccb4"),
    ("Kural ve yönetmelik genişletmeleri",
     "7df9c52 b241812 92ee471 041e31d 750c23d 8f9239d ad319da 0f8fb06 1bfd485 75bd9b7 cb91d45"),
    ("Havale süresi, kabulü; zamanlayıcı", "4abbe00 0c9c7d7 cfaf577 4da4c15"),
    ("Elle denetim ve Docker doğrulaması", "18ff27d d82a342"),
    ("Sınıf gösterimi ve sunum", "f85662d c987a03 d8b12b7 8c9a1be"),
    ("Kararların sonuçları: görsel, dilekçe,\ntakvim, gazete; desenler",
     "b938fa3 3f11538 db36421 d7ce844 3045399 7a3f14e"),
    ("Analiz: CRISP-DM, değerlendirme", "defcd45 d6de9b3"),
    ("Tohum içeriği", "1cd2e44 ca373c2 0793f0e"),
    ("Belgeler ve rapor", "5a4aca8 9cfc694 3211203 7b5cb13 707f57c ba38840 22eb85b 8ce1dfa 047b2ae eaec08c "
                          "880d43f 0fe8121 cd5b0f1"),
]
_MILESTONES = [("5a4aca8", "ilk tam sürüm"), ("f85662d", "sınıf gösterimi"), ("22eb85b", "rapor"),
               ("0fe8121", "A5 baskı")]


def _commits() -> list[tuple[str, datetime, str]]:
    from datetime import datetime as dt
    out = subprocess.run(["git", "log", "--reverse", "--format=%h|%aI|%s"], cwd=_REPO, check=True,
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        h, t, subj = line.split("|", 2)
        rows.append((h[:7], dt.fromisoformat(t), subj))
    return rows


def gantt() -> uml.Diagram:
    from datetime import datetime as dt
    commits = _commits()
    phase_of = {h: i for i, (_, hs) in enumerate(_GANTT) for h in hs.split()}
    doc = len(_GANTT) - 1
    rows: dict[int, list] = {i: [] for i in range(len(_GANTT))}
    for h, t, subj in commits:
        i = phase_of.get(h)
        if i is None:
            if subj.startswith(("Rapor", "Belge")):
                i = doc
            elif subj.startswith("Tohum"):
                i = _GANTT.index(next(g for g in _GANTT if g[0] == "Tohum içeriği"))
            else:
                raise ValueError(f"Gantt: aşaması belirsiz commit {h} {subj}")
        rows[i].append(t)
    d0 = min(t for _, t, _ in commits).date()
    d1 = max(t for _, t, _ in commits).date() + timedelta(days=1)
    days = (d1 - d0).days
    c = Canvas()
    X0, X1 = 230, 728
    dw = (X1 - X0) / days

    def tx(t) -> float:
        if isinstance(t, date) and not isinstance(t, dt):
            return X0 + (t - d0).days * dw
        return X0 + ((t.date() - d0).days + (t.hour + t.minute / 60) / 24) * dw

    top = 30
    rh = 26
    n = len(_GANTT)
    for k in range(days):
        d = d0 + timedelta(days=k)
        if d.weekday() >= 5:
            c.rect(tx(d), top, dw, n * rh + rh, fill=WASH, stroke=WASH, sw=0)
        if k % 2 == 0:
            c.text(tx(d) + dw / 2, top - 8, f"{d.day}.{d.month:02d}", 8.6, "mono", anchor="middle", fill=SOFT)
        c.line([(tx(d), top - 4), (tx(d), top + n * rh + rh)], stroke=GREY, sw=0.6)
    for i, (name, _) in enumerate(_GANTT):
        y = top + i * rh
        lines = name.split("\n")
        for k, t in enumerate(lines):
            c.text(X0 - 8, y + rh / 2 + 3 - (len(lines) - 1) * 5 + k * 10.5, t, 9.2, anchor="end")
        ts = rows[i]
        if not ts:
            continue
        a, b = min(ts).date(), max(ts).date() + timedelta(days=1)
        c.rect(tx(a), y + 7, tx(b) - tx(a), rh - 14, fill=GREY, stroke=INK, sw=0.8)
        for t in ts:
            x = tx(t)
            c.line([(x, y + 5), (x, y + rh - 5)], sw=1.2)
        c.text(tx(b) + 4, y + rh / 2 + 3, str(len(ts)), 8.6, "mono", fill=SOFT)
        c.line([(0, y + rh), (X1, y + rh)], stroke=GREY, sw=0.6)
    y = top + n * rh
    c.text(X0 - 8, y + rh / 2 + 3, "Kilometre taşları", 9.2, "serifb", anchor="end")
    when = {h: t for h, t, _ in commits}
    for k, (h, label) in enumerate(_MILESTONES):
        x = tx(when[h])
        c.path(f"M{x} {y + 6} L{x + 6} {y + 13} L{x} {y + 20} L{x - 6} {y + 13} Z", (x - 6, y + 6, x + 6, y + 20),
               fill=INK)
        _lab(c, x, y + rh + 12 + (k % 2) * 11, label, "middle", size=8.6)
    c.rect(0, top - 4, X1, (n + 1) * rh + 4, fill="none")
    note(c, 0, y + rh + 34, [f"Çubuk: aşamanın ilk ve son commit günü; dikey çizgi: commit (toplam {len(commits)}); "
                             "sağdaki sayı: commit sayısı.",
                             "Gri sütunlar hafta sonu. Kaynak: git log; aşamalar commit karmasıyla atanır."])
    return c.done("Gantt şeması: geliştirme takvimi (git geçmişinden)")


# =====================================================================================================
# BİLEŞİK YAPI, ETKİLEŞİME GENEL BAKIŞ, PROFİL
# =====================================================================================================


def cs_api() -> uml.Diagram:
    """Bileşik yapı: API sürecinin parçaları. Kaynak: main.create_app, default_graph, default_ledger,
    lifespan (scheduler.start_background); routers/deps.get_ctx; services/scheduler.background_tick."""
    c = Canvas()
    W, H = 590, 320
    c.rect(0, 0, W, H)
    c.text(12, 16, "«component»", 8.6, "serifi", fill=SOFT)
    c.text(12, 30, "API süreci  (mesveret.main:create_app)", 11, "serifb")
    routers = [q for q in (_REPO / "api/src/mesveret/routers").glob("*.py") if q.stem not in ("__init__", "deps")]

    def part(x, y, name, sub, w=170):
        b = box(c, x, y, [name, sub], size=10.5, kinds=["serifb", "serifi"], rx=0, w=w, h=40)
        return b

    ro = part(26, 70, f"routers [{len(routers)}]", "APIRouter, Depends(get_ctx)", w=160)
    cx = part(214, 140, "ctx : Ctx [0..*]", "istek ya da iş başına", w=160)
    zm = part(214, 250, "zamanlayıcı : Thread [0..1]", "SCHEDULER_ENABLED ise", w=160)
    st = part(404, 50, "settings : Settings [1]", "ortam değişkenleri", w=166)
    sm = part(404, 120, "sessionmaker [1]", "PostgreSQL oturumu", w=166)
    gr = part(404, 190, "graph : GraphStore [1]", "Neo4jGraph | InMemoryGraph", w=166)
    lg = part(404, 260, "ledger : LedgerClient [1]", "HttpLedgerClient | Fake…", w=166)
    c.line([ro.p("r"), (198, ro.cy), (198, cx.cy), cx.p("l")])
    c.text(202, 120, "her istekte kurulur", 8.6, "serifi", fill=SOFT)
    c.line([zm.p("t"), cx.p("b")])
    c.text(zm.cx + 6, (cx.b + zm.y) / 2 + 3, "kendi Ctx'ini kurar", 8.6, "serifi", fill=SOFT)
    bx = 390
    c.line([cx.p("r"), (bx, cx.cy)])
    c.line([(bx, st.cy), (bx, lg.cy)])
    for b in (st, sm, gr, lg):
        c.line([(bx, b.cy), (b.x, b.cy)])
    # kapılar
    def port(x, y):
        c.rect(x - 5, y - 5, 10, 10, fill=WHITE)
        return (x, y)

    pl = port(0, ro.cy)
    c.line([(5, ro.cy), (ro.x, ro.cy)])
    c.line([(-5, ro.cy), (-30, ro.cy)])
    c.circle(-36, ro.cy, 6)
    c.text(-36, ro.cy - 12, "REST :8000", 8.6, "serifi", anchor="middle", fill=SOFT)
    for b, name in ((sm, "SQL"), (gr, "Bolt"), (lg, "Defter HTTP")):
        port(W, b.cy)
        c.line([(b.r, b.cy), (W - 5, b.cy)])
        c.line([(W + 5, b.cy), (W + 24, b.cy)])
        c.path(f"M{W + 33} {b.cy - 9} A9 9 0 0 0 {W + 33} {b.cy + 9}", (W + 24, b.cy - 9, W + 33, b.cy + 9))
        c.text(W + 38, b.cy + 3, name, 8.6, "serifi", fill=SOFT)
    note(c, 30, 150, ["Parçalar app.state'te bir kez", "kurulur; Ctx her istekte", "ve her işte yeniden."])
    return c.done("Bileşik yapı diyagramı: API süreci")


def io_hafta() -> uml.Diagram:
    """Etkileşime genel bakış: bir önerinin yolundaki etkileşimler (öteki diyagramlara başvurur)."""
    c = Canvas()

    def ref(cx_, y, name, sub):
        w = max(tw(name, 10.5, "serifb"), tw(sub, 9, "serifi")) + 60
        x = cx_ - w / 2
        c.rect(x, y, w, 44)
        tag = tw("ref", 9, "monob") + 10
        c.path(f"M{x} {y} H{x + tag} V{y + 9} L{x + tag - 5} {y + 14} H{x} Z", (x, y, x + tag, y + 14), fill=WASH)
        c.text(x + 4, y + 10.5, "ref", 9, "monob")
        c.text(cx_, y + 22, name, 10.5, "serifb", anchor="middle")
        c.text(cx_, y + 35, sub, 9, "serifi", anchor="middle", fill=SOFT)
        return Box(x, y, w, 44)

    X = 330
    s0 = start_node(c, X, 0)
    d1 = decision(c, X, 40)
    edge(c, [s0.p("b"), d1.p("t")], head="open")
    rm = ref(120, 70, "Mahzen başlığının ifşası", "sıralama diyagramı")
    edge(c, [d1.p("l"), (rm.cx, 40), rm.p("t")], head="open")
    _lab(c, (rm.cx + d1.x) / 2, 34, "[Mahzen'den]", "middle")
    m1 = decision(c, X, 150)
    edge(c, [rm.p("b"), (rm.cx, 150), m1.p("l")], head="open")
    _lab(c, rm.cx + 8, rm.b + 16, "taslak gönderilir")
    edge(c, [d1.p("b"), m1.p("t")], head="open")
    _lab(c, X + 8, 98, "[doğrudan]")
    ro = ref(X, 180, "Öneri açma", "sıralama diyagramı")
    edge(c, [m1.p("b"), ro.p("t")], head="open")
    d2 = decision(c, X, 260)
    edge(c, [ro.p("b"), d2.p("t")], head="open")
    rs = ref(580, 280, "Sessiz onayla kabul", "iletişim diyagramı")
    edge(c, [d2.p("r"), (rs.cx, 260), rs.p("t")], head="open")
    _lab(c, (d2.r + rs.cx) / 2, 254, "[hızlı şerit, itiraz < eşik]", "middle")
    rv = ref(X, 300, "Karar Saati'nde oy verme", "sıralama diyagramı")
    edge(c, [d2.p("b"), rv.p("t")], head="open")
    _lab(c, X + 8, 284, "[yavaş şerit]")
    _lab(c, rv.x - 8, rv.cy + 3, "{Pazar 20:00–21:00}", "end")
    rk = ref(X, 380, "Karar Saati'nin kapanışı", "sıralama diyagramı")
    edge(c, [rv.p("b"), rk.p("t")], head="open")
    m2 = decision(c, X, 460)
    edge(c, [rk.p("b"), m2.p("t")], head="open")
    edge(c, [rs.p("b"), (rs.cx, 460), m2.p("r")], head="open")
    rd = ref(X, 490, "Defter yazımı ve çoğaltma", "sıralama diyagramı")
    edge(c, [m2.p("b"), rd.p("t")], head="open")
    f = final_node(c, X, 570)
    edge(c, [rd.p("b"), f.p("t")], head="open")
    note(c, 0, 400, ["Her kutu ayrı bir diyagrama", "başvurur (ref); aradaki akış", "etkinlik gösterimiyle çizilir."])
    return c.done("Etkileşime genel bakış diyagramı: bir önerinin yolu")


def pf_desen() -> uml.Diagram:
    """Profil diyagramı: diyagramlarda kullanılan desen klişeleri (stereotype) ve koddaki örnekleri.
    Örnek sınıflar sema.json'da denetlenir."""
    c = Canvas()
    rows = [
        [("Facade", ["proposals (modül)"]), ("Strategy", ["ProposalKind,", "BallotMethod, Detector"]),
         ("State", ["ProposalState"]), ("Command", ["Job"])],
        [("Chain of Responsibility", ["Rule (R1–R9)"]), ("Observer", ["EventBus,", "EvaluationObserver"]),
         ("Repository", ["OntologyView,", "LedgerClient,", "ScenarioRepository"]),
         ("Adapter", ["Neo4jGraph,", "HttpLedgerClient"])],
    ]
    for n in ("ProposalKind", "BallotMethod", "Detector", "ProposalState", "Job", "Rule", "EventBus",
              "EvaluationObserver", "OntologyView", "LedgerClient", "ScenarioRepository", "Neo4jGraph",
              "HttpLedgerClient"):
        _k(n)
    W_, gap = 172, 10
    tops, boxes = [0, 210], []
    for y, row in zip(tops, rows, strict=True):
        line = []
        for i, (name, ex) in enumerate(row):
            b = cls(c, i * (W_ + gap), y, name, ["örnek: " + ex[0], *["  " + e for e in ex[1:]]], [],
                    stereo="stereotype", w=W_, mkind="serif", size=10.5)
            line.append(b)
        boxes.append(line)
    mc = cls(c, 0, 0, "Class", [], [], stereo="metaclass", center_x=True)
    total = 4 * W_ + 3 * gap
    mx = total / 2
    mc_w = mc.w
    # metaclass ortada: yeniden çiz
    c2 = Canvas()
    c = c2
    boxes = []
    for y, row in zip(tops, rows, strict=True):
        line = []
        for i, (name, ex) in enumerate(row):
            b = cls(c, i * (W_ + gap), y, name, ["örnek: " + ex[0], *["  " + e for e in ex[1:]]], [],
                    stereo="stereotype", w=W_, mkind="serif", size=10.5)
            line.append(b)
        boxes.append(line)
    up_b = max(b.b for b in boxes[0])
    mc = cls(c, mx - mc_w / 2, up_b + 40, "Class", [], [], stereo="metaclass")
    bus1 = up_b + 18
    c.line([(boxes[0][0].cx, bus1), (boxes[0][-1].cx, bus1)])
    for b in boxes[0]:
        c.line([(b.cx, b.b), (b.cx, bus1)])
    edge(c, [(mx, bus1), (mx, mc.y)], head="ftri")
    bus2 = boxes[1][0].y - 18
    c.line([(boxes[1][0].cx, bus2), (boxes[1][-1].cx, bus2)])
    for b in boxes[1]:
        c.line([(b.cx, b.y), (b.cx, bus2)])
    edge(c, [(mx, bus2), (mx, mc.b)], head="ftri")
    package(c, -12, -12, total + 24, max(b.b for b in boxes[1]) + 24, "«profile» Meşveret desenleri",
            fill="none")
    return c.done("Profil diyagramı: desen klişeleri")
