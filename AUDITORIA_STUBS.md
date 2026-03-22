# AUDITORIA DE STUBS — Techá Backend
**Data:** 2026-03-16
**Auditor:** Claude (CTO Session)
**Projeto:** InnovAgro Py — Techá SaaS

---

## RESUMO EXECUTIVO

| Categoria | Total | Implementado | Stub / Vazio | Faltando |
|-----------|-------|-------------|--------------|---------|
| API Endpoints | 4 arquivos | 0 | 4 | 0 |
| Pipeline | 6 arquivos (README) | 0 | 1 | 5 |
| Core | 4 arquivos | 4 | 0 | 0 |
| Models | 6 arquivos | 6 | 0 | 0 |
| Schemas | 1 `__init__.py` | 0 | 0 | Todos |
| Repositories | 1 `__init__.py` | 0 | 0 | Todos |
| Services | 1 `__init__.py` | 0 | 0 | Todos |
| Migrations | pasta | 0 | 0 | Alembic não configurado |
| Testes | 3 arquivos | 3 | 0 | 0 |

**Grau de completude do Sprint 1:** ~30% (somente infra e modelos prontos)

---

## ARQUIVOS IMPLEMENTADOS (código real, funcionando)

### `app/core/config.py` ✅ COMPLETO
- Settings via Pydantic v2 com todas as variáveis de ambiente
- Validação de DATABASE_URL, propriedade `is_production`
- Singleton via `@lru_cache`
- Todas as variáveis do `.env.example` mapeadas

### `app/core/database.py` ✅ COMPLETO
- Engine assíncrona SQLAlchemy 2.0 + asyncpg
- Session factory `AsyncSessionLocal`
- Dependency `get_db()` para injeção nas rotas
- `check_db_connection()` para health check
- `create_tables()` para desenvolvimento

### `app/core/security.py` ✅ COMPLETO (com ressalva)
- `hash_password()` e `verify_password()` via bcrypt
- `create_access_token()` e `decode_access_token()` via python-jose
- Dependency `get_current_user_id()` pronto para uso nos routers
- **⚠️ RESSALVA:** usa `passlib` — o prompt indica bug de compatibilidade.
  A função está operacional mas pode falhar em Python 3.12+ com bcrypt >= 4.x

### `app/core/logging.py` ✅ COMPLETO
- Loguru configurado para dev (colorido) e produção (arquivo rotacionado)

### `app/main.py` ✅ COMPLETO (com ressalva)
- FastAPI app com lifespan correto
- CORS configurado
- Health check em `/health`
- Routers registrados (mas os routers são stubs)
- **⚠️ RESSALVA:** `from app.api.v1 import auth, farms, fields, anomalies` importa
  os módulos diretamente. O `app/api/v1/__init__.py` cria rotas com prefixos
  duplicados (`/api/v1/auth` + `/auth`) — esse arquivo é redundante e não é usado
  pelo main.py. Não causa erro mas pode gerar confusão.

### `app/models/user.py` ✅ COMPLETO
- Tabela `users`: id, name, email, password, plan, fcm_token, is_active, created_at
- Relacionamento com Farm (cascade delete)

### `app/models/farm.py` ✅ COMPLETO (com lacuna crítica)
- Tabela `farms`: id, user_id, name, city, state, created_at
- **❌ FALTA:** coluna `area_ha` (float) — usada na regra de negócio de threshold
- **❌ FALTA:** coluna `cultura` / `crop` — citada no exemplo de teste do prompt
- Relacionamento com User e Field

### `app/models/field.py` ✅ COMPLETO
- Tabela `fields`: id, farm_id, name, crop, planting_date, geometry (PostGIS POLYGON), area_ha, created_at
- Índice espacial GIST configurado
- Relacionamentos com Farm, SatelliteAnalysis, Anomaly

### `app/models/anomaly.py` ✅ COMPLETO
- Tabela `anomalies`: id, analysis_id, field_id, detected_at, ndvi_drop_pct, affected_area_ha, suspected_type, geometry (MULTIPOLYGON), status, push_sent, alert_sent_at
- Status: `active | inspected | resolved`

### `app/models/satellite_analysis.py` ✅ COMPLETO
- Tabela `satellite_analyses`: id, field_id, image_date, source, cloud_cover_pct, ndvi_mean/min/max, tiles_path, raster_path, status, baseline_provisional, processed_at
- Status: `valid | discarded_cloud | processing | error`

### `app/models/field_inspection.py` ✅ COMPLETO
- Tabela `field_inspections`: inspeção de campo pelo produtor

### `app/models/__init__.py` ✅ COMPLETO
- Importa todos os models (necessário para Alembic detectar)

### `tests/unit/test_ndvi.py` ✅ COMPLETO
- Testes da fórmula NDVI, SCL mask, thresholds de área
- **Obs:** imports dos módulos de pipeline estão comentados (TDD aguardando implementação)

### `tests/unit/test_ndvi_logic.py` ✅ COMPLETO
- `calculate_ndvi()`, `calculate_ndvi_drop()`, `get_alert_area_threshold()` implementados inline
- Cobertura boa dos casos de borda

### `tests/unit/test_security.py` ✅ COMPLETO
- Hash/verify de senhas e ciclo completo de JWT

---

## STUBS (arquivo existe mas sem implementação)

### `app/api/v1/auth.py` ❌ STUB VAZIO
```python
# app/api/v1/auth.py — implementação completa no Sprint 1
from fastapi import APIRouter
router = APIRouter()
```
**Impacto CRÍTICO:** Sem registro nem login, nenhum token JWT pode ser gerado.
O prompt afirma que "Auth já funciona" no servidor — isso indica que o arquivo
no servidor pode ser diferente do arquivo local. Este arquivo precisa ser implementado.

**Endpoints necessários:**
- `POST /auth/register` — cadastro de novo usuário
- `POST /auth/login`    — login com email+senha, retorna JWT

### `app/api/v1/farms.py` ❌ STUB VAZIO
```python
# app/api/v1/farms.py — implementação completa no Sprint 1
from fastapi import APIRouter
router = APIRouter()
```
**Impacto CRÍTICO:** Sem fazendas, não há talhões, sem talhões não há análise.

### `app/api/v1/fields.py` ❌ STUB VAZIO
```python
# app/api/v1/fields.py — implementação completa no Sprint 1
from fastapi import APIRouter
router = APIRouter()
```

### `app/api/v1/anomalies.py` ❌ STUB VAZIO
```python
# app/api/v1/anomalies.py — implementação completa no Sprint 1
from fastapi import APIRouter
router = APIRouter()
```

### `app/pipeline/scheduler.py` ❌ STUB (scheduler inicia mas sem jobs)
```python
def start_scheduler():
    scheduler = BackgroundScheduler()
    logger.info("Scheduler stub — implementação completa na US-01")
    scheduler.start()
    return scheduler
```
**Impacto ALTO:** O scheduler inicia (não quebra o servidor) mas nunca dispara
nenhuma análise Sentinel-2.

---

## ARQUIVOS FALTANDO (referenciados no README mas não existem)

| Arquivo esperado | Status | Impacto |
|-----------------|--------|---------|
| `app/pipeline/downloader.py` | ❌ NÃO EXISTE | CRÍTICO — sem download não há rasters |
| `app/pipeline/ndvi.py` | ❌ NÃO EXISTE | CRÍTICO — sem NDVI não há detecção |
| `app/pipeline/anomaly.py` (ou `anomaly_detector.py`) | ❌ NÃO EXISTE | CRÍTICO — motor do produto |
| `app/pipeline/preprocessor.py` | ❌ NÃO EXISTE | ALTO — sem SCL mask, nuvens geram falsos positivos |
| `app/pipeline/tiles.py` | ❌ NÃO EXISTE | MÉDIO — tiles para mapa (Sprint 1 secundário) |
| `app/schemas/` (conteúdo) | ❌ VAZIO | CRÍTICO — sem schemas não há validação |
| `app/repositories/` (conteúdo) | ❌ VAZIO | ALTO — sem repositories, queries diretas nos endpoints |
| `app/services/` (conteúdo) | ❌ VAZIO | ALTO — lógica de negócio inline |
| `migrations/` (pasta) | ❌ NÃO EXISTE | ALTO — sem migrations, schema gerenciado manualmente |
| `scripts/init_db.sql` | não verificado | MÉDIO — extensão PostGIS |

---

## PROBLEMAS CRÍTICOS IDENTIFICADOS

### 1. Farm model sem `area_ha`
O modelo `Farm` possui: `id, user_id, name, city, state, created_at`
**Falta:** `area_ha: float` — campo essencial para calcular threshold de alertas.
O threshold (3%/2%/1.5%) é calculado sobre a área do **talhão** (`Field.area_ha`),
mas o prompt exige `area_ha` na criação de fazenda também.

### 2. `passlib` com bcrypt — bug de compatibilidade
`requirements.txt` usa `passlib[bcrypt]==1.7.4` + `bcrypt` implícito.
O prompt diz explicitamente: **"Não usar passlib — tem bug de compatibilidade"**.
Com bcrypt >= 4.0, passlib emite warnings e pode falhar.
**Solução:** migrar para `bcrypt` direto.

### 3. Conflito de prefixos em `app/api/v1/__init__.py`
O `__init__.py` define prefixos `/auth`, `/farms`, etc. internamente,
mas `main.py` importa cada router individualmente e adiciona apenas `/api/v1`.
Isso significa que os endpoints ficarão em `/api/v1/<rota>` sem subprefixo,
a menos que cada router defina `/farms`, `/farms/{id}` etc. nos paths.

**Solução recomendada:** em cada router, definir os paths com prefixo explícito:
```python
@router.post("/farms")
@router.get("/farms/{farm_id}")
```
OU alterar o `main.py` para passar o prefixo correto:
```python
app.include_router(farms.router, prefix=f"{PREFIX}/farms", tags=["Fazendas"])
```

### 4. Migrations ausentes
Sem a pasta `migrations/`, o Alembic não está configurado localmente.
O banco no servidor provavelmente foi criado com `create_tables()` diretamente
ou com migrations geradas em outra sessão.

---

## PLANO DE IMPLEMENTAÇÃO (ordem de prioridade)

```
FASE 1 — Fundação (sem isso nada funciona)
  [1] Criar app/schemas/auth.py, farm.py, field.py, anomaly.py
  [2] Implementar app/api/v1/auth.py (register + login)
  [3] Corrigir Farm model: adicionar area_ha
  [4] Implementar app/api/v1/farms.py (CRUD completo)
  [5] Implementar app/api/v1/fields.py (CRUD + GeoJSON)
  [6] Implementar app/api/v1/anomalies.py (lista + confirm/dismiss)

FASE 2 — Pipeline Sentinel-2
  [7] Criar app/pipeline/ndvi.py (cálculo NDVI + SCL mask)
  [8] Criar app/pipeline/downloader.py (Copernicus STAC API)
  [9] Criar app/pipeline/anomaly_detector.py (regra de negócio)
  [10] Atualizar app/pipeline/scheduler.py (registrar job real)

FASE 3 — Qualidade
  [11] Configurar Alembic (migrations/)
  [12] Resolver bug do passlib
```

---

## NOTA SOBRE O SERVIDOR DE PRODUÇÃO

O servidor `167.71.28.159` tem Auth funcionando segundo o prompt.
Isso sugere que o código local está desatualizado em relação ao servidor,
OU que as migrações foram rodadas manualmente com `create_tables()`.
Antes de fazer deploy, verificar:
```bash
ssh root@167.71.28.159 "cat /opt/techa/backend/app/api/v1/auth.py"
```
Se auth.py no servidor tiver implementação, copiar de lá antes de sobrescrever.
