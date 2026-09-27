from datetime import date

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx
from mesveret.services import auth

router = APIRouter(prefix="/auth", tags=["kimlik"])


class RegisterIn(BaseModel):
    full_name: str
    email: EmailStr
    nickname: str
    password: str
    birth_date: date
    city: str
    district: str
    address_line: str = ""


class VerifyIn(BaseModel):
    email: EmailStr
    code: str


class ResendIn(BaseModel):
    email: EmailStr


class LoginIn(BaseModel):
    identifier: str
    password: str


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    user = auth.register(ctx, auth.RegisterData(**body.model_dump()))
    return {
        "nickname": user.nickname,
        "message": "Kayıt alındı. E-posta adresinize gönderilen doğrulama kodunu girin "
        "(geliştirme ortamında kod sunucu konsoluna basılır).",
    }


@router.post("/verify")
def verify(body: VerifyIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    user = auth.verify_email(ctx, body.email, body.code)
    return {"nickname": user.nickname, "message": "E-posta adresiniz doğrulandı; giriş yapabilirsiniz."}


@router.post("/resend")
def resend(body: ResendIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    auth.resend_code(ctx, body.email)
    return {"message": "Hesap doğrulanmamışsa yeni bir kod gönderildi."}


@router.post("/login")
def login(body: LoginIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    token, user = auth.login(ctx, body.identifier, body.password)
    return {"token": token, "nickname": user.nickname, "user_id": user.id}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"user_id": user.id, "nickname": user.nickname, "role": user.role,
            "cellar_warned": user.cellar_warned_at is not None}
