"""
tests/integration/test_api_live.py
────────────────────────────────────
Testes de integração contra a API em produção (Railway).
Execute com:
    pytest tests/integration/test_api_live.py -v

Variáveis de ambiente necessárias (ou use os defaults de teste):
    API_BASE_URL   — ex: https://techa-backend-production.up.railway.app
    TEST_EMAIL     — email de usuário de teste
    TEST_PASSWORD  — senha do usuário de teste
"""

import os
import uuid
import pytest
import httpx

# ── Config ───────────────────────────────────────────────────────
BASE_URL    = os.getenv("API_BASE_URL", "https://techa-backend-production.up.railway.app")
TEST_EMAIL  = os.getenv("TEST_EMAIL",   "caio.teste@techa.com")
TEST_PASS   = os.getenv("TEST_PASSWORD","Senha@123")

# GeoJSON de um polígono simples no MS/BR para testes
_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [-55.70, -22.10],
        [-55.60, -22.10],
        [-55.60, -22.00],
        [-55.70, -22.00],
        [-55.70, -22.10],
    ]],
}


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    resp = client.post("/api/v1/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASS,
    })
    assert resp.status_code == 200, f"Login falhou: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def farm_id(client, auth):
    """Reutiliza a primeira fazenda existente, ou cria uma se ainda não houver."""
    # Tenta reusar existente (evita bater limite do plano free)
    existing = client.get("/api/v1/farms", headers=auth)
    if existing.status_code == 200 and existing.json():
        yield existing.json()[0]["id"]
        return

    resp = client.post("/api/v1/farms", headers=auth, json={
        "name": "Fazenda Test Suite",
        "area_ha": 100.0,
        "crop": "soja",
        "city": "Campo Grande",
        "state": "MS",
    })
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    yield fid
    client.delete(f"/api/v1/farms/{fid}", headers=auth)


@pytest.fixture(scope="session")
def field_id(client, auth, farm_id):
    """Cria um talhão de teste e o remove ao final."""
    resp = client.post(f"/api/v1/farms/{farm_id}/fields", headers=auth, json={
        "name": "Talhao Test",
        "crop": "soja",
        "geometry": _POLYGON,
    })
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    yield fid
    # cleanup
    client.delete(f"/api/v1/fields/{fid}", headers=auth)


# ── Testes de saúde ───────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["database"] == "connected"


# ── Testes de autenticação ────────────────────────────────────────

class TestAuth:
    def test_login_retorna_token(self, client):
        r = client.post("/api/v1/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASS,
        })
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["token_type"] == "bearer"

    def test_login_senha_errada_401(self, client):
        r = client.post("/api/v1/auth/login", json={
            "email": TEST_EMAIL,
            "password": "senha_errada_123",
        })
        assert r.status_code == 401

    def test_me_retorna_usuario(self, client, auth):
        r = client.get("/api/v1/auth/me", headers=auth)
        assert r.status_code == 200
        assert r.json()["email"] == TEST_EMAIL

    def test_sem_token_retorna_401(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401


# ── Testes de fazendas ────────────────────────────────────────────

class TestFarms:
    def test_listar_farms(self, client, auth):
        r = client.get("/api/v1/farms", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_listar_farms_paginacao(self, client, auth):
        r = client.get("/api/v1/farms?limit=1&offset=0", headers=auth)
        assert r.status_code == 200
        assert len(r.json()) <= 1

    def test_criar_e_deletar_farm(self, client, auth):
        # Verifica limite antes de criar
        existing = client.get("/api/v1/farms", headers=auth).json()
        if len(existing) >= 3:
            pytest.skip("Limite de plano free atingido — skip criação de nova fazenda")

        r = client.post("/api/v1/farms", headers=auth, json={
            "name": "Farm Temp",
            "area_ha": 50.0,
            "crop": "milho",
            "city": "Dourados",
            "state": "MS",
        })
        assert r.status_code == 201
        farm = r.json()
        assert farm["name"] == "Farm Temp"

        del_r = client.delete(f"/api/v1/farms/{farm['id']}", headers=auth)
        assert del_r.status_code == 204

    def test_farm_nao_encontrada_404(self, client, auth):
        fake_id = uuid.uuid4()
        r = client.get(f"/api/v1/farms/{fake_id}", headers=auth)
        assert r.status_code == 404


# ── Testes de talhões ─────────────────────────────────────────────

class TestFields:
    def test_criar_talhao_com_geojson(self, client, auth, farm_id):
        r = client.post(f"/api/v1/farms/{farm_id}/fields", headers=auth, json={
            "name": "Talhao Inline",
            "crop": "trigo",
            "geometry": _POLYGON,
        })
        assert r.status_code == 201
        f = r.json()
        assert f["name"] == "Talhao Inline"
        assert f["area_ha"] > 0
        assert f["geometry"]["type"] == "Polygon"
        # Limpa
        client.delete(f"/api/v1/fields/{f['id']}", headers=auth)

    def test_listar_talhoes(self, client, auth, farm_id, field_id):
        r = client.get(f"/api/v1/farms/{farm_id}/fields", headers=auth)
        assert r.status_code == 200
        ids = [f["id"] for f in r.json()]
        assert field_id in ids

    def test_detalhe_talhao(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}", headers=auth)
        assert r.status_code == 200
        assert r.json()["id"] == field_id

    def test_patch_talhao(self, client, auth, field_id):
        r = client.patch(f"/api/v1/fields/{field_id}", headers=auth, json={
            "crop": "milho",
        })
        assert r.status_code == 200
        assert r.json()["crop"] == "milho"
        # Reverte
        client.patch(f"/api/v1/fields/{field_id}", headers=auth, json={"crop": "soja"})

    def test_talhao_sem_permissao_404(self, client, auth):
        fake_id = uuid.uuid4()
        r = client.get(f"/api/v1/fields/{fake_id}", headers=auth)
        assert r.status_code == 404

    def test_geometria_invalida_422(self, client, auth, farm_id):
        r = client.post(f"/api/v1/farms/{farm_id}/fields", headers=auth, json={
            "name": "Invalido",
            "geometry": {"type": "Point", "coordinates": [0, 0]},  # Point não é válido
        })
        assert r.status_code == 422


# ── Testes de análises ────────────────────────────────────────────

class TestAnalyses:
    def test_listar_analises_vazio(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}/analyses", headers=auth)
        assert r.status_code == 200
        assert r.json() == []

    def test_latest_sem_analise_404(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}/analyses/latest", headers=auth)
        assert r.status_code == 404


# ── Testes de anomalias ───────────────────────────────────────────

class TestAnomalies:
    def test_listar_anomalias(self, client, auth):
        r = client.get("/api/v1/anomalies", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_listar_anomalias_filtro_status(self, client, auth):
        r = client.get("/api/v1/anomalies?status=active", headers=auth)
        assert r.status_code == 200

    def test_listar_anomalias_paginacao(self, client, auth):
        r = client.get("/api/v1/anomalies?limit=5&offset=0", headers=auth)
        assert r.status_code == 200
        assert len(r.json()) <= 5

    def test_anomalia_inexistente_404(self, client, auth):
        fake_id = uuid.uuid4()
        r = client.get(f"/api/v1/anomalies/{fake_id}", headers=auth)
        assert r.status_code == 404


# ── Testes de relatório PDF ───────────────────────────────────────

class TestReport:
    def test_gerar_pdf(self, client, auth, field_id):
        r = client.post(f"/api/v1/fields/{field_id}/report", headers=auth)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000  # PDF deve ter pelo menos 1KB


# ── Testes do estágio fenológico ──────────────────────────────────

class TestGrowthStage:
    def test_sem_planting_date_retorna_400(self, client, auth, field_id):
        # Remove planting_date primeiro
        client.patch(f"/api/v1/fields/{field_id}", headers=auth,
                     json={"planting_date": None})
        r = client.get(f"/api/v1/fields/{field_id}/growth-stage", headers=auth)
        assert r.status_code == 400

    def test_com_planting_date_retorna_estagio(self, client, auth, field_id):
        # Seta data de plantio
        client.patch(f"/api/v1/fields/{field_id}", headers=auth,
                     json={"planting_date": "2026-01-01", "crop": "soja"})
        r = client.get(f"/api/v1/fields/{field_id}/growth-stage", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert "stage_key" in d
        assert "progress_pct" in d
        assert d["progress_pct"] >= 0
        assert "days_since_planting" in d

    def test_estagio_retorna_campos_obrigatorios(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}/growth-stage", headers=auth)
        if r.status_code == 200:
            d = r.json()
            for campo in ("field_id", "crop", "planting_date", "stage_key",
                          "stage_label", "progress_pct", "cycle_complete"):
                assert campo in d, f"Campo obrigatório ausente: {campo}"


# ── Testes do histórico NDVI ──────────────────────────────────────

class TestNdviHistory:
    def test_ndvi_history_sem_analises(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}/ndvi-history", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["data_points"] == 0
        assert d["series"] == []
        assert d["trend"] is None

    def test_ndvi_history_paginacao(self, client, auth, field_id):
        r = client.get(f"/api/v1/fields/{field_id}/ndvi-history?limit=10", headers=auth)
        assert r.status_code == 200

    def test_ndvi_history_campo_nao_proprio_404(self, client, auth):
        fake_id = uuid.uuid4()
        r = client.get(f"/api/v1/fields/{fake_id}/ndvi-history", headers=auth)
        assert r.status_code == 404


# ── Testes do dashboard ───────────────────────────────────────────

class TestDashboard:
    def test_dashboard_retorna_total_area(self, client, auth):
        r = client.get("/api/v1/dashboard", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert "total_area_ha" in d
        assert d["total_area_ha"] >= 0
        assert "farms_count" in d
        assert "fields_count" in d
        assert "active_anomalies" in d
        assert isinstance(d["fields"], list)

    def test_dashboard_sem_token_401(self, client):
        r = client.get("/api/v1/dashboard")
        assert r.status_code == 401


# ── Testes de limites por plano ───────────────────────────────────

class TestPlanLimits:
    def test_limite_farm_free_plan(self, client, auth):
        """Usuário free não pode ter mais de 3 fazendas."""
        # Descobre quantas fazendas já existem
        r = client.get("/api/v1/farms", headers=auth)
        existing = len(r.json())

        created_ids = []
        last_status = 201
        # Tenta criar até bater o limite (3)
        for i in range(3 - existing + 1):
            resp = client.post("/api/v1/farms", headers=auth, json={
                "name": f"Fazenda Limite Test {i}",
                "area_ha": 10.0,
                "crop": "soja",
                "city": "Test",
                "state": "MS",
            })
            last_status = resp.status_code
            if resp.status_code == 201:
                created_ids.append(resp.json()["id"])

        # O último deve ser 403
        assert last_status == 403

        # Limpa
        for fid in created_ids:
            client.delete(f"/api/v1/farms/{fid}", headers=auth)
