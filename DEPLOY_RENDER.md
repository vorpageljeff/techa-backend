# Deploy no Render

Este backend deve ser publicado no Render a partir do GitHub, usando a branch `main` para producao.

## Fluxo de ambientes

```text
feature/* -> develop -> test -> main
```

Para producao, o Render deve acompanhar a branch `main`.

## Criacao do servico

1. No Render, escolha **New > Blueprint**.
2. Selecione o repositorio `Innovagro-py/TechaMVP`.
3. Confirme o arquivo `render.yaml` na raiz do repositorio.
4. Preencha os segredos solicitados, se forem usados:
   - `RESEND_API_KEY`
   - `FIREBASE_CREDENTIALS_BASE64`

O Blueprint cria:

- Web service Docker `techa-backend-prod`
- PostgreSQL `techa-backend-prod-db`
- Redis/Key Value `techa-backend-prod-redis`

## Observacoes

- `ENABLE_PIPELINE=false` em producao evita rodar o scheduler Sentinel-2 junto com a API.
- As migrations rodam antes do deploy via `alembic upgrade head`.
- O health check usa `/health`.
- O deploy automatico usa `checksPass`, entao o Render so publica quando os checks do GitHub passarem.

Se o pipeline Sentinel-2 for ativado depois, configure tambem:

- `COPERNICUS_USER`
- `COPERNICUS_PASSWORD`
- ou `COPERNICUS_CLIENT_ID`
- e `COPERNICUS_CLIENT_SECRET`
