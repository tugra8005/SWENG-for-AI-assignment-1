"""Öneri türleri (Strategy + Registry + Factory Method).

Her öneri türünün türe özgü davranışı bir sınıftadır: girdiyi hazırlama, kabulde uygulama,
oylama eşiği, kurallara giden ek alanlar, görünüme eklenenler ve oylama biçimi. Öneri motoru
(``services.proposals``) türü sormaz; ``kind_for(p)`` ile türün nesnesini alıp ona sorar. Yeni bir
tür, yeni bir sınıfın ``@KINDS.register`` ile kaydedilmesidir; motor ve diğer türler değişmez.

Konu kabulünün dünyadaki sonuçları (dilekçe, takvim) burada değil, ``events`` abonelerindedir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import ClosureText, Decision, Message, Proposal, Topic, User
from mesveret.domain.diff import word_diff
from mesveret.domain.lifecycle import PENDING_STATUSES
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.oracle import ContentCheck, content_check
from mesveret.domain.registry import Registry
from mesveret.domain.regulation import (
    CONTENT_RULE_KIND,
    RegulationError,
    article_kind,
    article_title,
    validate_value,
)
from mesveret.domain.rules import format_date
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.domain.text import normalize
from mesveret.domain.types import ProposalType
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import events, ledger, media, regulation, topics
from mesveret.services.profile import nickname_map

MAX_TITLE = 200
MAX_BODY = 20_000
INTERNAL = "mesveret"  # yönetmelik, silme, düzenleme: Meşveret'in iç düzeni


@dataclass
class ProposalInput:
    type: str
    title: str = ""
    body: str = ""
    area_id: str | None = None
    scope_id: str | None = None
    resource_ids: list[str] = field(default_factory=list)
    parent_topic_id: int | None = None
    target_message_id: int | None = None
    target_topic_id: int | None = None
    new_text: str | None = None
    article_key: str | None = None
    new_value: dict[str, Any] | None = None
    reopens_topic_id: int | None = None
    # SILME: dayanılan içerik kuralları (IK-1…) ve kuralı ihlal eden kısım (metinden alıntı).
    content_rules: list[str] = field(default_factory=list)
    excerpt: str = ""
    # YONETMELIK: "degistir" (değer), "ekle" (yeni içerik kuralı), "kaldir" (içerik kuralı)
    article_action: str = "degistir"
    # Bölünebilir kaynak: {kaynak: {kapsam: yeni_pay}} (R2'nin ters yönü)
    share_effect: dict[str, dict[str, Any]] | None = None
    # KONU/ALT_KONU: önceden yüklenmiş kapak görseli (kabul edilince konunun kapağı olur)
    cover_media_id: str | None = None
    # KONU/ALT_KONU: önerinin iletileceği yer (R9); ALT_KONU verilmezse üst konununkini alır.
    addressee: str | None = None
    # KONU/ALT_KONU, muhatap takvim: etkinlik bilgisi (başlangıç, süre, yer; bkz. calendar)
    event: dict[str, Any] | None = None


@dataclass
class Prepared:
    """Türe özgü hazırlığın sonucu: Proposal alanları."""

    type: ProposalType
    title: str
    body: str
    area_id: str | None
    scope_id: str
    resource_ids: list[str]
    target_key: str
    payload: dict[str, Any]
    parent_resource_id: str | None = None


# --- ortak yardımcılar ------------------------------------------------------------------------------


def clean_title(text: str, *, required: bool = True) -> str:
    text = text.strip()
    if required and len(text) < 3:
        raise DomainError("Başlık en az 3 karakter olmalı.")
    if len(text) > MAX_TITLE:
        raise DomainError(f"Başlık en fazla {MAX_TITLE} karakter olabilir.")
    return text


def clean_body(text: str, *, required: bool = True, label: str = "Metin") -> str:
    text = text.strip()
    if required and not text:
        raise DomainError(f"{label} boş olamaz.")
    if len(text) > MAX_BODY:
        raise DomainError(f"{label} en fazla {MAX_BODY} karakter olabilir.")
    return topics.check_square_text(text, max_len=MAX_BODY) if text else text


def live_topic(ctx: Ctx, topic_id: int | None, *, must_be_open: bool = True) -> Topic:
    if topic_id is None:
        raise DomainError("Hedef konu belirtilmeli.")
    topic = topics.get_topic(ctx, topic_id)
    if topic.deleted_by_proposal_id is not None:
        raise Conflict(f"Bu konu #{topic.deleted_by_proposal_id} numaralı oylamayla silindi.")
    if must_be_open and topic.status != "OPEN":
        raise Conflict("Konu karara bağlandı; önce yeniden açılması gerekir.")
    return topic


def closure_texts(ctx: Ctx, p: Proposal) -> list[ClosureText]:
    return list(ctx.db.execute(
        select(ClosureText).where(ClosureText.proposal_id == p.id).order_by(ClosureText.id)
    ).scalars())


def deletion_target_text(ctx: Ctx, payload: dict) -> str:
    """Silinmesi önerilen içeriğin güncel metni (mesaj ya da konu başlığı + açılış metni)."""
    if payload.get("message_id") is not None:
        msg = ctx.db.get(Message, payload["message_id"])
        return topics.current_version(ctx, msg).text if msg else ""
    topic = ctx.db.get(Topic, payload.get("topic_id"))
    if topic is None:
        return ""
    opening = ctx.db.execute(select(Message).where(
        Message.topic_id == topic.id, Message.is_opening.is_(True)
    )).scalar_one_or_none()
    return f"{topic.title}\n{topics.current_version(ctx, opening).text if opening else ''}"


# --- tür arayüzü ------------------------------------------------------------------------------------


class ProposalKind(ABC):
    """Bir öneri türünün davranışı. Varsayılanlar çoğu tür için geçerlidir; tür yalnızca
    farklı olanı ezer (``threshold_key``, ``view``…)."""

    type: ClassVar[ProposalType]
    # Karar Saati'nde oylama biçimi: "binary" (EVET/HAYIR) ya da "approval" (metin onayı)
    ballot: ClassVar[str] = "binary"
    takes_cover: ClassVar[bool] = False

    @abstractmethod
    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        """Girdiyi doğrular ve önerinin alanlarını hazırlar (kurallar bundan sonra çalışır)."""

    @abstractmethod
    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        """Kabul edilen önerinin etkisi."""

    def threshold_key(self, p: Proposal) -> str | None:
        """Karar Saati'nde uygulanacak eşik maddesi (onay oylamasında yok)."""
        return "basit_cogunluk"

    def draft_fields(self, ctx: Ctx, p: Proposal | Prepared) -> dict[str, Any]:
        """Kural denetimine (``ProposalDraft``) türe özgü alanlar."""
        return {}

    def content_check(self, ctx: Ctx, p: Proposal) -> ContentCheck | None:
        """Hâtif'in H4 denetimi (yalnızca silme)."""
        return None

    def after_open(self, ctx: Ctx, p: Proposal, proposer: str) -> None:
        """Açılış kaydından sonra çalışan kanca."""

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        """Öneri sayfasının türe özgü alanları."""


KINDS = Registry[ProposalKind]("öneri türü")
REOPEN_KEY = "KONU/yeniden-acma"


def kind_of(type_: str, *, reopen: bool = False) -> ProposalKind:
    """Fabrika: hangi sınıfın örnekleneceğine tür (ve yeniden açma işareti) karar verir."""
    try:
        t = ProposalType(type_)
    except ValueError as exc:
        raise DomainError("Bilinmeyen öneri türü.") from exc
    return KINDS.create(REOPEN_KEY if reopen and t is ProposalType.KONU else str(t))


def kind_for(p: Proposal | Prepared) -> ProposalKind:
    return kind_of(str(p.type), reopen=bool(p.payload.get("reopen")))


def kind_for_input(inp: ProposalInput) -> ProposalKind:
    return kind_of(inp.type, reopen=inp.reopens_topic_id is not None)


# --- konu ve alt konu -------------------------------------------------------------------------------


class _NewTopic(ProposalKind):
    """KONU ve ALT_KONU: kabul edilince yeni bir konu açılır."""

    takes_cover = True

    def _parent(self, ctx: Ctx, inp: ProposalInput, payload: dict) -> tuple[str | None, str | None]:
        """Üst konu kancası: (üst kaynak kimliği, devralınan muhatap)."""
        return None, None

    def _target_key(self, inp: ProposalInput, payload: dict, title: str) -> str:
        return f"KONU:{inp.area_id}:{normalize(title)}"

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        title = clean_title(inp.title)
        if not inp.scope_id:
            raise DomainError("Seçmen kapsamı seçilmeli.")
        payload: dict[str, Any] = {}
        if inp.share_effect is not None:
            if not isinstance(inp.share_effect, dict) or not all(
                isinstance(v, dict) for v in inp.share_effect.values()
            ):
                raise DomainError("Pay etkisi {kaynak: {kapsam: yeni_pay}} biçiminde olmalı.")
            payload["share_effect"] = {rid: dict(eff) for rid, eff in inp.share_effect.items()}
            # Hedefler bu paylara göre bildirildi; kapanışta paylar değişmişse öneri uygulanamaz.
            payload["share_base"] = {
                rid: dict(r.shares) for rid in payload["share_effect"]
                if (r := ctx.graph.resource(rid)) is not None and r.divisible
            }
        parent_rid, inherited = self._parent(ctx, inp, payload)
        payload["addressee"] = inp.addressee or inherited
        from mesveret.services import calendar  # calendar events'e abone, events bu modülü değil

        event = calendar.prepare_event(ctx, payload["addressee"], inp.event)
        if event is not None:
            payload["event"] = event
        resource_ids = list(dict.fromkeys(inp.resource_ids))
        if event is not None and event.get("venue_resource_id"):
            # Ortak salon bir kaynaktır: etiketlenince R2 sahiplik denetimi kendiliğinden işler.
            resource_ids = list(dict.fromkeys([*resource_ids, event["venue_resource_id"]]))
        return Prepared(
            self.type, title, clean_body(inp.body, label="Açılış metni"), inp.area_id,
            inp.scope_id, resource_ids, self._target_key(inp, payload, title), payload,
            parent_rid,
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        parent_id = p.payload.get("parent_topic_id")
        topic = Topic(
            title=p.title, area_id=p.area_id, parent_id=parent_id, owner_scope_id=p.scope_id,
            author_id=p.proposer_id, status="OPEN", created_at=ctx.now, accepted_proposal_id=p.id,
            addressee=p.payload.get("addressee"),
        )
        ctx.db.add(topic)
        ctx.db.flush()
        ctx.graph.upsert_resource(
            ResourceInfo(topic.resource_id, ResourceKind.KONU, topic.title, topic.owner_scope_id),
            topic_area_id=topic.area_id,
            parent_topic_id=f"konu:{parent_id}" if parent_id else None,
        )
        topics.create_message(
            ctx, topic, p.proposer_id, p.body, is_opening=True, ledger_type="KONU_KABUL",
            extra={"oneri": p.id, "baslik": topic.title, "alan": topic.area_id,
                   "sahip_kapsam": topic.owner_scope_id,
                   "daraltma": [n["message"] for n in p.narrowings]},
        )
        _apply_share_effect(ctx, p)
        events.publish(ctx, events.TopicAccepted(topic, p))

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        body["cover"] = media.cover(ctx, p.id)
        body["event"] = p.payload.get("event")
        if p.status == "ACCEPTED":
            body["topic_id"] = ctx.db.execute(
                select(Topic.id).where(Topic.accepted_proposal_id == p.id)
            ).scalar_one_or_none()


@KINDS.register(ProposalType.KONU)
class TopicKind(_NewTopic):
    type = ProposalType.KONU


@KINDS.register(ProposalType.ALT_KONU)
class SubtopicKind(_NewTopic):
    type = ProposalType.ALT_KONU

    def _parent(self, ctx: Ctx, inp: ProposalInput, payload: dict) -> tuple[str | None, str | None]:
        parent = live_topic(ctx, inp.parent_topic_id)
        payload["parent_topic_id"] = parent.id
        return parent.resource_id, parent.addressee

    def _target_key(self, inp: ProposalInput, payload: dict, title: str) -> str:
        return f"ALT_KONU:{payload['parent_topic_id']}:{normalize(title)}"


@KINDS.register(REOPEN_KEY)
class ReopenKind(ProposalKind):
    """Karara bağlanmış konuyu yeniden açan KONU önerisi (``yeniden_acma`` süresinden sonra)."""

    type = ProposalType.KONU

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        topic = topics.get_topic(ctx, inp.reopens_topic_id)
        if topic.status != "CLOSED" or topic.closed_at is None:
            raise Conflict("Yalnızca karara bağlanmış bir konu yeniden açılabilir.")
        reopen_at = topic.closed_at + ctx.reg.duration("yeniden_acma")
        if ctx.now < reopen_at:
            raise DomainError(
                f"Bu konu {format_date(reopen_at)} tarihinden önce yeniden açılamaz "
                "(yeniden_acma süresi)."
            )
        return Prepared(
            self.type, clean_title(inp.title or f"Yeniden açma: {topic.title}"),
            clean_body(inp.body, label="Gerekçe"), topic.area_id,
            inp.scope_id or topic.owner_scope_id, [topic.resource_id],
            f"YENIDEN_ACMA:{topic.id}",
            {"topic_id": topic.id, "reopen": True, "addressee": topic.addressee},
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        topic = topics.get_topic(ctx, p.payload["topic_id"])
        topic.status, topic.reopened_at = "OPEN", ctx.now
        ledger.enqueue(ctx, "KONU_YENIDEN_ACILDI", {"konu": topic.id, "oneri": p.id})


def _apply_share_effect(ctx: Ctx, p: Proposal) -> None:
    """Kabul edilen önerinin bildirdiği yeni paylar kaynağa işlenir."""
    for rid, effect in (p.payload.get("share_effect") or {}).items():
        r = ctx.graph.resource(rid)
        if r is None or not effect:
            continue
        new = {sid: int(effect.get(sid, old)) for sid, old in r.shares.items()}
        if new == dict(r.shares):
            continue
        ctx.graph.upsert_resource(replace(r, shares=new))
        ledger.enqueue(ctx, "PAY_DEGISTI", {
            "oneri": p.id, "kaynak": rid, "eski": dict(r.shares), "yeni": new,
        })


# --- düzenleme --------------------------------------------------------------------------------------


@KINDS.register(ProposalType.DUZENLEME)
class EditKind(ProposalKind):
    type = ProposalType.DUZENLEME

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        msg = topics.get_message(ctx, inp.target_message_id) if inp.target_message_id else None
        if msg is None:
            raise DomainError("Düzenlenecek mesaj belirtilmeli.")
        if msg.deleted_by_proposal_id is not None:
            raise Conflict(f"Bu mesaj #{msg.deleted_by_proposal_id} numaralı oylamayla silindi.")
        if msg.author_id == user.id and not msg.is_opening:
            raise DomainError("Kendi mesajınızı doğrudan düzenleyebilirsiniz; öneri gerekmez.")
        topic = live_topic(ctx, msg.topic_id)
        new_text = clean_body(inp.new_text or "", label="Yeni metin")
        current = topics.current_version(ctx, msg)
        if new_text == current.text:
            raise DomainError("Önerilen metin mevcut metinle aynı.")
        return Prepared(
            self.type, clean_title(inp.title or f"Düzenleme: {topic.title}"),
            clean_body(inp.body, required=False), topic.area_id,
            inp.scope_id or topic.owner_scope_id, [topic.resource_id], f"ICERIK:mesaj:{msg.id}",
            {"topic_id": topic.id, "message_id": msg.id, "base_version": current.version_no,
             "new_text": new_text, "opening": msg.is_opening, "addressee": INTERNAL},
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        msg = topics.get_message(ctx, p.payload["message_id"])
        topics.add_version(ctx, msg, p.payload["new_text"], p.proposer_id, via_proposal_id=p.id)

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        msg = ctx.db.get(Message, p.payload["message_id"])
        base = topics.current_version(ctx, msg).text if msg else ""
        body["current_text"] = base
        body["diff"] = [list(c) for c in word_diff(base, p.payload["new_text"])]


# --- silme ------------------------------------------------------------------------------------------


@KINDS.register(ProposalType.SILME)
class DeletionKind(ProposalKind):
    type = ProposalType.SILME

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        if (inp.target_message_id is None) == (inp.target_topic_id is None):
            raise DomainError("Silinecek mesajı ya da konuyu (yalnızca birini) belirtin.")
        own = False
        if inp.target_message_id is not None:
            msg = topics.get_message(ctx, inp.target_message_id)
            if msg.deleted_by_proposal_id is not None:
                raise Conflict("Bu mesaj zaten silindi.")
            topic = live_topic(ctx, msg.topic_id, must_be_open=False)
            target = {"message_id": msg.id}
            key = f"ICERIK:mesaj:{msg.id}"
            default_title = f"Silme: {topic.title} konusundaki #{msg.id} numaralı mesaj"
            # Yazarın rızası: kendi mesajı için gerekçe gerekmez, basit çoğunluk yeter. Konu
            # silme hiçbir zaman "kendi" sayılmaz; başkalarının mesajlarını da götürür.
            own = msg.author_id == user.id
        else:
            topic = live_topic(ctx, inp.target_topic_id, must_be_open=False)
            target = {}
            key = f"ICERIK:konu:{topic.id}"
            default_title = f"Silme: {topic.title}"
        rules = list(dict.fromkeys(code.strip() for code in inp.content_rules if code.strip()))
        return Prepared(
            self.type, clean_title(inp.title or default_title),
            clean_body(inp.body, required=False), topic.area_id,
            inp.scope_id or topic.owner_scope_id, [topic.resource_id], key,
            {"topic_id": topic.id, **target, "rules": rules, "excerpt": inp.excerpt.strip(),
             "own": own, "addressee": INTERNAL},
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        if "message_id" in p.payload:
            target = topics.get_message(ctx, p.payload["message_id"])
        else:
            target = topics.get_topic(ctx, p.payload["topic_id"])
        target.deleted_by_proposal_id = p.id
        ledger.enqueue(ctx, "ICERIK_SILINDI", {
            "oneri": p.id, "konu": p.payload["topic_id"], "mesaj": p.payload.get("message_id"),
            "kurallar": p.payload.get("rules", []), "kendi": bool(p.payload.get("own")),
            "not": "İçerik sitede gizlendi; defterdeki kayıtları silinmez.",
        })

    def threshold_key(self, p: Proposal) -> str | None:
        # Yazarın kendi mesajı basit çoğunlukla; başkasının içeriği nitelikli çoğunlukla silinir.
        return "basit_cogunluk" if p.payload.get("own") else "silme_esigi"

    def draft_fields(self, ctx: Ctx, p: Proposal | Prepared) -> dict[str, Any]:
        return {"content_rules": tuple(p.payload.get("rules", ())),
                "excerpt": p.payload.get("excerpt", ""),
                "target_text": deletion_target_text(ctx, p.payload),
                "own_content": bool(p.payload.get("own"))}

    def content_check(self, ctx: Ctx, p: Proposal) -> ContentCheck | None:
        return content_check(p.payload.get("rules", ()), p.payload.get("excerpt", ""),
                             ctx.reg.content_rules(), own=bool(p.payload.get("own")))

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        if p.status != "ACCEPTED":
            body["target_preview"] = _target_preview(ctx, p)
        rules = ctx.reg.content_rules()
        body["content_rules"] = [{"code": c, "title": rules[c].title if c in rules else c}
                                 for c in p.payload.get("rules", [])]
        body["excerpt"] = p.payload.get("excerpt", "")
        body["own"] = bool(p.payload.get("own"))


def _target_preview(ctx: Ctx, p: Proposal) -> dict | None:
    if "message_id" in p.payload:
        msg = ctx.db.get(Message, p.payload["message_id"])
        if msg is None or msg.deleted_by_proposal_id is not None:
            return None
        return {"kind": "mesaj", "id": msg.id, "text": topics.current_version(ctx, msg).text}
    topic = ctx.db.get(Topic, p.payload["topic_id"])
    if topic is None or topic.deleted_by_proposal_id is not None:
        return None
    return {"kind": "konu", "id": topic.id, "title": topic.title}


# --- yönetmelik -------------------------------------------------------------------------------------


@KINDS.register(ProposalType.YONETMELIK)
class RegulationKind(ProposalKind):
    type = ProposalType.YONETMELIK

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        prep = self._prepare(ctx, inp)
        prep.payload["addressee"] = INTERNAL
        return prep

    def _prepare(self, ctx: Ctx, inp: ProposalInput) -> Prepared:
        action = inp.article_action or "degistir"
        if action not in regulation.ACTIONS:
            raise DomainError("Yönetmelik işlemi 'degistir', 'ekle' ya da 'kaldir' olmalı.")
        body, scope = clean_body(inp.body, required=False), inp.scope_id or GENERAL_SCOPE_ID
        current = ctx.graph.articles()

        if action == "ekle":
            key = regulation.next_content_rule_code(ctx)
            try:
                new_value = validate_value(key, inp.new_value or {})
            except RegulationError as exc:
                raise DomainError(str(exc)) from exc
            title = f"Yönetmelik: {key} eklensin ({new_value['baslik']})"
            # Hedef anahtarı kuralın başlığı: reddedilen ekleme yeni kodla hemen geri gelemez (R6).
            return Prepared(
                self.type, clean_title(inp.title or title), body, None, scope,
                [regulation.CONTENT_RULES_RESOURCE_ID],
                f"MADDE:ekle:{normalize(new_value['baslik'])}",
                {"article_key": key, "action": "ekle", "old_value": None, "new_value": new_value},
            )

        key = inp.article_key or ""
        kind = article_kind(key)
        if kind is None or key not in current:
            raise DomainError("Böyle bir yönetmelik maddesi yok ya da yürürlükte değil.")
        old_value = current[key]
        default_title = f"Yönetmelik: {article_title(key, old_value)}"
        if ctx.reg.is_unchangeable(key):
            # Değer doğrulanmaz: öneri R8'de "Bu madde değiştirilemez" gerekçesiyle reddedilir.
            return Prepared(
                self.type, clean_title(inp.title or default_title), body, None, scope,
                [regulation.article_resource_id(key)], f"MADDE:{key}",
                {"article_key": key, "action": action, "old_value": old_value,
                 "new_value": inp.new_value},
            )
        if action == "kaldir":
            if kind != CONTENT_RULE_KIND:
                raise DomainError(
                    "Yalnızca içerik kuralları kaldırılabilir; parametrelerin değeri değişir.")
            title = f"Yönetmelik: {key} kaldırılsın ({old_value['baslik']})"
            return Prepared(
                self.type, clean_title(inp.title or title), body, None, scope,
                [regulation.article_resource_id(key)], f"MADDE:{key}",
                {"article_key": key, "action": "kaldir", "old_value": old_value,
                 "new_value": None},
            )
        try:
            new_value = validate_value(key, inp.new_value or {})
        except RegulationError as exc:
            raise DomainError(str(exc)) from exc
        if new_value == old_value:
            raise DomainError("Önerilen değer mevcut değerle aynı.")
        return Prepared(
            self.type, clean_title(inp.title or default_title), body, None, scope,
            [regulation.article_resource_id(key)], f"MADDE:{key}",
            {"article_key": key, "action": "degistir", "old_value": old_value,
             "new_value": new_value},
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        action = p.payload.get("action", "degistir")
        regulation.apply_change(ctx, p.payload["article_key"], p.payload["new_value"], p.id,
                                action=action)
        ledger.enqueue(ctx, "YONETMELIK_DEGISTI", {
            "oneri": p.id, "madde": p.payload["article_key"], "islem": action,
            "eski": p.payload["old_value"], "yeni": p.payload["new_value"],
        })

    def threshold_key(self, p: Proposal) -> str | None:
        return "yonetmelik_esigi"

    def draft_fields(self, ctx: Ctx, p: Proposal | Prepared) -> dict[str, Any]:
        return {"article_key": p.payload.get("article_key"),
                "article_action": p.payload.get("action"),
                "new_value": p.payload.get("new_value")}

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        key = p.payload["article_key"]
        body["article"] = {"key": key, "kind": article_kind(key),
                           "title": article_title(key, p.payload.get("new_value")
                                                  or p.payload.get("old_value"))}


# --- kapanış ----------------------------------------------------------------------------------------


@KINDS.register(ProposalType.KAPANIS)
class ClosureKind(ProposalKind):
    """Konuyu Karar'la kapatır. Rakip metinler onay oylamasıyla yarışır; en çok ağırlıklı onayı
    alan metin Karar olur."""

    type = ProposalType.KAPANIS
    ballot = "approval"

    def prepare(self, ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
        topic = live_topic(ctx, inp.target_topic_id)
        if not topics.is_participant(ctx, topic, user.id):
            raise Forbidden("Kapanış önerisini yalnızca konunun katılımcıları açabilir.")
        active = ctx.db.execute(
            select(Proposal.id).where(
                Proposal.type == "KAPANIS", Proposal.status.in_(PENDING_STATUSES),
                Proposal.target_key == f"KAPANIS:{topic.id}",
            )
        ).first()
        if active:
            raise Conflict(
                f"Bu konuda açık bir kapanış önerisi var (#{active[0]}); rakip metin olarak "
                "ekleyin."
            )
        return Prepared(
            self.type, clean_title(inp.title or f"Kapanış: {topic.title}"),
            clean_body(inp.body, label="Karar metni"), topic.area_id,
            inp.scope_id or topic.owner_scope_id, [topic.resource_id],
            f"KAPANIS:{topic.id}", {"topic_id": topic.id, "addressee": topic.addressee},
        )

    def apply(self, ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
        texts = {ct.id: ct for ct in closure_texts(ctx, p)}
        if winner_text_id not in texts:
            raise DomainError("Kazanan karar metni bulunamadı.")
        topic = topics.get_topic(ctx, p.payload["topic_id"])
        d = Decision(topic_id=topic.id, proposal_id=p.id, closure_text_id=winner_text_id,
                     text=texts[winner_text_id].text, created_at=ctx.now)
        ctx.db.add(d)
        ctx.db.flush()
        topic.status, topic.closed_at = "CLOSED", ctx.now
        ctx.graph.record_decision(d.id, topic.resource_id)
        ledger.enqueue(ctx, "KARAR", {
            "karar": d.id, "konu": topic.id, "oneri": p.id, "metin": d.text,
        }, ref=d)
        events.publish(ctx, events.DecisionMade(topic, p, d))

    def threshold_key(self, p: Proposal) -> str | None:
        return None

    def after_open(self, ctx: Ctx, p: Proposal, proposer: str) -> None:
        # Açılış metni de rakip metinler gibi kendi kaydıyla mühürlenir (metin_no oylamada anılır).
        ct = ClosureText(proposal_id=p.id, author_id=p.proposer_id, text=p.body,
                         created_at=ctx.now)
        ctx.db.add(ct)
        ctx.db.flush()
        ledger.enqueue(ctx, "KAPANIS_METNI", {
            "oneri": p.id, "metin_no": ct.id, "yazar": proposer, "metin": ct.text,
        }, ref=ct)

    def view(self, ctx: Ctx, p: Proposal, body: dict[str, Any]) -> None:
        texts = closure_texts(ctx, p)
        tn = nickname_map(ctx, [ct.author_id for ct in texts])
        body["texts"] = [{"id": ct.id, "author": tn.get(ct.author_id), "text": ct.text,
                          "created_at": ct.created_at, "ledger_hash": ct.ledger_hash}
                         for ct in texts]
        d = ctx.db.execute(select(Decision).where(Decision.proposal_id == p.id)).scalar_one_or_none()
        body["decision_id"] = d.id if d else None
