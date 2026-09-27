from datetime import timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.db.models import User, VerificationCode
from mesveret.domain.counselor import counselor_areas
from mesveret.services import delegation, ontology
from tests.integration.world import make_user

REG = {
    "full_name": "Ayşe Yılmaz",
    "email": "ayse@example.com",
    "nickname": "ayse",
    "password": "gizli-parola",
    "birth_date": "1996-04-12",
    "city": "İstanbul",
    "district": "Kadıköy",
    "address_line": "Moda Cad. 1",
}


def latest_code(db, email):
    user = db.execute(select(User).where(User.email == email)).scalar_one()
    return db.execute(
        select(VerificationCode.code).where(VerificationCode.user_id == user.id)
        .order_by(VerificationCode.id.desc())
    ).scalars().first()


def register_and_verify(client, db, **overrides):
    body = {**REG, **overrides}
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    code = latest_code(db, body["email"])
    r = client.post("/auth/verify", json={"email": body["email"], "code": code})
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", json={"identifier": body["nickname"], "password": body["password"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# --- kayıt ve doğrulama --------------------------------------------------------------------------


def test_register_requires_email_verification_before_login(client, db):
    r = client.post("/auth/register", json=REG)
    assert r.status_code == 201
    assert "doğrulama kodu" in r.json()["message"]
    r = client.post("/auth/login", json={"identifier": "ayse", "password": REG["password"]})
    assert r.status_code == 403
    assert "doğrula" in r.json()["detail"]


def test_wrong_code_is_rejected(client, db):
    client.post("/auth/register", json=REG)
    r = client.post("/auth/verify", json={"email": REG["email"], "code": "000000"})
    assert r.status_code == 422


def test_verification_creates_general_city_and_age_memberships(client, db, graph):
    register_and_verify(client, db)
    user = db.execute(select(User).where(User.nickname == "ayse")).scalar_one()
    scopes = {m.scope_id for m in graph.memberships(user.id)}
    assert scopes == {"genel", "sehir:istanbul", "yas:25-34"}


def test_new_city_scope_is_created_on_demand(client, db, graph):
    register_and_verify(client, db, city="Trabzon")
    assert graph.scope("sehir:trabzon").name == "Trabzon"
    assert graph.is_strict_subset("sehir:trabzon", "genel")


def test_under_18_cannot_register(client):
    r = client.post("/auth/register", json={**REG, "birth_date": "2010-01-01"})
    assert r.status_code == 422
    assert "18" in r.json()["detail"]


def test_nickname_is_unique_case_insensitively(client, db):
    register_and_verify(client, db)
    r = client.post("/auth/register", json={**REG, "nickname": "AYSE", "email": "baska@example.com"})
    assert r.status_code == 409


def test_reserved_nicknames_are_rejected(client):
    for nick in ("Hatif", "hâtif", "Gölge"):
        r = client.post("/auth/register", json={**REG, "nickname": nick})
        assert r.status_code == 422, nick


def test_unknown_city_is_rejected(client):
    r = client.post("/auth/register", json={**REG, "city": "Atlantis"})
    assert r.status_code == 422


# --- giriş ---------------------------------------------------------------------------------------


def test_login_with_nickname_or_email_and_me(client, db):
    register_and_verify(client, db)
    for ident in ("ayse", "AYSE@example.com"):
        r = client.post("/auth/login", json={"identifier": ident, "password": REG["password"]})
        assert r.status_code == 200
    token = r.json()["token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["nickname"] == "ayse"
    user = db.execute(select(User).where(User.nickname == "ayse")).scalar_one()
    db.refresh(user)
    assert user.last_login_at is not None


def test_wrong_password_is_unauthorized(client, db):
    register_and_verify(client, db)
    r = client.post("/auth/login", json={"identifier": "ayse", "password": "yanlis-parola"})
    assert r.status_code == 401


def test_protected_endpoint_requires_token(client):
    assert client.get("/auth/me").status_code == 401


# --- profil --------------------------------------------------------------------------------------


def test_public_profile_hides_private_fields(client, db):
    headers = register_and_verify(client, db)
    public = client.get("/users/ayse").json()
    for key in ("full_name", "email", "birth_date", "address"):
        assert key not in public
    assert public["roles"] == ["Yurttaş"]
    own = client.get("/me/profile", headers=headers).json()
    assert own["full_name"] == "Ayşe Yılmaz"
    assert own["address"]["district"] == "Kadıköy"
    assert own["birth_date"] == "1996-04-12"


def test_profile_of_self_via_public_route_still_hides_private_fields(client, db):
    headers = register_and_verify(client, db)
    body = client.get("/users/ayse", headers=headers).json()
    assert "full_name" not in body
    assert body["is_self"] is True


def test_address_change_waits_ninety_days_in_new_city(client, db, ctx):
    headers = register_and_verify(client, db)
    r = client.put("/me/address", headers=headers,
                   json={"city": "Ankara", "district": "Çankaya", "address_line": ""})
    assert r.status_code == 200
    user = db.execute(select(User).where(User.nickname == "ayse")).scalar_one()
    scopes = {m.scope_id for m in ctx.graph.memberships(user.id)}
    assert "sehir:istanbul" not in scopes and "sehir:ankara" in scopes
    now = clock.now(db)
    assert not ontology.vote_right(ctx.at(now + timedelta(days=89)), user.id, "sehir:ankara").has_right
    assert ontology.vote_right(ctx.at(now + timedelta(days=90)), user.id, "sehir:ankara").has_right
    own = client.get("/me/profile", headers=headers).json()
    ankara = next(m for m in own["memberships"] if m["scope_id"] == "sehir:ankara")
    assert ankara["has_vote_right"] is False
    assert ankara["vote_right_from"] is not None


def test_interest_membership_waits_fourteen_days(client, db, ctx):
    headers = register_and_verify(client, db)
    r = client.post("/me/interests/sinema", headers=headers)
    assert r.status_code == 200
    user = db.execute(select(User).where(User.nickname == "ayse")).scalar_one()
    now = clock.now(db)
    assert not ontology.vote_right(ctx.at(now), user.id, "ilgi:sinema").has_right
    assert ontology.vote_right(ctx.at(now + timedelta(days=14)), user.id, "ilgi:sinema").has_right
    assert client.delete("/me/interests/sinema", headers=headers).status_code == 200
    assert "ilgi:sinema" not in {m.scope_id for m in ctx.graph.memberships(user.id)}


def test_counselor_label_appears_after_threshold(ctx, client):
    musavir = make_user(ctx, "musavir")
    for i in range(5):
        u = make_user(ctx, f"yurttas{i}")
        delegation.set_delegation(ctx, u, "musavir", "sinema")
    ctx.db.commit()
    assert counselor_areas(ctx.graph.incoming_delegations(musavir.id), ctx.reg) == ["sinema"]
    body = client.get("/users/musavir").json()
    assert body["counselor_areas"] == [{"area_id": "sinema", "name": "Sinema", "count": 5}]
    assert "Müşavir" in body["roles"]


def test_oracle_profile(client):
    body = client.get("/users/Hâtif").json()
    assert body["roles"] == ["Hâtif"]
