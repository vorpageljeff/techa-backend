# app/core/logging.py
# Configuração do Loguru — logging estruturado para o Techá
import sys
from loguru import logger
from app.core.config import settings


def setup_logging() -> None:
    """Configura o Loguru com formato adequado para cada ambiente."""
    logger.remove()  # Remove handler padrão

    fmt_dev = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )
    fmt_prod = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}"

    fmt = fmt_dev if not settings.is_production else fmt_prod

    # Reconfigura stdout para UTF-8 para suportar emojis no Windows
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    logger.add(sys.stdout, format=fmt, level="DEBUG" if settings.APP_DEBUG else "INFO", colorize=not settings.is_production)

    if settings.is_production:
        logger.add(
            "logs/techa_{time:YYYY-MM-DD}.log",
            rotation="00:00",    # novo arquivo por dia
            retention="30 days",
            compression="gz",
            level="INFO",
            format=fmt_prod,
        )

    logger.info(f"[OK] Techa iniciando — ambiente: {settings.APP_ENV}")
