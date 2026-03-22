# RELATÓRIO DE IMPLEMENTAÇÃO — Sprint 1
**Projeto:** Techá / InnovAgro Py
**Data:** 2026-03-16
**Status:** API REST completa + servidores rodando

---

## RESUMO EXECUTIVO

Partindo de um projeto com ~30% de implementação real (apenas infraestrutura e models), foram implementados todos os endpoints da API REST, corrigidos bugs críticos de dependência e configurado o ambiente de desenvolvimento local.

**Antes:** 4 routers vazios, 5 arquivos de pipeline inexistentes, zero schemas
**Depois:** 13 endpoints funcionando, banco conectado, API respondendo em localhost:8000

---

## ARQUIVOS CRIADOS

### Schemas Pydantic (`app/schemas/`)

| Arquivo | Conteúdo |
|---------|----------|
| `auth.py` | `UserRegister`, `UserLogin`, `TokenResponse`, `UserResponse` |
| `farm.py` | `FarmCreate` (validação area_ha > 0), `FarmUpdate`, `FarmResponse` |
| `field.py` | `FieldCreate` (validação GeoJSON Polygon/MultiPolygon), `FieldResponse` |
| `anomaly.py` | `AnomalyResponse`, `AnomalyConfirmRequest`, `AnomalyDismissRequest` |

### Outros
| Arquivo | Conteúdo |
|---------|----------|
| `.env` | Variáveis de ambiente para desenvolvimento local (criado a partir do .env.example) |
| `start-api.bat` | Script que navega para a pasta correta e inicia o uvicorn |
| `.claude/launch.json` | Configuração dos servidores dev para Claude Code |
| `AUDITORIA_STUBS.md` | Relatório detalhado de todos os stubs encontrados |

---

## ARQUIVOS MODIFICADOS

### `app/models/farm.py`
**Problema:** modelo não tinha `area_ha` nem `crop`, campos usados na regra de negócio
**Correção:** adicionadas as colunas:
```python
area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
crop:    Mapped[str | None]   = mapped_column(String(100), nullable=True)
```

### `app/core/security.py`
**Problema:** usava `passlib` que tem bug de compatibilidade com bcrypt >= 4.x
**Correção:** substituído por `bcrypt` direto:
```python
# ANTES
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# DEPOIS
import bcrypt as _bcrypt
def hash_password(plain): return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()
def verify_password(plain, hashed): return _bcrypt.checkpw(plain.encode(), hashed.encode())
```

### `requirements.txt`
```diff
- passlib[bcrypt]==1.7.4
+ bcrypt==4.1.3
+ email-validator==2.1.1
```

---

## ENDPOINTS IMPLEMENTADOS

### Auth (`app/api/v1/auth.py`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| POST | `/api/v1/auth/register` | Registrar usuário (name, email, password) | ❌ |
| POST | `/api/v1/auth/login` | Login → retorna Bearer JWT | ❌ |
| GET  | `/api/v1/auth/me` | Dados do usuário logado | ✅ JWT |

**Detalhes:**
- Registro valida e-mail duplicado → HTTP 409
- Senha mínima 6 caracteres
- Login retorna token válido por 30 dias (configurável via `JWT_EXPIRY_DAYS`)
- Mensagem de erro genérica no login (não revela se e-mail existe)

---

### Fazendas (`app/api/v1/farms.py`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| POST   | `/api/v1/farms` | Criar fazenda | ✅ JWT |
| GET    | `/api/v1/farms` | Listar fazendas do usuário | ✅ JWT |
| GET    | `/api/v1/farms/{farm_id}` | Detalhe de uma fazenda | ✅ JWT |
| PATCH  | `/api/v1/farms/{farm_id}` | Atualizar campos da fazenda | ✅ JWT |
| DELETE | `/api/v1/farms/{farm_id}` | Deletar fazenda (cascade nos talhões) | ✅ JWT |

**Campos aceitos no POST/PATCH:**
```json
{
  "name": "Fazenda São João",
  "area_ha": 320,
  "crop": "soja",
  "city": "Hernandarias",
  "state": "Alto Paraná"
}
```

---

### Talhões (`app/api/v1/fields.py`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| POST   | `/api/v1/farms/{farm_id}/fields` | Criar talhão com polígono GeoJSON | ✅ JWT |
| GET    | `/api/v1/farms/{farm_id}/fields` | Listar talhões da fazenda | ✅ JWT |
| GET    | `/api/v1/fields/{field_id}` | Detalhe + geometria GeoJSON | ✅ JWT |
| DELETE | `/api/v1/fields/{field_id}` | Deletar talhão (cascade nas análises) | ✅ JWT |

**Campos aceitos no POST:**
```json
{
  "name": "Talhão 1",
  "crop": "soja",
  "planting_date": "2025-10-15",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lng, lat], [lng, lat], ...]]
  }
}
```

**Cálculo automático de área:** usa `pyproj` (WGS84) → `area_ha` calculado e salvo automaticamente
**Auto-reparo de geometria:** `shapely.buffer(0)` corrige polígonos levemente inválidos

---

### Anomalias (`app/api/v1/anomalies.py`)

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| GET    | `/api/v1/anomalies` | Listar todas as anomalias do usuário | ✅ JWT |
| GET    | `/api/v1/anomalies/{anomaly_id}` | Detalhe de uma anomalia | ✅ JWT |
| PATCH  | `/api/v1/anomalies/{anomaly_id}/confirm` | Produtor confirma no campo | ✅ JWT |
| PATCH  | `/api/v1/anomalies/{anomaly_id}/dismiss` | Produtor descarta (falso positivo) | ✅ JWT |

**Fluxo de status:**
```
active → inspected  (via /confirm)
active → dismissed  (via /dismiss)
```

**Isolamento de dados:** join `anomalies → fields → farms → users` garante que o usuário só vê suas próprias anomalias.

---

## TESTES PARA VALIDAR

### 1. Registrar usuário
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"João Silva","email":"joao@fazenda.py","password":"senha123"}'
# Esperado: HTTP 201 com id, name, email, plan
```

### 2. Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"joao@fazenda.py","password":"senha123"}'
# Esperado: HTTP 200 com {"access_token":"eyJ...","token_type":"bearer"}
# Salve o token → TOKEN=<valor retornado>
```

### 3. Criar fazenda
```bash
curl -X POST http://localhost:8000/api/v1/farms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Fazenda São João","area_ha":320,"crop":"soja","city":"Hernandarias"}'
# Esperado: HTTP 201 com id da fazenda
```

### 4. Listar fazendas
```bash
curl http://localhost:8000/api/v1/farms \
  -H "Authorization: Bearer $TOKEN"
# Esperado: HTTP 200 com array de fazendas
```

### 5. Criar talhão
```bash
curl -X POST http://localhost:8000/api/v1/farms/<FARM_ID>/fields \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Talhão Norte",
    "crop": "soja",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[
        [-55.1, -25.1], [-55.0, -25.1], [-55.0, -25.0], [-55.1, -25.0], [-55.1, -25.1]
      ]]
    }
  }'
# Esperado: HTTP 201 com area_ha calculada automaticamente
```

### 6. Listar anomalias
```bash
curl http://localhost:8000/api/v1/anomalies \
  -H "Authorization: Bearer $TOKEN"
# Esperado: HTTP 200 com array vazio [] (pipeline ainda não rodou)
```

### 7. Health check
```bash
curl http://localhost:8000/health
# Esperado: {"status":"ok","database":"connected",...}
```

---

## ESTADO ATUAL DOS SERVIDORES

| Serviço | Porta | Status |
|---------|-------|--------|
| PostgreSQL 15 + PostGIS | 5432 | ✅ rodando (Docker) |
| Redis | 6379 | ✅ rodando (Docker) |
| FastAPI (hot-reload) | 8000 | ✅ rodando |
| Swagger UI | 8000/docs | ✅ acessível |

---

## O QUE AINDA FALTA (Sprint 1 — Fase 2)

| Item | Arquivo | Prioridade |
|------|---------|-----------|
| Downloader Sentinel-2 | `app/pipeline/downloader.py` | ALTA |
| Cálculo NDVI + SCL mask | `app/pipeline/ndvi.py` | ALTA |
| Motor de detecção de anomalias | `app/pipeline/anomaly_detector.py` | ALTA |
| Preprocessador (cloud mask) | `app/pipeline/preprocessor.py` | ALTA |
| Scheduler com job real | `app/pipeline/scheduler.py` | ALTA |
| Migrations Alembic | `migrations/` | MÉDIA |
| Geração de tiles PMTiles | `app/pipeline/tiles.py` | BAIXA |
| Push notifications FCM | Sprint 2 | BAIXA |

---

## OBSERVAÇÕES PARA O SERVIDOR DE PRODUÇÃO (167.71.28.159)

1. **Migrations:** o banco no servidor pode ter sido criado com `create_tables()`. Antes do deploy, verificar se as colunas `area_ha` e `crop` existem na tabela `farms`:
   ```sql
   SELECT column_name FROM information_schema.columns WHERE table_name='farms';
   ```
   Se não existirem, rodar:
   ```sql
   ALTER TABLE farms ADD COLUMN area_ha FLOAT;
   ALTER TABLE farms ADD COLUMN crop VARCHAR(100);
   ```

2. **Variáveis de ambiente:** trocar no `.env` de produção:
   - `SECRET_KEY` — gerar com `openssl rand -hex 32`
   - `JWT_SECRET_KEY` — gerar com `openssl rand -hex 32`
   - `APP_ENV=production`

3. **Python 3.14 no local vs 3.11 no servidor:** as versões instaladas localmente são mais novas (sem pin de versão). No deploy o Docker usa Python 3.11-slim — as versões pinadas no `requirements.txt` precisam ser atualizadas para as instaladas localmente antes do deploy:
   - `fastapi>=0.135.1`
   - `uvicorn>=0.42.0`
   - `sqlalchemy>=2.0.48`
   - `asyncpg>=0.31.0`
   - `pydantic>=2.12.5`
   - `bcrypt>=5.0.0`

4. **psycopg2-binary:** não foi instalado localmente (sem wheel para Python 3.14). No Docker (Python 3.11) instala normalmente — manter no requirements.txt para produção.
