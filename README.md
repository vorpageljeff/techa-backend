# 🌱 Techá — Back-end API
**by InnovAgro Py** | Inteligência de Campo para o Agronegócio Paraguaio

## Stack
- **Python 3.11+** + **FastAPI** + **SQLAlchemy 2.0 async**
- **PostgreSQL 15 + PostGIS** (dados geoespaciais)
- **Redis + RQ** (fila de processamento)
- **Rasterio + NumPy** (processamento de imagens Sentinel-2)

## Primeiros Passos

### 1. Pré-requisitos
```bash
# Docker e Docker Compose instalados
docker --version && docker compose version

# Python 3.11+
python --version
```

### 2. Clone e configure
```bash
git clone <repo-url>
cd techa-backend
cp .env.example .env
# Edite o .env com suas credenciais
```

### 3. Suba o banco e o Redis
```bash
docker compose up -d
# Aguarde: "techa_db" e "techa_redis" ficarem healthy
docker compose ps
```

### 4. Ambiente virtual Python
```bash
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
# .venv\Scripts\activate        # Windows

# GDAL deve ser instalado via sistema ANTES do pip:
# Ubuntu: sudo apt-get install gdal-bin libgdal-dev
pip install -r requirements.txt
```

### 5. Execute as migrations
```bash
alembic upgrade head
```

### 6. Inicie a API
```bash
python -m app.main
# ou
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Execução em ambiente de produção / deploy
- A API principal pode ser executada em qualquer host ou container com conexão ao PostgreSQL e Redis.
- O pipeline de Sentinel-2 é iniciado automaticamente apenas quando `ENABLE_PIPELINE=true`.
- Para rodar a API sem o scheduler no mesmo serviço (útil para deploy serverless ou plataforma de APIs), use:
  ```bash
  ENABLE_PIPELINE=false uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```
- Use `docker compose up --build` para iniciar `db`, `redis` e `api` juntos localmente.

### Observação sobre Vercel
- Vercel é otimizado para funções serverless e frontends. Este projeto é um backend FastAPI com agendador e uso de Postgres/Redis, portanto não é uma boa escolha para deploy completo.
- Para um backend como este, prefira plataformas que suportam containers ou processos long-running, como Railway, Render, Fly.io, Heroku ou DigitalOcean.
- Se você quiser uma versão online rápida, o mais prático é criar um container Docker e implantar em uma dessas plataformas.

### Android / mobile
- Esta API já está preparada para ser consumida por um app Android: basta que o app aponte para o endpoint HTTPS público.
- O projeto atual é o backend; o cliente Android precisa ser um app separado que consuma as rotas `/api/v1/...`.
- O uso de `FastAPI` significa que qualquer app Android pode se conectar sem mudanças na API, desde que a API esteja hospedada e acessível na internet.

### 7. Acesse a documentação
- Swagger UI: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Testes
```bash
pytest tests/ -v --cov=app
```

## Estrutura do Projeto
```
techa-backend/
├── app/
│   ├── main.py              # Entrypoint FastAPI
│   ├── core/
│   │   ├── config.py        # Configurações (.env via Pydantic)
│   │   ├── database.py      # Conexão PostgreSQL async
│   │   ├── security.py      # JWT + bcrypt
│   │   └── logging.py       # Loguru
│   ├── models/              # SQLAlchemy ORM + PostGIS
│   ├── schemas/             # Pydantic (request/response)
│   ├── api/v1/              # Routers FastAPI
│   ├── services/            # Lógica de negócio
│   ├── repositories/        # Queries ao banco
│   └── pipeline/            # Processamento Sentinel-2
│       ├── scheduler.py     # Cron job (APScheduler)
│       ├── downloader.py    # Download Sentinel-2
│       ├── preprocessor.py  # SCL Mask
│       ├── ndvi.py          # Cálculo NDVI
│       ├── anomaly.py       # Motor de detecção
│       └── tiles.py         # Geração PMTiles
├── tests/
│   ├── unit/                # Testes sem banco (rápidos)
│   └── integration/         # Testes com banco real
├── migrations/              # Alembic
├── scripts/
│   └── init_db.sql          # PostGIS extension
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── pytest.ini
```

## Sprints
| Sprint | Status | Entregável |
|--------|--------|------------|
| **Sprint 1** | 🔨 Em progresso | Pipeline Sentinel + API REST |
| **Sprint 2** | ⏳ Aguardando | Push Notifications + FCM |
| **Sprint 3** | ⏳ Aguardando | App React Native |
| **Sprint 4** | ⏳ Aguardando | Modo Offline completo |

## Contato
Caio Lambert — caio@innovagropy.com | Hernandarias, Paraguay
