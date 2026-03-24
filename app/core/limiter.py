# app/core/limiter.py
# Instância compartilhada do rate limiter (slowapi)
# Importada em main.py e nos routers que precisam de limites por rota.

from fastapi import Request
from slowapi import Limiter


def _get_real_ip(request: Request) -> str:
    """
    Extrai o IP real do cliente, respeitando proxy reverso (Railway / Nginx).
    Usa X-Forwarded-For se disponível, senão usa o IP de conexão direta.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_real_ip, default_limits=["120/minute"])
