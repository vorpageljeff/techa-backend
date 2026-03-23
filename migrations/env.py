# ─────────────────────────────────────────────────────────────────
# migrations/env.py
# Configuração do Alembic para o projeto Techá
# ─────────────────────────────────────────────────────────────────

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Importa a Base e todos os models para que o Alembic os detecte
from app.core.database import Base
import app.models  # noqa: F401 — importa todos os models via __init__.py

# Alembic Config object (acesso ao alembic.ini)
config = context.config

# Interpreta o arquivo de configuração de logging do alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata de todos os models — necessário para --autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Obtém a URL do banco de dados (sync) do ambiente ou alembic.ini."""
    url = os.getenv("DATABASE_URL_SYNC", "")
    if not url:
        url = config.get_main_option("sqlalchemy.url", "")
    # Normaliza postgres:// -> postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # Remove prefixo asyncpg se presente
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url[len("postgresql+asyncpg://"):]
    return url


def run_migrations_offline() -> None:
    """
    Modo offline: gera SQL sem conectar ao banco.
    Útil para revisar antes de aplicar.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo online: conecta ao banco e aplica as migrations.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
