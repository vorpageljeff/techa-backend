# ─────────────────────────────────────────────────────────────────
# app/pipeline/downloader.py
# Download de imagens Sentinel-2 via Copernicus Data Space (CDSE)
# Busca:     STAC API  (catalogue.dataspace.copernicus.eu/stac)
# Catálogo:  OData API (catalogue.dataspace.copernicus.eu/odata)
# Download:  OData API (download.dataspace.copernicus.eu/odata)
#
# O STAC retorna URLs s3:// que não funcionam com requests.
# A solução é usar o OData catalog para localizar o produto e depois
# navegar pela árvore de Nodes para obter URLs HTTP de download.
# ─────────────────────────────────────────────────────────────────

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from requests import Session, Request as _Request
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

# Coleção correta: tudo minúsculo com hifens (CRÍTICO)
SENTINEL_COLLECTION = "sentinel-2-l2a"
MAX_CLOUD_COVER = 30
DAYS_BACK = 15

# OData: busca de produtos (catálogo)
ODATA_CATALOG = "https://catalogue.dataspace.copernicus.eu/odata/v1"
# OData: download de arquivos (nós e $value)
ODATA_DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1"


# ── Autenticação ──────────────────────────────────────────────────

def _get_token() -> str:
    """
    Obtém Bearer token OAuth2 do Copernicus Data Space Ecosystem (CDSE).

    Dois métodos suportados (tentados em ordem):
    1. Password grant com conta pessoal CDSE — OBRIGATÓRIO para downloads OData.
       Variáveis: COPERNICUS_USER (email) + COPERNICUS_PASSWORD
    2. Client credentials (sh-* service account) — funciona apenas para STAC/catálogo,
       NÃO funciona para download (erro 401 "Token audience not allowed").
       Variáveis: COPERNICUS_CLIENT_ID + COPERNICUS_CLIENT_SECRET
    """
    token_url = os.getenv(
        "COPERNICUS_TOKEN_URL",
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
    )

    cdse_user = os.getenv("COPERNICUS_USER", "")
    cdse_pass = os.getenv("COPERNICUS_PASSWORD", "")

    if cdse_user and cdse_pass:
        # Método 1: password grant — token com audiência para downloads
        resp = requests.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": "cdse-public",
                "username": cdse_user,
                "password": cdse_pass,
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            return token
        raise ValueError("Token CDSE (password grant) não retornado")

    # Método 2: client_credentials — apenas para busca STAC/catálogo
    client_id = os.getenv("COPERNICUS_CLIENT_ID", "")
    client_secret = os.getenv("COPERNICUS_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise ValueError(
            "Credenciais Copernicus ausentes. "
            "Configure COPERNICUS_USER+COPERNICUS_PASSWORD (recomendado) "
            "ou COPERNICUS_CLIENT_ID+COPERNICUS_CLIENT_SECRET no .env"
        )
    resp = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise ValueError("Token Copernicus não retornado — verificar CLIENT_ID e CLIENT_SECRET")
    logger.warning(
        "Usando token client_credentials (sh-*). "
        "Downloads OData vão falhar com 401 — configure COPERNICUS_USER e COPERNICUS_PASSWORD."
    )
    return token


# ── Busca STAC ────────────────────────────────────────────────────

def search_images(bbox: list[float], days_back: int = DAYS_BACK) -> list:
    """
    Busca imagens Sentinel-2 L2A para um bbox nos últimos N dias.

    Args:
        bbox: [min_lon, min_lat, max_lon, max_lat] em WGS84
        days_back: janela de busca em dias

    Returns:
        Lista de STACItem ordenada do mais recente para o mais antigo.
    """
    stac_url = os.getenv(
        "SENTINEL_STAC_URL",
        "https://catalogue.dataspace.copernicus.eu/stac",
    )

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days_back)
    date_range = (
        f"{start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}/"
        f"{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    )

    try:
        from pystac_client import Client

        catalog = Client.open(stac_url)
        search = catalog.search(
            collections=[SENTINEL_COLLECTION],
            bbox=bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lte": MAX_CLOUD_COVER}},
            max_items=10,
        )
        items = list(search.items())

        # Ordena do mais recente para o mais antigo
        items.sort(
            key=lambda x: x.datetime if x.datetime else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        logger.info(
            f"Copernicus STAC: {len(items)} imagens encontradas | "
            f"bbox={bbox} | últimos {days_back} dias"
        )
        return items

    except Exception as exc:
        logger.error(f"Erro na busca STAC: {exc}")
        return []


# ── OData: navegação e download ───────────────────────────────────

def _odata_get(url: str, token: str) -> dict:
    """
    Faz GET em um endpoint OData com Bearer token.

    Usa PreparedRequest para enviar a URL exatamente como fornecida,
    sem que o requests re-encode espaços, aspas ou '$' nos parâmetros
    OData ($filter, $select). Isso é necessário porque o endpoint
    Copernicus rejeita filtros com encoding (400 Bad Request).
    """
    session = Session()
    prepared = _Request(
        "GET",
        "http://placeholder",
        headers={"Authorization": f"Bearer {token}"},
    ).prepare()
    # Sobrescreve a URL APÓS prepare() para evitar qualquer re-encoding
    prepared.url = url
    resp = session.send(prepared, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _odata_nodes(url: str, token: str) -> list:
    """Faz GET em um endpoint OData Nodes e retorna a lista de itens."""
    data = _odata_get(url, token)
    # OData retorna 'result' ou 'value' dependendo do endpoint
    return data.get("result", data.get("value", []))


def _find_product_nodes_url(product_name: str, token: str) -> Optional[str]:
    """
    Busca o produto pelo nome no OData Catalog e retorna a URL do nó raiz.

    CRÍTICO: constrói a URL manualmente para evitar URL-encoding do '$'
    pelo requests. O OData requer '$filter' com '$' literal.

    NOTA: $select não pode incluir 'Nodes' pois é uma navigation property,
    não um campo regular — isso causa 400 Bad Request. A URL de nodes é
    construída manualmente usando o Id do produto retornado.

    Args:
        product_name: ID do produto STAC (com ou sem .SAFE)
    Returns:
        URL de nodes do produto ou None se não encontrado.
    """
    safe_name = product_name if product_name.endswith(".SAFE") else f"{product_name}.SAFE"

    # Sem $select — evita 400 causado por 'Nodes' ser navigation property
    url = f"{ODATA_CATALOG}/Products?$filter=Name eq '{safe_name}'&$top=1"

    try:
        data = _odata_get(url, token)
    except requests.HTTPError as e:
        logger.error(f"OData catalog retornou erro: {e} | URL: {url}")
        return None

    items = data.get("result", data.get("value", []))

    if not items:
        logger.warning(f"Produto não encontrado no OData: {safe_name}")
        return None

    item = items[0]

    # Tenta pegar nodes_url da resposta (campo Nodes se $expand foi usado)
    nodes_info = item.get("Nodes", {})
    nodes_url = nodes_info.get("uri", "") if isinstance(nodes_info, dict) else ""

    if not nodes_url:
        # Constrói a URL usando o Id retornado (UUID do produto)
        product_id = item.get("Id") or item.get("id", "")
        if not product_id:
            logger.error(f"Id não encontrado na resposta OData para {safe_name}")
            return None
        # Products({id})/Nodes retorna o .SAFE como único item no topo
        top_nodes_url = f"{ODATA_DOWNLOAD}/Products({product_id})/Nodes"

        # Navega para dentro do .SAFE para expor GRANULE, DATASTRIP, etc.
        top_items = _odata_nodes(top_nodes_url, token)
        safe_node = next(
            (i for i in top_items if str(i.get("Name", "")).endswith(".SAFE")),
            top_items[0] if top_items else None,
        )
        if not safe_node or not safe_node.get("Nodes", {}).get("uri"):
            logger.error(f"Não foi possível navegar para o interior do .SAFE: {top_items}")
            return None
        nodes_url = safe_node["Nodes"]["uri"]

    logger.info(f"Produto OData encontrado: {safe_name} | Id: {item.get('Id', 'N/A')}")
    logger.debug(f"Nodes URL (dentro do .SAFE): {nodes_url}")
    return nodes_url


def _navigate_to_bands(root_nodes_url: str, token: str) -> Optional[dict[str, str]]:
    """
    Navega pela estrutura de diretórios do produto Sentinel-2 L2A:
      .SAFE/ → GRANULE/ → L2A_T*/ → IMG_DATA/ → R10m/ e R20m/

    Retorna dict com URLs de download para B04, B08 e SCL.
    """
    # Nível 1: conteúdo do .SAFE (GRANULE, DATASTRIP, etc.)
    safe_items = _odata_nodes(root_nodes_url, token)
    granule_node = next((i for i in safe_items if i.get("Name") == "GRANULE"), None)
    if not granule_node:
        logger.error(f"GRANULE não encontrado. Disponível: {[i.get('Name') for i in safe_items]}")
        return None

    # Nível 2: conteúdo de GRANULE (L2A_T21JYN_...)
    granule_nodes_url = granule_node["Nodes"]["uri"]
    granule_items = _odata_nodes(granule_nodes_url, token)
    if not granule_items:
        logger.error("GRANULE vazio")
        return None

    granule_dir = granule_items[0]  # primeiro (e único) granule
    granule_name = granule_dir["Name"]
    logger.debug(f"Granule: {granule_name}")

    # Nível 3: conteúdo do granule → IMG_DATA
    granule_content_url = granule_dir["Nodes"]["uri"]
    granule_content = _odata_nodes(granule_content_url, token)
    img_data_node = next((i for i in granule_content if i.get("Name") == "IMG_DATA"), None)
    if not img_data_node:
        logger.error(f"IMG_DATA não encontrado. Disponível: {[i.get('Name') for i in granule_content]}")
        return None

    # Nível 4: conteúdo de IMG_DATA (R10m, R20m, R60m)
    img_data_items = _odata_nodes(img_data_node["Nodes"]["uri"], token)
    r10m_node = next((i for i in img_data_items if i.get("Name") == "R10m"), None)
    r20m_node = next((i for i in img_data_items if i.get("Name") == "R20m"), None)

    if not r10m_node or not r20m_node:
        logger.error(
            f"R10m/R20m não encontrados. Disponível: {[i.get('Name') for i in img_data_items]}"
        )
        return None

    # Nível 5: arquivos .jp2 em R10m e R20m
    r10m_files = _odata_nodes(r10m_node["Nodes"]["uri"], token)
    r20m_files = _odata_nodes(r20m_node["Nodes"]["uri"], token)

    b04_file = next((f for f in r10m_files if "_B04_10m" in f.get("Name", "")), None)
    b08_file = next((f for f in r10m_files if "_B08_10m" in f.get("Name", "")), None)
    scl_file = next((f for f in r20m_files if "_SCL_20m" in f.get("Name", "")), None)

    if not b04_file or not b08_file:
        logger.error(
            f"Bandas B04/B08 não encontradas em R10m. "
            f"Arquivos: {[f.get('Name') for f in r10m_files[:6]]}"
        )
        return None

    if not scl_file:
        logger.warning(
            f"SCL não encontrado em R20m. "
            f"Arquivos: {[f.get('Name') for f in r20m_files[:6]]}"
        )

    def _dl_url(nodes_base_url: str, filename: str) -> str:
        """Constrói URL de download direto: ...Nodes(filename)/$value"""
        base = nodes_base_url.rstrip("/")
        # Remove trailing /Nodes se existir e reconstrói de forma limpa
        if base.endswith("/Nodes"):
            base = base[:-6]
        return f"{base}/Nodes({filename})/$value"

    r10m_base = r10m_node["Nodes"]["uri"]
    r20m_base = r20m_node["Nodes"]["uri"]

    result: dict[str, str] = {
        "B04": _dl_url(r10m_base, b04_file["Name"]),
        "B08": _dl_url(r10m_base, b08_file["Name"]),
    }
    if scl_file:
        result["SCL"] = _dl_url(r20m_base, scl_file["Name"])

    logger.info(
        f"Bandas localizadas: B04={b04_file['Name']} | "
        f"B08={b08_file['Name']} | "
        f"SCL={scl_file['Name'] if scl_file else 'N/A'}"
    )
    return result


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download_file(url: str, dest: Path, token: str) -> None:
    """Baixa um arquivo via HTTP com Bearer token. Retry automático em falha."""
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=180,
    )
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)


# ── Função principal ──────────────────────────────────────────────

def download_bands(
    stac_item,
    field_id: str,
    save_dir: str = "/data/rasters",
) -> Optional[dict[str, Path]]:
    """
    Baixa as bandas B04 (RED), B08 (NIR) e SCL de um item STAC
    usando a API OData do Copernicus Data Space.

    Fluxo:
      1. Busca produto no OData Catalog pelo nome (STAC item id)
      2. Navega pela árvore de Nodes até R10m/R20m
      3. Baixa os arquivos .jp2 com Bearer token

    Args:
        stac_item: pystac.Item retornado por search_images()
        field_id:  UUID do talhão — organiza o diretório de destino
        save_dir:  raiz do armazenamento local (default: /data/rasters)

    Returns:
        dict com chaves 'B04', 'B08', 'SCL' e Path local de cada arquivo,
        ou None se o download falhar.
    """
    try:
        token = _get_token()
        product_name = stac_item.id
        date_str = stac_item.datetime.strftime("%Y-%m-%d")
        dest_dir = Path(save_dir) / str(field_id) / date_str
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Verifica se já foi baixado anteriormente (> 500KB = arquivo real)
        cached: dict[str, Path] = {}
        for band in ("B04", "B08", "SCL"):
            p = dest_dir / f"{band}.jp2"
            if p.exists() and p.stat().st_size > 500_000:
                cached[band] = p
        if "B04" in cached and "B08" in cached:
            logger.info(f"Bandas já em cache para {field_id}/{date_str}")
            return cached

        # 1. Localiza produto no OData Catalog
        logger.info(f"Buscando produto OData: {product_name}")
        nodes_url = _find_product_nodes_url(product_name, token)
        if not nodes_url:
            return None

        # 2. Navega pela estrutura de diretórios
        logger.info("Navegando estrutura de diretórios Sentinel-2...")
        band_urls = _navigate_to_bands(nodes_url, token)
        if not band_urls:
            return None

        # 3. Baixa cada banda
        paths: dict[str, Path] = {}
        for band_name, url in band_urls.items():
            dest_file = dest_dir / f"{band_name}.jp2"

            if dest_file.exists() and dest_file.stat().st_size > 500_000:
                logger.debug(f"{band_name} já em cache: {dest_file}")
                paths[band_name] = dest_file
                continue

            logger.info(f"Baixando {band_name}...")
            _download_file(url, dest_file, token)

            size_mb = dest_file.stat().st_size / 1_048_576
            # Limites mínimos: B04/B08 precisam de pelo menos 1MB (10m resolution)
            # SCL pode ser menor (20m resolution, tile parcial) — mínimo 50KB
            min_mb = 1.0 if band_name in ("B04", "B08") else 0.05
            if size_mb < min_mb:
                logger.error(
                    f"{band_name} muito pequeno ({size_mb:.2f} MB, mín {min_mb}MB) — "
                    "possível erro de autenticação ou arquivo inválido"
                )
                if band_name in ("B04", "B08"):
                    return None  # Bandas essenciais: falha crítica
                else:
                    logger.warning(f"SCL ignorado (tamanho inválido) — continuando sem máscara de nuvens")
                    continue  # SCL é opcional

            logger.info(f"{band_name} OK: {size_mb:.1f} MB")
            paths[band_name] = dest_file

        # Valida bandas essenciais
        if "B04" not in paths or "B08" not in paths:
            logger.error(
                f"Bandas essenciais (B04, B08) não baixadas para {product_name}. "
                f"Baixadas: {list(paths.keys())}"
            )
            return None

        logger.info(f"Download completo: {list(paths.keys())} → {dest_dir}")
        return paths

    except Exception as exc:
        logger.error(f"Erro ao baixar bandas de {stac_item.id}: {exc}")
        return None
