# app/core/limiter.py
# Instância compartilhada do rate limiter (slowapi)
# Importada em main.py e nos routers que precisam de limites por rota.

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
