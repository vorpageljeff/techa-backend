# ─────────────────────────────────────────────────────────────────
# app/core/database.py
# Conexão assíncrona com PostgreSQL via SQLAlchemy 2.0 + asyncpg
# ─────────────────────────────────────────────────────────────────

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from loguru import logger

from app.core.config import settings


# ── Engine assíncrona ─────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,       # loga queries SQL em development
    pool_size=10,                  # conexões simultâneas no pool
    max_overflow=20,               # conexões extras em pico
    pool_pre_ping=True,            # verifica conexão antes de usar
    pool_recycle=3600,             # recicla conexões a cada 1h
)

# ── Session factory ───────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,        # mantém objetos acessíveis após commit
    autocommit=False,
    autoflush=False,
)


# ── Base declarativa para todos os models ─────────────────────────
class Base(DeclarativeBase):
    """
    Classe base para todos os models SQLAlchemy do Techá.
    Todos os models em app/models/ herdam desta classe.
    """
    pass


# ── Dependency injection para rotas FastAPI ───────────────────────
async def get_db() -> AsyncSession:
    """
    Dependency do FastAPI que fornece uma sessão de banco de dados.
    Garante que a sessão é fechada mesmo em caso de exceção.

    Uso nas rotas:
        async def minha_rota(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Healthcheck do banco ──────────────────────────────────────────
async def check_db_connection() -> bool:
    """Verifica se o banco está acessível. Usado no /health endpoint."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Falha na conexão com o banco: {e}")
        return False


# ── Criação das tabelas (apenas desenvolvimento) ──────────────────
async def create_tables() -> None:
    """
    Cria todas as tabelas definidas nos models.
    Em produção, usar Alembic (migrations/) no lugar desta função.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Tabelas criadas com sucesso")
