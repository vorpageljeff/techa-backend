# ─────────────────────────────────────────────────────────────────
# app/main.py
# Entrypoint da aplicação FastAPI — Techá by InnovAgro Py
# ─────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from loguru import logger

from app.core.config import settings
from app.core.database import check_db_connection
from app.core.logging import setup_logging

# Importa routers
from app.api.v1 import auth, farms, fields, anomalies, dashboard, admin

# ── Rate Limiter (por IP) — 120 req/min geral, 10 req/min para login ──
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.
    Código ANTES do yield: executado na inicialização.
    Código APÓS o yield:   executado no encerramento.
    """
    # ── Startup ──────────────────────────────────────────────────
    setup_logging()
    logger.info("🚀 Techá API iniciando...")

    # Verifica conexão com banco
    db_ok = await check_db_connection()
    if not db_ok:
        logger.error("❌ Não foi possível conectar ao banco de dados!")
        raise RuntimeError("Banco de dados inacessível")
    logger.info("✅ Banco de dados conectado")

    # Inicia o scheduler de verificação do Sentinel-2
    # (importado aqui para evitar import circular)
    from app.pipeline.scheduler import start_scheduler
    scheduler = start_scheduler()
    logger.info("✅ Scheduler Sentinel-2 iniciado")

    yield  # aplicação rodando

    # ── Shutdown ─────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("👋 Techá API encerrada")


# ── Criação da aplicação ──────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="API de Inteligência de Campo — Monitoramento de Satélite para o Agronegócio Paraguaio",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://app.techa.com.py"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────
PREFIX = "/api/v1"
app.include_router(auth.router,       prefix=PREFIX, tags=["Auth"])
app.include_router(farms.router,      prefix=PREFIX, tags=["Fazendas"])
app.include_router(fields.router,     prefix=PREFIX, tags=["Talh\u00f5es"])
app.include_router(anomalies.router,  prefix=PREFIX, tags=["Anomalias"])
app.include_router(dashboard.router,  prefix=PREFIX, tags=["Dashboard"])
app.include_router(admin.router,      prefix=PREFIX, tags=["Admin"])


# ── Health Check ──────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health_check():
    """Verifica se a API está no ar. Usado por load balancers e monitoramento."""
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "1.0.0",
        "service": "Tech" + chr(0xe1),  # chr(0xe1)=á, encoding-safe em qualquer locale
        "environment": settings.APP_ENV,
        "database": "connected" if db_ok else "error",
    }


# ── Execução direta (desenvolvimento) ────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
        log_level="debug" if settings.APP_DEBUG else "info",
    )
