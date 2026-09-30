"""PostgreSQL şeması: kimlik, içerik, sürümler, öneriler, oylar, Mahzen, defter outbox'ı.

Graf verisi (ontoloji, üyelik, havale, etkileşim, yönetmelik değerleri) Neo4j'dedir.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mesveret.db.base import Base

TS = DateTime(timezone=True)


class SimClockRow(Base):
    """Sahte saat: tek satır, gerçek saate eklenen ofset (mikrosaniye)."""

    __tablename__ = "sim_clock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    offset_us: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Demo modu: doluysa saat bu anda durur (geri sayımlar, zaman damgaları iki çalıştırmada aynı).
    frozen_at: Mapped[datetime | None] = mapped_column(TS)


class DemoState(Base):
    """Sınıf gösterimi modu: yığının hangi demo adımında olduğu (yalnızca geliştirme)."""

    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    step: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(TS)


class SchedulerState(Base):
    """Zamanlayıcının en son işlediği an (haftalık Karar Saati'ni kaçırmamak için)."""

    __tablename__ = "scheduler_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_tick_at: Mapped[datetime | None] = mapped_column(TS)


# --- kimlik ------------------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32), unique=True)
    nickname_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    birth_date: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None] = mapped_column(String(40))
    city_scope_id: Mapped[str | None] = mapped_column(String(64))
    district: Mapped[str | None] = mapped_column(String(60))
    address_line: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default="CITIZEN")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS)
    last_login_at: Mapped[datetime | None] = mapped_column(TS)
    address_changed_at: Mapped[datetime | None] = mapped_column(TS)
    cellar_warned_at: Mapped[datetime | None] = mapped_column(TS)
    # "Havale kabul etmiyorum": açıksa bu kişiye yeni havale verilemez.
    refuses_delegations: Mapped[bool] = mapped_column(Boolean, default=False)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(TS)
    used_at: Mapped[datetime | None] = mapped_column(TS)


# --- içerik -------------------------------------------------------------------------------------


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    area_id: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"))
    owner_scope_id: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")  # OPEN | CLOSED
    created_at: Mapped[datetime] = mapped_column(TS)
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    reopened_at: Mapped[datetime | None] = mapped_column(TS)
    accepted_proposal_id: Mapped[int | None] = mapped_column(Integer)
    deleted_by_proposal_id: Mapped[int | None] = mapped_column(Integer)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))

    @property
    def resource_id(self) -> str:
        return f"konu:{self.id}"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reply_to_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    is_opening: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    deleted_by_proposal_id: Mapped[int | None] = mapped_column(Integer)


class MessageVersion(Base):
    __tablename__ = "message_versions"
    __table_args__ = (UniqueConstraint("message_id", "version_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    editor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    via_proposal_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TS)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


# --- öneriler ------------------------------------------------------------------------------------


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    lane: Mapped[str] = mapped_column(String(8))
    proposer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    scope_id: Mapped[str] = mapped_column(String(64))
    area_id: Mapped[str | None] = mapped_column(String(64))
    resource_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    narrowings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    target_key: Mapped[str] = mapped_column(String(300), index=True)
    oracle_comment: Mapped[str | None] = mapped_column(Text)
    oracle_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(TS)
    deadline_at: Mapped[datetime | None] = mapped_column(TS)
    queued_at: Mapped[datetime | None] = mapped_column(TS)
    session_id: Mapped[int | None] = mapped_column(Integer)
    decided_at: Mapped[datetime | None] = mapped_column(TS)
    outcome_note: Mapped[str | None] = mapped_column(Text)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


class Objection(Base):
    __tablename__ = "objections"
    __table_args__ = (UniqueConstraint("proposal_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS)


class ClosureText(Base):
    """Kapanış önerisinin karar metinleri (ilk metin + rakipler)."""

    __tablename__ = "closure_texts"
    __table_args__ = (UniqueConstraint("proposal_id", "author_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    closure_text_id: Mapped[int] = mapped_column(ForeignKey("closure_texts.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


class Dissent(Base):
    """Şerh: kaybeden tarafın karara eklediği, silinemez azınlık görüşü."""

    __tablename__ = "dissents"
    __table_args__ = (UniqueConstraint("decision_id", "author_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    # Şerhin dayandığı kaybeden metin: yazarın sahibi olduğu ya da onay verdiği.
    closure_text_id: Mapped[int | None] = mapped_column(ForeignKey("closure_texts.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


class DelegationRequest(Base):
    """Havale isteği. Alan kişi kabul edene kadar BEKLIYOR'dur ve grafa girmez: ağırlığa, zincire
    ve Karar Saati anlık görüntüsüne yalnızca kabul edilmiş havaleler (graf kenarları) katılır.

    Durumlar: PENDING (bekliyor), ACCEPTED (kabul edildi, graf kenarı var), REJECTED (alan reddetti),
    EXPIRED (``havale_kabul_suresi`` içinde kabul edilmedi), RETURNED (alan kişi iade etti),
    CANCELLED (veren bekleyen isteği geri aldı ya da yenisiyle değiştirdi), ENDED (veren geri aldı
    ya da süresi doldu).
    """

    __tablename__ = "delegation_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    giver_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    area_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), index=True)
    created_at: Mapped[datetime] = mapped_column(TS)
    decide_by: Mapped[datetime] = mapped_column(TS)  # kabul için son an
    decided_at: Mapped[datetime | None] = mapped_column(TS)


class RegulationChange(Base):
    __tablename__ = "regulation_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), index=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # None: madde eklendi
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # None: madde kaldırıldı
    proposal_id: Mapped[int | None] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(TS)


# --- Karar Saati --------------------------------------------------------------------------------


class DecisionSession(Base):
    __tablename__ = "decision_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(TS, unique=True)
    opened_at: Mapped[datetime] = mapped_column(TS)
    closes_at: Mapped[datetime] = mapped_column(TS)
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    status: Mapped[str] = mapped_column(String(8), default="OPEN")  # OPEN | CLOSED
    regulation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    scripted: Mapped[bool] = mapped_column(Boolean, default=False)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))


class SessionItem(Base):
    """Bir oylama: pencere açılışındaki anlık görüntü ve kapanıştaki sonuç.

    Her önerinin seçmen kapsamında bir ana oylaması vardır. Bölünebilir kaynakta orantısız
    etkilenen her alt kapsam için ayrıca bir eşzamanlı oylama açılır (``concurrent``).
    """

    __tablename__ = "session_items"
    __table_args__ = (UniqueConstraint("session_id", "proposal_id", "vote_scope_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("decision_sessions.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    vote_scope_id: Mapped[str] = mapped_column(String(64))  # oylamanın seçmen kapsamı
    concurrent: Mapped[bool] = mapped_column(Boolean, default=False)
    area_id: Mapped[str | None] = mapped_column(String(64))
    eligible: Mapped[list[str]] = mapped_column(JSONB)
    resolved: Mapped[dict[str, str]] = mapped_column(JSONB)
    flagged: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Oyu açık olan seçmenler: açılıştaki ağırlığı 1'den büyük olanlar (başkalarının oyunu taşır)
    # ve Hâtif. Diğer oylar gizlidir; pencere boyunca değişmez.
    open_voters: Mapped[list[str]] = mapped_column(JSONB, default=list)
    oracle_note: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Ballot(Base):
    __tablename__ = "ballots"
    __table_args__ = (UniqueConstraint("session_id", "proposal_id", "vote_scope_id", "voter_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("decision_sessions.id"), index=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    vote_scope_id: Mapped[str] = mapped_column(String(64))
    voter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    choice: Mapped[Any] = mapped_column(JSONB)
    salt: Mapped[str] = mapped_column(String(64))
    commit: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS)
    commit_ledger_hash: Mapped[str | None] = mapped_column(String(64))
    reveal_ledger_hash: Mapped[str | None] = mapped_column(String(64))


class DevVotePlan(Base):
    """Yalnızca geliştirme: tohum kullanıcılarının demo oy planı (run-karar-saati uygular)."""

    __tablename__ = "dev_vote_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    voter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    choice: Mapped[Any] = mapped_column(JSONB)
    vote_scope_id: Mapped[str | None] = mapped_column(String(64))  # None: ana oylama


# --- defter -------------------------------------------------------------------------------------


class LedgerOutbox(Base):
    __tablename__ = "ledger_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[Any] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(TS)
    sent_at: Mapped[datetime | None] = mapped_column(TS, index=True)
    ledger_seq: Mapped[int | None] = mapped_column(BigInteger)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))
    ref_table: Mapped[str | None] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(40))
    ref_attr: Mapped[str | None] = mapped_column(String(40))


# --- Mahzen -------------------------------------------------------------------------------------


class CellarThread(Base):
    __tablename__ = "cellar_threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS)
    bumped_at: Mapped[datetime] = mapped_column(TS, index=True)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    revealed_at: Mapped[datetime | None] = mapped_column(TS)
    ledger_hash: Mapped[str | None] = mapped_column(String(64))
    draft_proposal_id: Mapped[int | None] = mapped_column(Integer)


class CellarPost(Base):
    __tablename__ = "cellar_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("cellar_threads.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    signed: Mapped[bool] = mapped_column(Boolean, default=False)


class CellarVote(Base):
    """"Öneriye dönüştür" oylaması. Başlık silinince onunla birlikte ölür."""

    __tablename__ = "cellar_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("cellar_threads.id", ondelete="CASCADE"), index=True
    )
    opened_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(TS)
    electorate: Mapped[list[str]] = mapped_column(JSONB)
    flagged: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(8), default="OPEN")  # OPEN | PASSED
    passed_at: Mapped[datetime | None] = mapped_column(TS)


class CellarBallot(Base):
    __tablename__ = "cellar_ballots"
    __table_args__ = (UniqueConstraint("vote_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vote_id: Mapped[int] = mapped_column(ForeignKey("cellar_votes.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    yes: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(TS)


class Notification(Base):
    """Site içi bildirim: kişinin oy verdiği ya da açtığı önerilerin sonucu (bkz. services/notifications).

    Yalnızca sahibine görünür; deftere yazılmaz. Metin üretildiği anda sabitlenir.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # KARAR_SAATI | SESSIZ_ONAY | YAVAS_SERIT
    title: Mapped[str] = mapped_column(String(200))
    lines: Mapped[list[str]] = mapped_column(JSONB, default=list)
    link: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(TS)
    read_at: Mapped[datetime | None] = mapped_column(TS)
