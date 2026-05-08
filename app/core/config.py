# ─────────────────────────────────────────────────────────────────
# app/core/config.py
# Configurações centrais da aplicação — lidas do arquivo .env
# Todas as variáveis de ambiente são validadas aqui via Pydantic
# ─────────────────────────────────────────────────────────────────

from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    """
    Configurações globais do Techá.
    Pydantic valida e converte os tipos automaticamente.
    lru_cache garante que o arquivo .env é lido apenas uma vez.
    """

    # ── Aplicação ─────────────────────────────────────────────────
    APP_NAME: str = "Techá"
    APP_ENV: Literal["development", "production"] = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ALLOWED_ORIGINS: str = (
        "https://app.techa.com.py,"
        "http://localhost:8081,"
        "http://localhost:19006,"
        "http://127.0.0.1:8081,"
        "http://127.0.0.1:19006"
    )
    CORS_ALLOWED_ORIGIN_REGEX: str = r"https://.*\.vercel\.app"
    SECRET_KEY: str

    # ── Banco de Dados ────────────────────────────────────────────
    DATABASE_URL: str          # async (asyncpg) — usado pela API
    DATABASE_URL_SYNC: str = ""  # sync (psycopg2) — usado pelo Alembic (derivado se vazio)

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ───────────────────────────────────────────────────────
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_DAYS: int = 30

    # ── Copernicus / Sentinel-2 ───────────────────────────────────
    COPERNICUS_CLIENT_ID: str = ""
    COPERNICUS_CLIENT_SECRET: str = ""
    COPERNICUS_TOKEN_URL: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/"
        "CDSE/protocol/openid-connect/token"
    )
    SENTINEL_STAC_URL: str = (
        "https://catalogue.dataspace.copernicus.eu/stac"
    )

    # ── Storage ───────────────────────────────────────────────────
    TILES_STORAGE_PATH: str = "/data/tiles"
    RASTER_STORAGE_PATH: str = "/data/rasters"

    # ── Email ─────────────────────────────────────────────────────
    # Resend (HTTP API — recomendado em produção/Railway)
    RESEND_API_KEY: str = ""          # ex: re_xxxxxxxxxxxx
    EMAIL_FROM_ADDRESS: str = "noreply@techa.com.py"  # deve ser domínio verificado no Resend

    # Gmail SMTP (fallback para desenvolvimento local)
    GMAIL_USER: str = ""              # ex: caiolamberts@gmail.com
    GMAIL_APP_PASSWORD: str = ""      # Senha de App do Google

    EMAIL_FROM_NAME: str = "Techá - InnovAgro"
    RESET_CODE_TTL_MINUTES: int = 15  # validade do código OTP

    # ── Firebase ──────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = ""

    # ── Regras de Negócio (Motor de Alertas) ──────────────────────
    SENTINEL_CHECK_INTERVAL_MINUTES: int = 30
    CLOUD_COVER_THRESHOLD: float = 20.0   # % máximo de nuvem aceito
    NDVI_DROP_THRESHOLD: float = 15.0     # % mínimo de queda de NDVI

    # ── Pipeline e deploy ─────────────────────────────────────────
    ENABLE_PIPELINE: bool = True          # permite desabilitar scheduler em hosts API-only

    # ── Thresholds de Área por Tamanho de Talhão ──────────────────
    # (corresponde à regra de negócio validada com o agrônomo)
    ALERT_AREA_PCT_SMALL: float = 3.0     # talhões até 100ha
    ALERT_AREA_PCT_MEDIUM: float = 2.0    # talhões 100-500ha
    ALERT_AREA_PCT_LARGE: float = 1.5     # talhões acima de 500ha
    ALERT_AREA_MIN_HA_LARGE: float = 10.0 # mínimo absoluto para grandes

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        # Railway / Heroku fornecem "postgres://" ou "postgresql://"
        # SQLAlchemy+asyncpg exige "postgresql+asyncpg://"
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL deve começar com 'postgresql'")
        return v

    @field_validator("DATABASE_URL_SYNC")
    @classmethod
    def validate_db_url_sync(cls, v: str) -> str:
        # Normaliza "postgres://" para "postgresql://"
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        return v

    def model_post_init(self, __context) -> None:
        # Se DATABASE_URL_SYNC não foi definido, deriva do DATABASE_URL
        if not self.DATABASE_URL_SYNC:
            sync_url = self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            object.__setattr__(self, "DATABASE_URL_SYNC", sync_url)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna instância única das configurações (Singleton via cache).
    Uso: from app.core.config import get_settings; s = get_settings()
    """
    return Settings()


# Instância global para imports diretos
settings = get_settings()
