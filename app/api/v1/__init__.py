"""
app/api/v1/__init__.py
──────────────────────
Agrega todos os routers da API v1 em um único router.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.farms import router as farms_router
from app.api.v1.fields import router as fields_router
from app.api.v1.anomalies import router as anomalies_router

router = APIRouter()

router.include_router(auth_router,      prefix="/auth",      tags=["Autenticação"])
router.include_router(farms_router,     prefix="/farms",     tags=["Fazendas"])
router.include_router(fields_router,    prefix="/fields",    tags=["Talhões"])
router.include_router(anomalies_router, prefix="/anomalies", tags=["Anomalias"])
