"""Defter düğümü HTTP servisi. (f) aşamasında zincir, çoğaltma ve doğrulama eklenir."""

import os

from fastapi import FastAPI

NODE_ID = os.environ.get("NODE_ID", "ledger-local")
ROLE = os.environ.get("ROLE", "leader")

app = FastAPI(title=f"Meşveret defteri ({NODE_ID})")


@app.get("/health")
def health() -> dict:
    return {"durum": "ok", "dugum": NODE_ID, "rol": ROLE}
