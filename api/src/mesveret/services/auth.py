"""Kayıt, sahte e-posta doğrulaması, giriş ve JWT."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import func, or_, select

from mesveret.clock import ISTANBUL
from mesveret.config import Settings
from mesveret.context import Ctx
from mesveret.data.iller import ILLER
from mesveret.db.models import User, VerificationCode
from mesveret.domain.scopes import age_on
from mesveret.domain.text import turkish_lower
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound, Unauthorized
from mesveret.services import interactions, ontology

log = logging.getLogger("mesveret.auth")

HASHER = PasswordHasher()
NICKNAME_RE = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû_.\-]{3,24}$")
RESERVED = {"hatif", "golge", "sistem", "yonetim", "mesveret"}
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def nickname_key(nickname: str) -> str:
    return turkish_lower(nickname.strip())


def _folded(nickname: str) -> str:
    return nickname_key(nickname).translate(_FOLD)


@dataclass
class RegisterData:
    full_name: str
    email: str
    nickname: str
    password: str
    birth_date: date
    city: str
    district: str
    address_line: str = ""


def _validate(ctx: Ctx, d: RegisterData) -> None:
    if not NICKNAME_RE.match(d.nickname.strip()):
        raise DomainError(
            "Takma ad 3–24 karakter olmalı; harf, rakam, alt çizgi, nokta ve tire içerebilir."
        )
    if _folded(d.nickname) in RESERVED:
        raise DomainError("Bu takma ad ayrılmış; başka bir takma ad seçin.")
    if len(d.full_name.strip()) < 3:
        raise DomainError("Ad soyad en az 3 karakter olmalı.")
    if len(d.password) < 8:
        raise DomainError("Şifre en az 8 karakter olmalı.")
    if d.city not in ILLER:
        raise DomainError("İl, Türkiye'nin 81 ilinden biri olmalı.")
    if not 2 <= len(d.district.strip()) <= 60:
        raise DomainError("İlçe 2–60 karakter olmalı.")
    today = ctx.now.astimezone(ISTANBUL).date()
    if d.birth_date > today:
        raise DomainError("Doğum tarihi gelecekte olamaz.")
    if age_on(d.birth_date, today) < 18:
        raise DomainError("Kayıt için 18 yaşını doldurmuş olmalısınız.")
    key = nickname_key(d.nickname)
    if ctx.db.execute(select(User.id).where(User.nickname_key == key)).first():
        raise Conflict("Bu takma ad kullanılıyor.")
    if ctx.db.execute(select(User.id).where(User.email == d.email.lower())).first():
        raise Conflict("Bu e-posta adresiyle kayıtlı bir hesap var.")


def _new_user(ctx: Ctx, d: RegisterData, *, verified: bool, user_id: str | None = None) -> User:
    user = User(
        id=user_id or str(uuid.uuid4()),
        nickname=d.nickname.strip(),
        nickname_key=nickname_key(d.nickname),
        full_name=d.full_name.strip(),
        email=d.email.lower(),
        password_hash=HASHER.hash(d.password),
        birth_date=d.birth_date,
        city=d.city,
        district=d.district.strip(),
        address_line=d.address_line.strip() or None,
        role="CITIZEN",
        email_verified=verified,
        created_at=ctx.now,
    )
    ctx.db.add(user)
    ctx.db.flush()
    return user


def _issue_code(ctx: Ctx, user: User) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    ctx.db.add(VerificationCode(user_id=user.id, code=code, created_at=ctx.now))
    # Sahte doğrulama servisi: kod konsola basılır (docker compose logs api).
    print(f"[SAHTE E-POSTA] {user.email} için doğrulama kodu: {code}", flush=True)
    log.info("doğrulama kodu üretildi: %s", user.email)
    return code


def register(ctx: Ctx, d: RegisterData) -> User:
    _validate(ctx, d)
    user = _new_user(ctx, d, verified=False)
    _issue_code(ctx, user)
    ctx.commit()
    return user


def _activate(ctx: Ctx, user: User) -> None:
    user.email_verified = True
    ontology.register_memberships(ctx, user)
    interactions.on_registration(ctx, user)


def create_verified_user(ctx: Ctx, *, user_id: str | None = None, **fields) -> User:
    """Tohum ve testler için: doğrulanmış kullanıcıyı ``ctx.now`` anında oluşturur. Tohum sabit
    kimlik verir (takma addan türetilmiş): Gölge kimlikleri ve takma kimlikler her tohumda aynı."""
    d = RegisterData(**fields)
    _validate(ctx, d)
    user = _new_user(ctx, d, verified=True, user_id=user_id)
    _activate(ctx, user)
    return user


def verify_email(ctx: Ctx, email: str, code: str) -> User:
    user = ctx.db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None:
        raise NotFound("Bu e-posta adresiyle kayıt bulunamadı.")
    if user.email_verified:
        raise Conflict("E-posta adresi zaten doğrulanmış.")
    row = ctx.db.execute(
        select(VerificationCode).where(
            VerificationCode.user_id == user.id, VerificationCode.used_at.is_(None)
        ).order_by(VerificationCode.id.desc())
    ).scalars().first()
    if row is None or not secrets.compare_digest(row.code, code.strip()):
        raise DomainError("Doğrulama kodu hatalı.")
    row.used_at = ctx.now
    _activate(ctx, user)
    ctx.commit()
    return user


def resend_code(ctx: Ctx, email: str) -> None:
    user = ctx.db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if user is None or user.email_verified:
        return  # hesap varlığını sızdırmamak için sessiz
    _issue_code(ctx, user)
    ctx.commit()


def login(ctx: Ctx, identifier: str, password: str) -> tuple[str, User]:
    ident = identifier.strip()
    user = ctx.db.execute(
        select(User).where(or_(User.nickname_key == nickname_key(ident),
                               func.lower(User.email) == ident.lower()))
    ).scalar_one_or_none()
    if user is None or user.password_hash is None:
        raise Unauthorized("Takma ad / e-posta ya da şifre hatalı.")
    try:
        HASHER.verify(user.password_hash, password)
    except VerificationError as exc:
        raise Unauthorized("Takma ad / e-posta ya da şifre hatalı.") from exc
    if not user.email_verified:
        raise Forbidden("Giriş yapmadan önce e-posta adresinizi doğrulayın.")
    user.last_login_at = ctx.now
    ontology.sync_age_membership(ctx, user)
    ctx.commit()
    return create_token(ctx.settings, user.id), user


def create_token(settings: Settings, user_id: str) -> str:
    now = datetime.now(UTC)  # JWT süresi gerçek saate göredir, sahte saate değil
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=settings.jwt_ttl_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(settings: Settings, token: str) -> str:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError as exc:
        raise Unauthorized("Oturum geçersiz ya da süresi dolmuş; yeniden giriş yapın.") from exc
